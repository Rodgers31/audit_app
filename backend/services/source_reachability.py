"""On-demand, process-local homepage observations; never ingestion authority."""
import asyncio
import copy
from datetime import datetime, timezone
import ssl
import threading
import time
from typing import Literal

import httpx
from pydantic import BaseModel


SOURCES = {
    "knbs": ("Kenya National Bureau of Statistics", "https://www.knbs.or.ke"),
    "cob": ("Controller of Budget", "https://cob.go.ke"),
    "treasury": ("National Treasury", "https://www.treasury.go.ke"),
    "cbk": ("Central Bank of Kenya", "https://www.centralbank.go.ke"),
    "oag": ("Office of the Auditor General", "https://www.oagkenya.go.ke"),
}
REFRESH_SECONDS = 300
BATCH_SECONDS = 3

FailureReason = Literal[
    "certificate_expired", "certificate_chain_unverified", "certificate_hostname_mismatch",
    "certificate_untrusted", "connect_timeout", "response_timeout", "request_timeout",
    "redirect_limit", "request_failed",
]
FAILURE_MESSAGES = {
    "certificate_expired": "The publisher's HTTPS certificate has expired. A renewed certificate is required.",
    "certificate_chain_unverified": "The publisher's HTTPS certificate chain could not be verified. A complete trusted chain is required.",
    "certificate_hostname_mismatch": "The HTTPS certificate does not match the publisher hostname.",
    "certificate_untrusted": "The publisher's HTTPS certificate could not be verified.",
    "connect_timeout": "The homepage connection exceeded the check budget; source availability is unconfirmed.",
    "response_timeout": "The homepage response exceeded the check budget; source availability is unconfirmed.",
    "request_timeout": "The homepage check exceeded its time budget; source availability is unconfirmed.",
    "redirect_limit": "The homepage exceeded the permitted redirect limit.",
    "request_failed": "The homepage request failed; source availability is unconfirmed.",
}


class SourceObservation(BaseModel):
    key: str
    name: str
    url: str
    freshness: Literal["unknown", "fresh", "stale"]
    outcome: Literal["not_observed", "http_response", "timeout", "certificate_error", "request_error"]
    reachable: bool | None
    status_code: int | None = None
    observed_at: str | None = None
    failure_reason: FailureReason | None = None


class PipelineHealthV2(BaseModel):
    schema_version: Literal[2]
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    checked_at: str
    auto_seeder: dict | None
    database: dict
    sources: dict[str, SourceObservation]
    source_checks_in_progress: bool
    execution: dict
    alerts: list[dict]
    summary: dict


def exception_outcome(exc: Exception) -> str:
    """Classify without returning remote/library error text or internal paths."""
    return failure_detail(exc)[0]


def failure_detail(exc: Exception) -> tuple[str, FailureReason]:
    """Keep verification failures distinct without disclosing exception text."""
    if isinstance(exc, httpx.ConnectTimeout):
        return "timeout", "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "timeout", "response_timeout"
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout", "request_timeout"
    cause = exc
    certificate_seen = False
    for _ in range(8):
        if isinstance(cause, ssl.SSLCertVerificationError):
            code = getattr(cause, "verify_code", None)
            reasons = {10: "certificate_expired", 20: "certificate_chain_unverified",
                       21: "certificate_chain_unverified", 62: "certificate_hostname_mismatch"}
            return "certificate_error", reasons.get(code, "certificate_untrusted") if type(code) is int else "certificate_untrusted"
        certificate_seen = certificate_seen or "CERTIFICATE_VERIFY_FAILED" in str(cause)
        cause = cause.__cause__ or cause.__context__
        if cause is None:
            break
    if certificate_seen:
        return "certificate_error", "certificate_untrusted"
    if isinstance(exc, httpx.TooManyRedirects):
        return "request_error", "redirect_limit"
    return "request_error", "request_failed"


def observation_error(source: dict) -> str:
    reason = source.get("failure_reason")
    if isinstance(reason, str) and reason in FAILURE_MESSAGES:
        return FAILURE_MESSAGES[reason]
    return {"timeout": "Homepage check timed out.",
            "certificate_error": "Certificate verification failed.",
            "request_error": "Homepage request failed."}.get(
                source["outcome"], f"Homepage returned HTTP {source['status_code']}.")


class SourceReachability:
    """At most one five-host batch per process per five minutes, only on reads.

    Unknown/stale observations remain explicit. No timer, scheduler, DB, retry,
    source-body download or application writer is involved. A pending batch
    keeps its slot until cancellation/client cleanup has actually finished.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._clock = time.monotonic
        self._records = {}
        self._observed_mono = None
        self._next_attempt = 0.0
        self._running = False
        self._task = None

    def observe(self) -> tuple[dict, bool]:
        now = self._clock()
        with self._lock:
            if not self._running and now >= self._next_attempt:
                self._running = True
                self._next_attempt = now + REFRESH_SECONDS
                try:
                    self._task = asyncio.get_running_loop().create_task(self._refresh())
                except BaseException:
                    self._running = False
                    raise
            age = None if self._observed_mono is None else now - self._observed_mono
            freshness = "unknown" if age is None or age < 0 else (
                "fresh" if age < REFRESH_SECONDS else "stale"
            )
            sources = {}
            for key, (name, url) in SOURCES.items():
                record = copy.deepcopy(self._records.get(key, {}))
                sources[key] = dict(key=key, name=name, url=url, freshness=freshness,
                                    outcome="not_observed", reachable=None,
                                    status_code=None, observed_at=None, failure_reason=None) | record
                sources[key]["freshness"] = freshness
                if freshness == "unknown":
                    sources[key].update(outcome="not_observed", reachable=None,
                                        status_code=None, observed_at=None, failure_reason=None)
            return sources, self._running

    async def legacy(self) -> dict:
        """Older consumers require booleans, so wait for an actual observation.

        Cancellation of a caller never cancels shared work. Refuse instead of
        converting an unobserved homepage into a negative availability claim.
        """
        sources, _ = self.observe()
        if any(s["freshness"] != "fresh" for s in sources.values()):
            with self._lock:
                task = self._task
            if task is not None:
                await asyncio.shield(task)
            sources, _ = self.observe()
        if any(s["freshness"] != "fresh" or s["reachable"] is None for s in sources.values()):
            raise RuntimeError("SOURCE_OBSERVATION_UNAVAILABLE")
        result = {}
        for key, source in sources.items():
            row = {k: source[k] for k in ("key", "name", "url", "reachable")}
            if source["status_code"] is not None:
                row["status_code"] = source["status_code"]
            else:
                row["error"] = observation_error(source)
            result[key] = row
        return result

    async def _refresh(self):
        results = {}

        async def check(client, key, url):
            try:
                response = await client.head(url)
                result = dict(outcome="http_response", reachable=response.status_code < 500,
                              status_code=response.status_code, failure_reason=None)
            except Exception as exc:
                outcome, reason = failure_detail(exc)
                result = dict(outcome=outcome, reachable=False, status_code=None, failure_reason=reason)
            results[key] = result

        async def batch():
            async with httpx.AsyncClient(
                timeout=2.0, follow_redirects=True, max_redirects=2,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=0),
            ) as client:
                await asyncio.gather(*(check(client, key, url) for key, (_, url) in SOURCES.items()))

        try:
            try:
                await asyncio.wait_for(batch(), timeout=BATCH_SECONDS)
            except TimeoutError:
                for key in SOURCES:
                    results.setdefault(key, dict(outcome="timeout", reachable=False, status_code=None,
                                                 failure_reason="request_timeout"))
            except Exception:
                for key in SOURCES:
                    results.setdefault(key, dict(outcome="request_error", reachable=False, status_code=None,
                                                 failure_reason="request_failed"))
            observed = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._records = {key: value | {"observed_at": observed} for key, value in results.items()}
                self._observed_mono = self._clock()
        finally:
            with self._lock:
                self._running = False


def assemble_health(snapshot: dict, sources: dict, in_progress: bool) -> dict:
    alerts = copy.deepcopy(snapshot["alerts"])
    for key, source in sources.items():
        if source["freshness"] == "fresh" and source["reachable"] is False:
            detail = observation_error(source)
            alerts.append(dict(level="warning", source=key, message=detail))
    errors = sum(a["level"] == "error" for a in alerts)
    warnings = sum(a["level"] == "warning" for a in alerts)
    unknown = (set(sources) != set(SOURCES) or not snapshot["database"]
               or any(s["freshness"] != "fresh" or s["reachable"] is None for s in sources.values()))
    state = "unhealthy" if errors else "degraded" if warnings else "unknown" if unknown else "healthy"
    return dict(
        schema_version=2, status=state, checked_at=snapshot["checked_at"],
        auto_seeder=None if any(a["source"] == "auto_seeder" and a["level"] == "error" for a in alerts)
        else snapshot["auto_seeder"], database=snapshot["database"],
        sources=sources, source_checks_in_progress=in_progress,
        execution=dict(owner="dedicated seeding runner", status="not_observed",
                       evidence_url="/admin/etl", legacy_web_pipeline="retired"),
        alerts=alerts, summary=dict(errors=errors, warnings=warnings, total_alerts=len(alerts)),
    )

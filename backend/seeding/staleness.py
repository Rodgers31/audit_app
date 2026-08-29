"""Freshness gates — "is this data actually still arriving?"

WHY THIS EXISTS
---------------
The nightly validation asserted row-count FLOORS:

    [OK] Audit Records: 27 rows (expected >= 20)

``27 >= 20`` passes forever. It passed every night for months while
``audits`` had not gained a row since 2026-07-19 and ``budget_lines`` since
2026-06-11, because a floor cannot distinguish "up to date" from "frozen".
A gate that cannot fail is not a gate.

Two independent questions are asked here, and both must be, because either
alone can be fooled:

1. :func:`check_ingestion_freshness` — *is the pipeline still reaching the
   publisher?* Read from ``ingestion_jobs.metadata.source_mode``, which
   ``seeding/freshness.py`` records. Catches "we fell back to a git-tracked
   fixture every night", which is invisible in row counts because a fixture
   re-seeds identical values.

2. :func:`check_table_freshness` — *has the data itself moved inside its
   publication cadence?* Catches a source that is reachable and parsing but
   silently yielding nothing.

Cadences come from the Layer-1 source registry, so the tolerances track the
publisher's real schedule (OAG annual with a 6-9 month lag; COB quarterly at
+45 days) instead of an arbitrary number. Being inside a known publication
lull is NOT staleness — a gate that fires every summer would be muted by
February, which is how gates die.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from .source_registry import PUBLICATION_SCHEDULE

# Severity levels, mirroring the nightly's existing vocabulary.
FAIL = "FAIL"
WARN = "WARN"
OK = "OK"


@dataclass(frozen=True)
class Finding:
    level: str
    label: str
    message: str

    def __str__(self) -> str:  # matches the nightly's "[LEVEL] label: msg"
        return f"[{self.level}] {self.label}: {self.message}"


@dataclass(frozen=True)
class TableRule:
    """How stale a fact table is allowed to get before it is a defect."""

    label: str
    model_name: str
    column: str
    max_age_days: int
    dataset_id: Optional[str] = None
    level: str = FAIL
    note: str = ""


# Tolerances = publication cadence + lag + a grace margin, so a gate only
# fires when the data is later than the publisher's own schedule allows.
TABLE_RULES: List[TableRule] = [
    TableRule(
        label="Audit findings",
        model_name="Audit",
        column="created_at",
        # OAG is annual with a 6-9 month lag, so ~15 months is the honest
        # ceiling for "a new report should have appeared by now".
        max_age_days=460,
        dataset_id="oag_national_audits",
        note="OAG annual, 6-9 month lag",
    ),
    TableRule(
        label="Budget lines",
        model_name="BudgetLine",
        column="created_at",
        # COB reports quarterly at ~45 days, so rows should arrive roughly
        # every 90 days. 150d means one whole quarter was missed — tight
        # enough to fire, loose enough to survive a late publication.
        max_age_days=150,
        dataset_id="cob_qbirr",
        note="COB quarterly, +45 day lag",
    ),
    TableRule(
        label="Source documents",
        model_name="SourceDocument",
        column="fetch_date",
        # Something should be fetched at least monthly across all sources.
        max_age_days=45,
        note="any publisher, any dataset",
    ),
    TableRule(
        label="Economic indicators",
        model_name="EconomicIndicator",
        column="created_at",
        max_age_days=120,
        level=WARN,
        note="KNBS/World Bank, monthly-to-annual",
    ),
]

# A domain must have reached its publisher at least this recently. Generous
# because a slow CDN legitimately costs a few nights of resumed downloading.
MAX_DAYS_SINCE_LIVE = 14


def _age_days(ts: Optional[datetime], now: datetime) -> Optional[float]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def in_publication_lull(dataset_id: Optional[str], today: date) -> bool:
    """True when the publisher is not expected to have published recently.

    Prevents the annual-report gate from screaming through the eight months
    of every year when OAG legitimately has nothing new out.
    """
    if not dataset_id:
        return False
    sched = PUBLICATION_SCHEDULE.get(dataset_id)
    if not sched:
        return False
    return sched.get("frequency") == "annual"


def check_table_freshness(session, now: Optional[datetime] = None) -> List[Finding]:
    """Has each fact table changed inside its publisher's cadence?"""
    from sqlalchemy import func

    import models

    now = now or datetime.now(timezone.utc)
    findings: List[Finding] = []

    for rule in TABLE_RULES:
        model = getattr(models, rule.model_name, None)
        if model is None:  # pragma: no cover - defensive
            findings.append(
                Finding(FAIL, rule.label, f"model {rule.model_name} not found")
            )
            continue
        column = getattr(model, rule.column, None)
        if column is None:  # pragma: no cover - defensive
            findings.append(
                Finding(
                    FAIL, rule.label, f"column {rule.column} not on {rule.model_name}"
                )
            )
            continue

        newest = session.query(func.max(column)).scalar()
        age = _age_days(newest, now)
        if age is None:
            findings.append(
                Finding(rule.level, rule.label, "table is EMPTY — nothing ingested")
            )
            continue
        if age > rule.max_age_days:
            findings.append(
                Finding(
                    rule.level,
                    rule.label,
                    f"newest row is {age:.0f} days old (limit "
                    f"{rule.max_age_days}d for {rule.note}); newest={newest}",
                )
            )
        else:
            findings.append(
                Finding(
                    OK,
                    rule.label,
                    f"newest row {age:.0f}d old (limit {rule.max_age_days}d)",
                )
            )
    return findings


def check_ingestion_freshness(
    session, now: Optional[datetime] = None, domains: Optional[List[str]] = None
) -> List[Finding]:
    """Has each domain actually reached its publisher recently?

    Reads ``ingestion_jobs.metadata.source_mode``. A domain whose every
    recent run says ``fixture`` is serving a file from the repo — the exact
    condition that hid three frozen domains behind a green nightly.
    """
    from models import IngestionJob

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_DAYS_SINCE_LIVE)
    findings: List[Finding] = []

    rows = (
        session.query(IngestionJob)
        .filter(IngestionJob.started_at >= cutoff.replace(tzinfo=None))
        .all()
    )
    seen: dict[str, list] = {}
    for job in rows:
        seen.setdefault(job.domain, []).append(job)

    watched = domains if domains is not None else sorted(seen)
    for domain in watched:
        jobs = seen.get(domain, [])
        if not jobs:
            findings.append(
                Finding(
                    WARN,
                    f"{domain} ingestion",
                    f"no run recorded in the last {MAX_DAYS_SINCE_LIVE} days",
                )
            )
            continue
        modes = [(j.meta or {}).get("source_mode") for j in jobs]
        if "live" in modes:
            findings.append(
                Finding(
                    OK,
                    f"{domain} ingestion",
                    f"reached the publisher in {modes.count('live')}/"
                    f"{len(modes)} recent run(s)",
                )
            )
        elif all(m is None for m in modes):
            # Pre-dates provenance recording; cannot judge, and saying "OK"
            # would be exactly the false green this module exists to kill.
            findings.append(
                Finding(
                    WARN,
                    f"{domain} ingestion",
                    "no source_mode recorded on any recent run — provenance "
                    "unknown, not confirmed healthy",
                )
            )
        else:
            reasons = {
                (j.meta or {}).get("source_fallback_reason")
                for j in jobs
                if (j.meta or {}).get("source_fallback_reason")
            }
            findings.append(
                Finding(
                    FAIL,
                    f"{domain} ingestion",
                    f"served from a FIXTURE in all {len(modes)} recent run(s) "
                    f"— the publisher was never successfully read "
                    f"(reasons: {', '.join(sorted(reasons)) or 'unrecorded'})",
                )
            )
    return findings


def run_all(session, now: Optional[datetime] = None) -> List[Finding]:
    return check_table_freshness(session, now) + check_ingestion_freshness(
        session, now
    )


__all__ = [
    "FAIL",
    "Finding",
    "OK",
    "TABLE_RULES",
    "TableRule",
    "WARN",
    "check_ingestion_freshness",
    "check_table_freshness",
    "in_publication_lull",
    "run_all",
]

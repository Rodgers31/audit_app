"""A data-source outage must never render as a figure.

Sibling to ``test_no_withheld_data_on_public_endpoints.py``. That file asserts
*withheld* values do not reach the public. This one asserts the opposite
failure: values that were never in the database at all, **manufactured by the
API from a failure**, and therefore invisible to any withheld-value check
because ``0`` is not a withheld value.

The defect this pins, observed live on 2026-08-29 with the database
unreachable::

    GET /api/v1/debt/national  ->  200
    {"data": {"total_debt": 0, "total_outstanding": 0, "debt_to_gdp_ratio": 0}}

which the homepage rendered as::

    TOTAL DEBT AS OF — | KES 0.00T | DEBT-TO-GDP 0.0% | RISK LEVEL  LOW RISK

``classifyDebtRisk(0)`` falls into the ``< LOW_MAX`` branch, so a total
infrastructure failure displayed as a reassuring rating on the national
accounts. Both endpoints carried the comment "No hardcoded fallback — data
must come from the database" directly above a hardcoded block of zeros.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from database import get_db
from main import app

# Keys whose value is a published quantity. A zero here is a claim about the
# world. Counts (``loan_count``, ``total_fetches``, ``count``) are excluded:
# "zero rows recorded" is a legitimate, non-misleading answer for those.
MONEY_KEY = re.compile(
    r"(amount|debt|budget|spent|allocated|revenue|outstanding|ratio|pct|"
    r"percent|flagged|questioned|gdp|_kes|value)$",
    re.I,
)

# Routes exercised with a dead database, DERIVED from the running app rather
# than hand-listed.
#
# Reported by review on PR #135: this file previously carried a literal list of
# 16 routes while the PR description claimed new endpoints were covered "by
# construction". They were not — a new money endpoint joined the API untested,
# which is the exact regression mode the description said the suite eliminated.
#
# There are deliberately NO exclusions. Every GET under /api/v1/ is swept, and
# the ones that cannot contribute exclude themselves by answering something
# other than 2xx: auth-gated /admin/ routes answer 401, and a route that dies
# on the dead database answers 500 or 503. That is a stronger position than an
# exclusion list, which is another hand-maintained artefact that drifts. If a
# route ever genuinely needs excluding, add the mechanism WITH a reason — do
# not quietly drop it from the derivation.
API_PREFIX = "/api/v1/"

# Values for path and required-query params. Deliberately real-looking but
# certain to match nothing: the assertion is about how the API reports absence,
# and a fixture that accidentally matched a row would test the opposite.
PATH_PARAM_FIXTURES: Dict[str, str] = {
    "country_id": "1", "county_id": "001", "doc_id": "1", "document_id": "1",
    "entity_id": "1", "job_id": "1", "line_id": "1", "period_id": "1",
    "source": "cob", "table_name": "audits", "user_id": "1",
}
QUERY_PARAM_FIXTURES: Dict[str, str] = {
    "country": "KE", "period": "FY2024/25", "q": "health",
    "url": "https://example.invalid/report.pdf", "year": "2024",
}

# The 16 routes the hand-maintained list covered, kept as a FLOOR. The
# derivation must never return fewer than these. Without this, a route dropping
# out of the schema (include_in_schema=False, a router failing to register, a
# refactor) would shrink the sweep silently and it would still report green —
# trading one invisible gap for another.
HISTORICALLY_SWEPT: List[str] = [
    "/api/v1/debt/national",
    "/api/v1/dashboards/national/debt-mix",
    "/api/v1/debt/timeline",
    "/api/v1/debt/loans",
    "/api/v1/budget/overview",
    "/api/v1/budget/enhanced",
    "/api/v1/fiscal/summary",
    "/api/v1/sectors/spending",
    "/api/v1/audits/federal",
    "/api/v1/audit/summary",
    "/api/v1/accountability/missing-funds",
    "/api/v1/counties",
    "/api/v1/counties/{county_id}/comprehensive",
    "/api/v1/counties/{county_id}/accountability",
    "/api/v1/pending-bills/summary",
]


def _derived_routes() -> List[str]:
    """Every GET path under ``/api/v1/`` the app actually serves."""
    spec = app.openapi()
    return sorted(
        path
        for path, ops in spec.get("paths", {}).items()
        if "get" in ops and path.startswith(API_PREFIX)
    )


def _concrete_url(path: str, ops: Dict[str, Any]) -> tuple:
    """``path`` with params filled: a requestable URL plus its query dict."""
    url = re.sub(
        r"\{(\w+)\}",
        lambda m: PATH_PARAM_FIXTURES.get(m.group(1), "1"),
        path,
    )
    query = {
        prm["name"]: QUERY_PARAM_FIXTURES.get(prm["name"], "1")
        for prm in ops.get("get", {}).get("parameters", [])
        if prm.get("in") == "query" and prm.get("required")
    }
    return url, query


def _zeroed_money(obj: Any, path: str = "") -> List[str]:
    """Money-ish leaves whose value is a numeric zero."""
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                found += _zeroed_money(v, f"{path}.{k}")
            elif isinstance(v, bool):
                continue
            elif isinstance(v, (int, float)) and v == 0 and MONEY_KEY.search(k):
                found.append(f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            found += _zeroed_money(v, f"{path}[{i}]")
    return found


@pytest.fixture()
def dead_db_client():
    """A client whose data layer raises the way an unreachable Postgres does."""

    def _raise(*_a, **_kw):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    _startup = list(app.router.on_startup)
    _shutdown = list(app.router.on_shutdown)
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()

    # BOTH mechanisms are required; they cover different route styles.
    #
    #   patch("main.get_db")        -> handlers that call next(get_db()) directly
    #   app.dependency_overrides    -> handlers declaring Depends(get_db)
    #
    # FastAPI captures the dependency callable at decoration time, so rebinding
    # the module-level name never reaches a Depends route. 21 GET routes use
    # Depends(get_db); with only the patch installed, six requests in the sweep
    # below constructed a session from the REAL database.SessionLocal — whose
    # engine is postgresql against a non-local host, because conftest installs
    # its SQLite override only inside the `client` fixture and clears it after.
    # The sweep asserting the API survives an unreachable database was issuing
    # those requests against the configured live one. Pinned by
    # tests/test_review_findings_pr135.py::TestTheOutageSweepIsNotVacuous.
    def _dead_get_db():
        """The override MUST take no arguments.

        FastAPI introspects an override's signature and turns each parameter
        into a request field. A ``(*_a, **_kw)`` override therefore makes
        ``_a`` and ``_kw`` REQUIRED QUERY PARAMS on every route that depends on
        it, and all 21 answer 422 before the handler runs — which is not an
        outage, and leaves the sweep green over routes it still never
        exercised. Pinned by ``test_the_override_adds_no_request_parameters``.
        """
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    _saved_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _dead_get_db

    # The rate limiter is bypassed session-wide in conftest.pytest_configure;
    # patching it here would be a no-op (the middleware instance binds
    # dispatch_func at construction, long before this fixture runs).
    with patch("main.get_db", _raise):
        yield TestClient(app, raise_server_exceptions=False)

    if _saved_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = _saved_override
    app.router.on_startup = _startup
    app.router.on_shutdown = _shutdown


# ── the two endpoints this task fixes ──────────────────────────────────────


def test_debt_national_reports_absence_not_zero(dead_db_client):
    r = dead_db_client.get("/api/v1/debt/national")
    assert r.status_code < 500, r.text
    if r.status_code >= 300:
        return  # failing loudly is also acceptable
    body: Dict[str, Any] = r.json()
    data = body.get("data") or {}

    for field in ("total_debt", "total_outstanding", "gdp", "debt_to_gdp_ratio"):
        assert data.get(field) is None, (
            f"{field} is {data.get(field)!r} with the database unreachable — "
            "a zero here renders as 'KES 0.00T / LOW RISK' on the homepage"
        )
    assert body.get("reason"), "no machine-readable reason for the absence"
    assert body.get("data_source") == "database_unavailable", (
        "an outage must be distinguishable from an empty table, or the UI "
        "cannot tell 'we could not ask' from 'there is nothing'"
    )


def test_debt_mix_reports_absence_not_zero(dead_db_client):
    r = dead_db_client.get("/api/v1/dashboards/national/debt-mix")
    assert r.status_code < 500, r.text
    if r.status_code >= 300:
        return
    body = r.json()
    for field in ("external", "domestic", "external_amount", "domestic_amount", "total"):
        assert body.get(field) is None, (
            f"{field} is {body.get(field)!r} — a 0/0 split is a readable claim "
            "about the composition of public debt"
        )
    assert body.get("reason"), "no machine-readable reason for the absence"


# ── the general rule, so a new endpoint is covered by construction ─────────


def test_the_derivation_covers_everything_the_old_hand_list_did(dead_db_client):
    """The derived list must never be SMALLER than the list it replaced.

    A derivation that silently shrinks is worse than the hand list: it looks
    automatic while covering less. ``include_in_schema=False``, a router that
    fails to register, or a renamed path would each do it.
    """
    derived = set(_derived_routes())
    missing = [r for r in HISTORICALLY_SWEPT if r not in derived]
    assert not missing, (
        "routes the previous hand-maintained sweep covered are no longer in "
        "the derived list:\n  " + "\n  ".join(missing)
    )


def test_no_public_endpoint_manufactures_a_zero_from_an_outage(dead_db_client):
    spec = app.openapi()
    exercised: Dict[str, Any] = {}
    statuses: Dict[str, int] = {}

    for route in _derived_routes():
        url, query = _concrete_url(route, spec["paths"][route])
        r = dead_db_client.get(url, params=query)
        statuses[route] = r.status_code
        if 200 <= r.status_code < 300:
            try:
                exercised[route] = r.json()
            except ValueError:
                pass

    # Anti-vacuity, in two parts.
    #
    # (1) Something must have returned 2xx, or there is nothing to assert on
    #     and a green result would mean only that every route happened to 500.
    assert exercised, (
        "no route returned 2xx with a dead database — this check proved "
        "nothing. Add a route that degrades gracefully, or fix the fixture."
    )
    # (2) A 422 means the request was rejected before the handler ran, so the
    #     route was NOT exercised against the dead database however green the
    #     result looks. This is not hypothetical: an ``app.dependency_overrides``
    #     entry whose signature was ``(*_a, **_kw)`` turned ``_a``/``_kw`` into
    #     required query params and produced 422 on all 21 Depends(get_db)
    #     routes, while this test still passed.
    unexercised = sorted(r for r, code in statuses.items() if code == 422)
    assert not unexercised, (
        "these routes answered 422, i.e. the request never reached the "
        "handler, so the sweep did not exercise them:\n  "
        + "\n  ".join(unexercised)
    )

    offenders = []
    for route, body in exercised.items():
        for field in _zeroed_money(body):
            offenders.append(f"{route}{field}")
    assert not offenders, (
        "endpoints returning 2xx with a manufactured zero while the data "
        "source is unreachable:\n  " + "\n  ".join(offenders)
    )


def test_positive_control_a_real_figure_still_publishes(client, db_session):
    """The fix must not be "return null always".

    Without this, nulling every field unconditionally would satisfy every
    assertion above. A working database must still yield a figure. Do not
    weaken this test to make the negatives pass.
    """
    from models import DebtTimeline

    db_session.add(
        DebtTimeline(
            year=2031,          # distinctive: `year` is unique across the suite
            external=5680,
            domestic=6820,
            total=12500,
            gdp=17578,
            gdp_ratio=71.1,
        )
    )
    db_session.commit()

    r = client.get("/api/v1/debt/timeline")
    assert r.status_code == 200, r.text
    assert "12500" in r.text or "12,500" in r.text, (
        "a seeded figure did not reach the response — the negative "
        "assertions above are worthless if nothing can publish"
    )


class TestTheFixtureReachesEveryRoute:
    """The sweep above is only as good as the deadness of its database.

    Reported by review on PR #135: the fixture patched ``main.get_db`` and
    installed no ``app.dependency_overrides`` entry, so the 21 GET routes
    declaring ``Depends(get_db)`` — five of them money endpoints — kept
    resolving the real dependency. Six requests per sweep constructed a
    session from ``database.SessionLocal``, whose engine is ``postgresql``
    against a non-local host, so the outage test was talking to the configured
    live database and reporting a pass for routes it never tested.
    """

    def test_no_route_reaches_the_real_session_factory(self, dead_db_client):
        """RED against the pre-fix fixture: ``reached`` held six entries.

        The tripwire RAISES instead of connecting, so this test never opens a
        connection to whatever ``DATABASE_URL`` points at — including when it
        fails.
        """
        import database

        reached: List[str] = []

        def _tripwire(*_a, **_kw):
            reached.append("SessionLocal()")
            raise OperationalError("SELECT 1", {}, Exception("tripwire"))

        with patch.object(database, "SessionLocal", _tripwire):
            spec = app.openapi()
            for route in _derived_routes():
                url, query = _concrete_url(route, spec["paths"][route])
                dead_db_client.get(url, params=query)

        assert not reached, (
            f"{len(reached)} request(s) built a session from the REAL "
            "database.SessionLocal. Those routes are not being exercised "
            "against a dead database, so the sweep's pass does not cover them."
        )


    def test_the_override_adds_no_request_parameters(self, dead_db_client):
        """A dependency override's signature becomes part of the REQUEST.

        RED against the first version of this fix, whose override was
        ``(*_a, **_kw)``: FastAPI turned those into required query params, so
        all 21 ``Depends(get_db)`` routes answered 422 — rejected at
        validation, never reaching the handler — and the sweep stayed green
        over routes it still had not exercised. Swapping one invisible gap for
        another is not a fix.
        """
        from database import get_db as _real_get_db

        override = app.dependency_overrides.get(_real_get_db)
        assert override is not None, "the fixture installed no override"

        import inspect

        params = list(inspect.signature(override).parameters.values())
        assert not params, (
            f"the get_db override declares {[p.name for p in params]}; FastAPI "
            "turns each into a required request field, so every Depends(get_db) "
            "route answers 422 instead of running against the dead database"
        )

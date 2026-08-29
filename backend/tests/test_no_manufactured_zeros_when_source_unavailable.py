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

from main import app

# Keys whose value is a published quantity. A zero here is a claim about the
# world. Counts (``loan_count``, ``total_fetches``, ``count``) are excluded:
# "zero rows recorded" is a legitimate, non-misleading answer for those.
MONEY_KEY = re.compile(
    r"(amount|debt|budget|spent|allocated|revenue|outstanding|ratio|pct|"
    r"percent|flagged|questioned|gdp|_kes|value)$",
    re.I,
)

# Routes exercised with a dead database. Path params get a real-looking value;
# these are the public GET routes that read money out of the data layer.
DEAD_DB_ROUTES: List[str] = [
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
    "/api/v1/counties/001/comprehensive",
    "/api/v1/counties/001/accountability",
    "/api/v1/pending-bills/summary",
]


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

    async def _passthrough(self, request, call_next):  # noqa: ANN001
        return await call_next(request)

    with patch("main.get_db", _raise), patch(
        "middleware.security.RateLimitMiddleware.dispatch", _passthrough
    ), patch("middleware.security.RedisRateLimitMiddleware.dispatch", _passthrough):
        yield TestClient(app, raise_server_exceptions=False)

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


def test_no_public_endpoint_manufactures_a_zero_from_an_outage(dead_db_client):
    exercised: Dict[str, Any] = {}
    for route in DEAD_DB_ROUTES:
        r = dead_db_client.get(route)
        if 200 <= r.status_code < 300:
            try:
                exercised[route] = r.json()
            except ValueError:
                pass

    # Anti-vacuity: if nothing returned 2xx there is nothing to assert on, and
    # a green result would mean only that every route happened to 500.
    assert exercised, (
        "no route returned 2xx with a dead database — this check proved "
        "nothing. Add a route that degrades gracefully, or fix the fixture."
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

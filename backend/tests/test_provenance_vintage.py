"""Tests for provenance-based data vintage (audit §2.9 / §3.7).

Locks in that ``last_updated`` is derived from the source document's real
vintage (publication_date in meta, else fetch_date) and never the request
time.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from provenance import _parse_dt, doc_vintage, resolve_data_vintage

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── _parse_dt ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "value,expected",
    [
        ("2025-04-30", dt.datetime(2025, 4, 30)),
        ("2025-04", dt.datetime(2025, 4, 1)),
        ("2024", dt.datetime(2024, 1, 1)),
        (dt.date(2023, 6, 1), dt.datetime(2023, 6, 1)),
        (None, None),
        ("", None),
        ("not-a-date", None),
    ],
)
def test_parse_dt(value, expected):
    assert _parse_dt(value) == expected


# ── doc_vintage: publication_date preferred, fetch_date fallback ────────
def test_doc_vintage_prefers_publication_date():
    doc = SimpleNamespace(
        meta={"publication_date": "2025-04-30"},
        fetch_date=dt.datetime(2026, 6, 1),
    )
    assert doc_vintage(doc) == dt.datetime(2025, 4, 30)


def test_doc_vintage_falls_back_to_fetch_date():
    doc = SimpleNamespace(meta={}, fetch_date=dt.datetime(2026, 1, 15))
    assert doc_vintage(doc) == dt.datetime(2026, 1, 15)


def test_doc_vintage_none_doc():
    assert doc_vintage(None) is None


# ── resolve_data_vintage: max across docs, honest None ──────────────────
class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._docs


class _FakeDB:
    def __init__(self, docs):
        self._docs = docs

    def query(self, *a, **k):
        return _FakeQuery(self._docs)


def test_resolve_returns_most_recent_vintage():
    docs = [
        SimpleNamespace(id=1, meta={"publication_date": "2025-04-30"}, fetch_date=None),
        SimpleNamespace(id=2, meta={}, fetch_date=dt.datetime(2026, 2, 20)),
    ]
    assert resolve_data_vintage(_FakeDB(docs), [1, 2]) == dt.datetime(2026, 2, 20)


def test_resolve_empty_ids_is_none():
    assert resolve_data_vintage(_FakeDB([]), []) is None
    assert resolve_data_vintage(_FakeDB([]), [None, None]) is None


def test_resolve_no_resolvable_vintage_is_none():
    docs = [SimpleNamespace(id=1, meta={}, fetch_date=None)]
    assert resolve_data_vintage(_FakeDB(docs), [1]) is None


def test_resolve_mixes_aware_and_naive_without_error():
    docs = [
        SimpleNamespace(
            id=1,
            meta={},
            fetch_date=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        ),
        SimpleNamespace(id=2, meta={}, fetch_date=dt.datetime(2026, 1, 1)),
    ]
    # Must not raise on aware/naive comparison; 2026 is the latest.
    assert resolve_data_vintage(_FakeDB(docs), [1, 2]).year == 2026


# ── /debt/national wired to the helper (no request-time last_updated) ───
def test_debt_national_uses_vintage_helper_not_now():
    src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    # The endpoint must resolve vintage from provenance and serve it as
    # last_updated, rather than stamping the response with the request time.
    # (Other endpoints still on datetime.now() are tracked as the rest of
    # the 0.2 freshness work; this asserts the /debt/national fix only.)
    assert "resolve_data_vintage(" in src
    assert '"last_updated": _vintage_iso,' in src


def test_wired_endpoints_use_real_vintage_not_now():
    """audits/federal, budget/national, budget/overview, economic summary
    must report a real source vintage, not the request time."""
    main_src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    econ_src = (BACKEND_DIR / "routers" / "economic.py").read_text(encoding="utf-8")
    # audits/federal + budget/national wired via the inline vintage helper.
    assert "vintage_iso(" in main_src
    # budget/overview serves the already-computed real source timestamp.
    assert "src_updated_at.isoformat() if src_updated_at else None" in main_src
    # economic /summary no longer stamps the request time.
    assert "data_as_of=datetime.now().isoformat()" not in econ_src
    assert "data_as_of=vintage_iso(" in econ_src


# ── The verifier must identify the data point it claims to verify ──────────

def test_budget_line_verification_honours_the_year_parameter(
    client, db_session, seed_country, seed_source_doc
):
    """/verify/budget_lines?year=... must answer about THAT year.

    It ordered by BudgetLine.id and ignored `year` entirely, so it returned an
    arbitrary latest row from a different fiscal period — a verification that
    cannot identify the figure it verifies.
    """
    from datetime import datetime

    from models import BudgetLine, Entity, EntityType, FiscalPeriod

    entity = Entity(
        id=720, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    for pid, label, start, amount in (
        (7200, "FY2023/24", datetime(2023, 7, 1), 3_000_000_000),
        (7201, "FY2024/25", datetime(2024, 7, 1), 5_000_000_000),
    ):
        db_session.add(
            FiscalPeriod(
                id=pid, country_id=seed_country.id, label=label,
                start_date=start, end_date=datetime(start.year + 1, 6, 30),
            )
        )
        db_session.flush()
        db_session.add(
            BudgetLine(
                entity_id=entity.id, period_id=pid, category="Health",
                allocated_amount=amount, actual_spent=amount / 2,
                currency="KES", source_document_id=seed_source_doc.id,
            )
        )
    db_session.commit()

    body = client.get(
        f"/api/v1/provenance/verify/budget_lines?entity_id={entity.id}&year=2023"
    ).json()

    assert "3,000,000,000" in (body.get("value") or ""), (
        f"asked about 2023 and got: {body.get('value')!r}"
    )
    assert "FY2023/24" in (body.get("value") or ""), (
        "the verification must name the period it verified"
    )


def test_a_null_allocation_is_not_reported_as_zero(
    client, db_session, seed_country, seed_source_doc
):
    """allocated_amount is nullable; absence must not render as KES 0."""
    from datetime import datetime

    from models import BudgetLine, Entity, EntityType, FiscalPeriod

    entity = Entity(
        id=721, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Kwale County", slug="kwale-county",
    )
    period = FiscalPeriod(
        id=7210, country_id=seed_country.id, label="FY2024/25",
        start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    db_session.add(
        BudgetLine(
            entity_id=entity.id, period_id=period.id, category="Health",
            allocated_amount=None, actual_spent=None, currency="KES",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()

    body = client.get(
        f"/api/v1/provenance/verify/budget_lines?entity_id={entity.id}"
    ).json()

    assert body.get("value") is None, (
        f"an absent allocation was published as a figure: {body.get('value')!r}"
    )
    assert "KES 0" not in str(body.get("value")), body
    assert "no allocation recorded" in (body.get("reason") or "").lower(), body


def test_debt_timeline_verification_honours_the_year_parameter(
    client, db_session
):
    from models import DebtTimeline

    db_session.add_all([
        DebtTimeline(year=2019, external=2_800_000_000_000,
                     domestic=3_000_000_000_000, total=5_800_000_000_000),
        DebtTimeline(year=2025, external=5_400_000_000_000,
                     domestic=6_200_000_000_000, total=11_600_000_000_000),
    ])
    db_session.commit()

    body = client.get("/api/v1/provenance/verify/debt_timeline?year=2019").json()
    assert "year 2019" in (body.get("value") or ""), (
        f"asked about 2019 and got: {body.get('value')!r}"
    )

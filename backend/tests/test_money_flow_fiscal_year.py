"""Fiscal-year handling on the money-flow endpoints (credibility audit F3/F36).

Two defects in one parser:

1. The pattern was anchored right after the second year group, so any label
   carrying a Controller of Budget PERIOD QUALIFIER — "FY2025/26 9M",
   "FY2025/26 H1" — failed to parse. GET /audits/fiscal-years offers both, and
   the Follow the Money picker renders both, so the page showed "No data yet"
   for periods that exist in the database. That is a broken join presenting as
   a missing dataset.

2. A value that is not a fiscal year at all — a bare calendar year, "2024" —
   also produced an empty candidate list, and the endpoint answered with a
   well-formed object whose every stage was null and data_unavailable: true.
   Indistinguishable from "nothing published". This is exactly what sent the
   credibility audit hunting for an ETL gap that was really a wrong parameter
   format; the seed brief it produced asserted the domain was empty at the API.

Both are pinned here, in both directions.
"""

from __future__ import annotations

import pytest
from routers.money_flow import UnparseableFiscalYear, _normalize_fiscal_year


# ── Qualified labels must parse ───────────────────────────────────────────

@pytest.mark.parametrize(
    "label,expected_exact",
    [
        ("FY2025/26 9M", "FY2025/26 9M"),
        ("FY2025/26 H1", "FY2025/26 H1"),
        ("2025/26 9M", "FY2025/26 9M"),
        ("fy2025/26 h1", "FY2025/26 H1"),
    ],
)
def test_period_qualified_labels_resolve(label, expected_exact):
    """These are the labels /audits/fiscal-years actually returns."""
    candidates = _normalize_fiscal_year(label)
    assert expected_exact in candidates, (
        f"{label!r} must produce the DB label {expected_exact!r}; got {candidates}"
    )


def test_a_qualified_request_does_not_match_the_full_year():
    """Asking for the 9-month report must not return the full-year period."""
    candidates = _normalize_fiscal_year("FY2025/26 9M")
    assert "FY2025/26" not in candidates


def test_an_unqualified_request_does_not_match_a_part_year():
    """And asking for the full year must not silently return the 9-month one —
    they are different periods with different totals."""
    candidates = _normalize_fiscal_year("FY2025/26")
    assert "FY2025/26" in candidates
    assert not any(c.endswith(("9M", "H1", "H2", "Q1")) for c in candidates)


# ── The formats that already worked must keep working ────────────────────

@pytest.mark.parametrize(
    "label",
    ["2023/24", "2023/2024", "FY2023/24", "FY 2023/24", "2023-24", "23/24"],
)
def test_unqualified_variants_still_resolve(label):
    assert "FY2023/24" in _normalize_fiscal_year(label)


# ── Unparseable input must raise, not answer ─────────────────────────────

@pytest.mark.parametrize("bad", ["2024", "2025", "", "   ", "next year", "FY", "abc/def"])
def test_input_that_is_not_a_fiscal_year_raises(bad):
    with pytest.raises(UnparseableFiscalYear):
        _normalize_fiscal_year(bad)


def test_the_calendar_year_that_misled_the_audit_raises():
    """`?year=2024` returned a well-formed all-null response for every year,
    which read as 'this domain has no data'. It must now be refused."""
    with pytest.raises(UnparseableFiscalYear) as exc:
        _normalize_fiscal_year("2024")
    assert "fiscal-year label" in str(exc.value)


# ── End to end through the API ───────────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/audit/money-flow/national",
        "/api/v1/money-flow/all-counties",
    ],
)
def test_endpoints_refuse_a_calendar_year_with_400(client, path):
    resp = client.get(f"{path}?year=2024")
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_fiscal_year"
    assert "FY2025/26 9M" in detail["hint"], "the hint must show the qualified form"


@pytest.fixture()
def one_county(db_session, seed_country):
    """The national endpoint 404s with no counties at all, so give it one."""
    from models import Entity, EntityType

    e = Entity(
        id=901,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Test County",
        slug="test-county",
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_a_valid_but_absent_period_says_which_problem_it_is(client, one_county):
    resp = client.get("/api/v1/audit/money-flow/national?year=FY1999/00")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unavailable_reason"] == "fiscal_period_not_found"
    assert all(s["amount"] is None for s in body["stages"])


# ── The qualifier must be a real sub-period marker, not any trailing text ──

@pytest.mark.parametrize(
    "label",
    [
        "FY2025/26 garbage",
        "FY2025/26 H3",
        "FY2025/26 Q5",
        "FY2025/26 nonsense 9M",
        "FY2025/26 9",
        "2024/25 -- drop table",
    ],
)
def test_junk_after_the_year_is_rejected_not_treated_as_a_qualifier(label):
    """A trailing `(.*)` made every suffix a valid qualifier.

    Such input then reported `fiscal_period_not_found` — indistinguishable from
    a period that genuinely has nothing published — instead of the 400 this
    parser exists to raise.
    """
    with pytest.raises(UnparseableFiscalYear):
        _normalize_fiscal_year(label)


@pytest.mark.parametrize(
    "label,expected_qualifier",
    [("FY2025/26 H1", "H1"), ("FY2024/25 Q3", "Q3"), ("FY2025/26 9M", "9M")],
)
def test_canonical_qualifiers_still_parse(label, expected_qualifier):
    """Positive control: the markers seeding/utils.py emits must still work."""
    candidates = _normalize_fiscal_year(label)
    assert any(expected_qualifier in c for c in candidates), candidates

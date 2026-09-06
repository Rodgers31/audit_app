"""Revenue-by-source rows must carry their own basis to the reader.

Six tax heads render on /budget as equals under one blanket credit reading
"Source: KRA Annual Performance". Two of the six are not KRA-published figures
at all:

* the whole of FY 2022/23 is back-computed — each head divided out of the
  FY 2023/24 release's growth rate ("Derived: FY 2023/24 Customs 791.368B grew
  4.9%, implies prior year ~754.4B"), and it is the leftmost bar of every
  sparkline on the page;
* ``Other Tax Revenue`` is a subtraction in every year — the exchequer total
  less the identified heads — and renders as a card at KES 181B, 7.8% of the
  displayed mix.

The fixture rows say so in their own ``notes``. The API did not carry them: the
union of per-source keys served by /budget/enhanced was
``amount, category, performance_pct, revenue_type, share_pct, target,
yoy_growth_pct`` and nothing else, so the honesty stopped at the database and
the blanket credit was the only provenance claim a reader ever saw.

``basis`` is declared per row rather than sniffed out of the note prose,
because the KRA overlay rewrites amounts without touching notes — a promoted
row would otherwise keep whatever the fixture last said about a number the
overlay has since replaced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from models import RevenueBySource
from seeding.domains.revenue_by_source.fetcher import _overlay_kra_breakdown
from seeding.domains.revenue_by_source.parser import parse_revenue_payload

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "seeding"
    / "real_data"
    / "revenue_by_source.json"
)

# The four bases a row may declare. Anything else is a typo, and a typo must
# not quietly read as "published".
VALID_BASES = {"published", "derived", "residual", "projected"}


# ── The fixture declares a basis, and it agrees with its own note ──────────


def _fixture_rows():
    return json.loads(FIXTURE.read_text())


def test_every_tax_head_row_declares_a_basis():
    """No breakdown row may reach the seeder without saying what it is."""
    missing = [
        f"{r['fiscal_year']}/{r['revenue_type']}"
        for r in _fixture_rows()
        if r.get("category", "tax") == "tax" and not r.get("basis")
    ]
    assert missing == [], f"rows with no declared basis: {missing}"


def test_declared_bases_are_from_the_known_set():
    bad = [
        (r["fiscal_year"], r["revenue_type"], r.get("basis"))
        for r in _fixture_rows()
        if r.get("basis") is not None and r["basis"] not in VALID_BASES
    ]
    assert bad == [], f"unrecognised basis values: {bad}"


@pytest.mark.parametrize(
    "prefix,expected",
    [("Derived:", "derived"), ("Residual:", "residual"), ("Projected:", "projected")],
)
def test_basis_agrees_with_the_note_that_describes_it(prefix, expected):
    """The note prose and the declared basis cannot drift apart.

    The notes were the only record of these derivations before this change;
    they stay the human explanation, and this pins them to the machine-readable
    field so a future edit cannot relabel one without the other.
    """
    disagreeing = [
        (r["fiscal_year"], r["revenue_type"], r.get("basis"))
        for r in _fixture_rows()
        if (r.get("notes") or "").startswith(prefix) and r.get("basis") != expected
    ]
    assert disagreeing == [], f"{prefix} rows not marked {expected}: {disagreeing}"


def test_fy_2022_23_is_derived_and_not_credited_as_published():
    """The year that is entirely back-computed says so on every one of its rows."""
    rows = [r for r in _fixture_rows() if r["fiscal_year"] == "FY 2022/23"]
    assert rows, "FY 2022/23 rows vanished from the fixture"
    assert all(r["basis"] in {"derived", "residual"} for r in rows), [
        (r["revenue_type"], r.get("basis")) for r in rows
    ]
    assert not any(r["basis"] == "published" for r in rows)


def test_other_tax_revenue_is_never_published():
    """The residual head is a subtraction in every year, never a KRA figure.

    In the three actual years it is the exchequer total less the identified
    heads; in FY 2025/26 it is the same subtraction against a *target*, so it
    is a projection rather than a residual of anything collected. Neither is a
    published line, and that is the property the page depends on.
    """
    rows = [r for r in _fixture_rows() if r["revenue_type"] == "Other Tax Revenue"]
    assert len(rows) >= 3
    assert all(r["basis"] in {"residual", "projected"} for r in rows), [
        (r["fiscal_year"], r.get("basis")) for r in rows
    ]
    actuals = [r for r in rows if r.get("amount_billion_kes") is not None]
    assert actuals, "no Other Tax Revenue row carries an actual amount"
    assert all(r["basis"] == "residual" for r in actuals), [
        (r["fiscal_year"], r.get("basis")) for r in actuals
    ]


# ── The parser carries it through ─────────────────────────────────────────


def test_parser_carries_basis_into_metadata():
    records = parse_revenue_payload(
        [
            {
                "fiscal_year": "FY 2022/23",
                "revenue_type": "Customs & Import Duty",
                "category": "tax",
                "amount_billion_kes": 754.4,
                "basis": "derived",
                "notes": "Derived: FY 2023/24 Customs 791.368B grew 4.9%",
            }
        ]
    )
    assert len(records) == 1
    assert records[0].metadata["basis"] == "derived"
    assert records[0].metadata["notes"].startswith("Derived:")


def test_parser_records_no_basis_rather_than_defaulting_to_published():
    """An undeclared basis is absence, not a claim.

    Defaulting the missing case to "published" would manufacture a provenance
    claim out of a fixture omission — the same shape as publishing a zero for a
    figure nobody measured.
    """
    records = parse_revenue_payload(
        [
            {
                "fiscal_year": "FY 2019/20",
                "revenue_type": "Total Government Revenue",
                "category": "tax",
                "amount_billion_kes": 1600.0,
            }
        ]
    )
    assert records[0].metadata.get("basis") is None


def test_parser_drops_an_unrecognised_basis():
    records = parse_revenue_payload(
        [
            {
                "fiscal_year": "FY 2022/23",
                "revenue_type": "PAYE",
                "category": "tax",
                "amount_billion_kes": 495.2,
                "basis": "vibes",
            }
        ]
    )
    assert records[0].metadata.get("basis") is None


# ── The live KRA overlay re-bases the rows it replaces ─────────────────────


def test_kra_overlay_marks_promoted_rows_as_published():
    """A promoted amount is a KRA-published figure, so its basis must move.

    The overlay rewrites ``amount_billion_kes`` in place and leaves ``notes``
    alone. Without this, a promoted FY 2025/26 row would carry a real collected
    figure under basis "projected", and the page would caption a published
    number as a projection.
    """
    payload = [
        {
            "fiscal_year": "FY 2024/25",
            "revenue_type": rt,
            "category": "tax",
            "amount_billion_kes": amt,
            "basis": "projected",
            "notes": "Projected: from the MTRS target",
        }
        for rt, amt in [
            ("PAYE", 561.0),
            ("Corporation Tax", 304.8),
            ("VAT", 327.3),
            ("Excise Duty", 69.4),
            ("Customs & Import Duty", 879.3),
        ]
    ]
    by_type = {
        "PAYE": 560.9,
        "Corporation Tax": 304.8,
        "VAT": 327.3,
        "Excise Duty": 69.4,
        "Customs & Import Duty": 879.3,
    }

    out, status = _overlay_kra_breakdown(payload, by_type, "FY 2024/25")

    assert status.startswith("promoted:"), status
    assert all(r["basis"] == "published" for r in out), [
        (r["revenue_type"], r.get("basis")) for r in out
    ]


def test_kra_overlay_leaves_the_basis_of_rows_it_did_not_touch():
    """A residual is still a residual after its neighbours are refreshed.

    KRA publishes the five named heads; the residual is this project's own
    subtraction and has no counterpart in the release, so the overlay never
    matches it and must not re-base it.
    """
    payload = [
        {
            "fiscal_year": "FY 2024/25",
            "revenue_type": rt,
            "category": "tax",
            "amount_billion_kes": amt,
            "basis": "derived",
        }
        for rt, amt in [
            ("PAYE", 561.0),
            ("Corporation Tax", 304.8),
            ("VAT", 327.3),
            ("Excise Duty", 69.4),
            ("Customs & Import Duty", 879.3),
        ]
    ] + [
        {
            "fiscal_year": "FY 2024/25",
            "revenue_type": "Other Tax Revenue",
            "category": "tax",
            "amount_billion_kes": 181.2,
            "basis": "residual",
        }
    ]
    by_type = {
        "PAYE": 561.0,
        "Corporation Tax": 304.8,
        "VAT": 327.3,
        "Excise Duty": 69.4,
        "Customs & Import Duty": 879.3,
    }

    out, status = _overlay_kra_breakdown(payload, by_type, "FY 2024/25")

    assert status == "promoted:5/FY 2024/25", status
    by_name = {r["revenue_type"]: r for r in out}
    assert by_name["PAYE"]["basis"] == "published"
    assert by_name["Other Tax Revenue"]["basis"] == "residual"


def test_a_rejected_overlay_does_not_re_base_anything():
    """Safe-by-construction: a parse that fails the gate changes nothing."""
    payload = [
        {
            "fiscal_year": "FY 2022/23",
            "revenue_type": "PAYE",
            "category": "tax",
            "amount_billion_kes": 495.2,
            "basis": "derived",
        }
    ]
    out, status = _overlay_kra_breakdown(payload, {}, "FY 2022/23")
    assert status == "no_live_value"
    assert out[0]["basis"] == "derived"


# ── The API serves it ─────────────────────────────────────────────────────


@pytest.fixture
def seeded_revenue(db_session):
    db_session.add_all(
        [
            RevenueBySource(
                fiscal_year="FY 2022/23",
                revenue_type="Customs & Import Duty",
                category="tax",
                amount_billion_kes=754.4,
                share_of_total_pct=37.2,
                meta={
                    "basis": "derived",
                    "notes": (
                        "Derived: FY 2023/24 Customs 791.368B grew 4.9%, "
                        "implies prior year ~754.4B"
                    ),
                },
            ),
            RevenueBySource(
                fiscal_year="FY 2024/25",
                revenue_type="PAYE",
                category="tax",
                amount_billion_kes=561.0,
                share_of_total_pct=24.1,
                meta={
                    "basis": "published",
                    "notes": "KRA Annual Performance FY 2024/25: PAYE KES 560.963B",
                },
            ),
            RevenueBySource(
                fiscal_year="FY 2024/25",
                revenue_type="Other Tax Revenue",
                category="tax",
                amount_billion_kes=181.2,
                share_of_total_pct=7.8,
                meta={
                    "basis": "residual",
                    "notes": (
                        "Residual: Exchequer 2323B minus identified tax heads."
                    ),
                },
            ),
        ]
    )
    db_session.commit()


def _sources(payload, fy):
    for block in payload["revenue_by_source"]:
        if block["fiscal_year"] == fy:
            return {s["revenue_type"]: s for s in block["sources"]}
    raise AssertionError(f"{fy} missing from response")


def test_enhanced_serves_basis_per_revenue_row(client, seeded_revenue):
    body = client.get("/api/v1/budget/enhanced").json()

    derived = _sources(body, "FY 2022/23")["Customs & Import Duty"]
    assert derived["basis"] == "derived"
    assert derived["basis_note"].startswith("Derived:")

    latest = _sources(body, "FY 2024/25")
    assert latest["PAYE"]["basis"] == "published"
    assert latest["Other Tax Revenue"]["basis"] == "residual"
    assert "Residual:" in latest["Other Tax Revenue"]["basis_note"]


def test_enhanced_reports_no_basis_rather_than_guessing_one(client, db_session):
    """A row with no recorded provenance is served as having none."""
    db_session.add(
        RevenueBySource(
            fiscal_year="FY 2019/20",
            revenue_type="Total Government Revenue",
            category="tax",
            amount_billion_kes=1600.0,
            meta={},
        )
    )
    db_session.commit()

    row = _sources(client.get("/api/v1/budget/enhanced").json(), "FY 2019/20")[
        "Total Government Revenue"
    ]
    assert row["basis"] is None
    assert row["basis_note"] is None


def test_enhanced_survives_a_null_metadata_column(client, db_session):
    """``metadata`` is nullable in the table; reading it must not 500."""
    db_session.add(
        RevenueBySource(
            fiscal_year="FY 2018/19",
            revenue_type="Total Tax Revenue",
            category="tax",
            amount_billion_kes=1500.0,
            meta=None,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/budget/enhanced")
    assert resp.status_code == 200
    row = _sources(resp.json(), "FY 2018/19")["Total Tax Revenue"]
    assert row["basis"] is None

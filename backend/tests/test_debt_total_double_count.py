"""KSh 300Bn of Treasury bonds were in the published total twice.

The register's ``domestic_bonds`` category carried CBK's inclusive Treasury
Bonds aggregate AND a separate "Domestic Infrastructure & Green Bonds" row that
is a subset of it. Production published 5,879.0Bn where CBK publishes 5,579.0.

The subsumption was already known — ``fetcher._DOMESTIC_BOND_MARKERS`` carries
a comment describing it, and ``_published_bond_stock_kes`` already excludes the
subset. But it excluded it from the coverage-gate DENOMINATOR only. The row
stayed in the loans payload, went into the loans table, and went on being
summed into the headline.

These tests are about the published TOTAL, which is where the money was.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from seeding.config import SeedingSettings
from seeding.domains.national_debt import fetcher as nd_fetcher

#: CBK Statistical Bulletin Table 4.1.4, Treasury Bonds column, the vintage the
#: register carries in production. Inclusive of infrastructure and green bonds.
CBK_TREASURY_BONDS_KES = 5_578_982_400_000

#: What production published instead: the line above plus the fixture's
#: standalone infrastructure/green bond row.
PUBLISHED_WITH_DOUBLE_COUNT_KES = 5_878_982_400_000

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "seeding"
    / "real_data"
    / "national_debt.json"
)


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        live_pdf_fetch_enabled=True,
    )
    s.ensure_directories()
    return s


def _shipped_payload() -> Dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _cbk_bond_overlay() -> List[Dict[str, Any]]:
    """What the live CBK bulletin overlay writes for the Treasury Bonds column."""
    return [
        {
            "entity_name": "National Government",
            "entity_type": "national",
            "lender": "Domestic Treasury Bonds",
            "debt_category": "domestic_bonds",
            "principal": f"{CBK_TREASURY_BONDS_KES}.00",
            "outstanding": f"{CBK_TREASURY_BONDS_KES}.00",
            "interest_rate": None,
            "issue_date": "2025-07-01",
            "maturity_date": None,
            "currency": "KES",
            "notes": "CBK Statistical Bulletin Table 4.1.4 (month-end 2025-12-01)",
        }
    ]


def _domestic_bonds(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        loan
        for loan in payload["loans"]
        if loan.get("debt_category") == "domestic_bonds"
    ]


def _sum_kes(loans: List[Dict[str, Any]]) -> Decimal:
    return sum(
        (Decimal(str(l.get("outstanding") or l.get("principal") or 0)) for l in loans),
        Decimal(0),
    )


# ── The defect: the published bond stock ─────────────────────────────────


def test_the_bond_category_publishes_cbks_figure_not_cbks_figure_plus_a_subset(
    settings,
):
    """The whole finding, measured on the number the site publishes.

    Run the real fetcher over the shipped fixture with the CBK bulletin overlay
    that production gets. The ``domestic_bonds`` total must be CBK's published
    Treasury Bonds line and nothing more.
    """
    with (
        patch.object(
            nd_fetcher, "load_json_resource", return_value=_shipped_payload()
        ),
        patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=[]),
        patch.object(nd_fetcher, "fetch_external_creditors", return_value=None),
        patch.object(
            nd_fetcher,
            "fetch_domestic_debt_from_cbk_bulletin",
            return_value=_cbk_bond_overlay(),
        ),
        patch.object(
            nd_fetcher, "fetch_bond_register", side_effect=RuntimeError("not under test")
        ),
    ):
        payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)

    total = _sum_kes(_domestic_bonds(payload))
    assert total == Decimal(CBK_TREASURY_BONDS_KES), (
        "domestic_bonds must be CBK's Treasury Bonds line; got "
        f"{total / Decimal(1e9):,.1f}Bn against CBK's "
        f"{CBK_TREASURY_BONDS_KES / 1e9:,.1f}Bn"
    )
    assert total != Decimal(PUBLISHED_WITH_DOUBLE_COUNT_KES), (
        "the 300Bn infrastructure-bond double count is back in the headline"
    )


def test_the_bond_category_holds_no_aggregate_and_its_own_subset(settings):
    """The invariant, stated directly: one inclusive aggregate, no subsets."""
    with (
        patch.object(
            nd_fetcher, "load_json_resource", return_value=_shipped_payload()
        ),
        patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=[]),
        patch.object(nd_fetcher, "fetch_external_creditors", return_value=None),
        patch.object(
            nd_fetcher,
            "fetch_domestic_debt_from_cbk_bulletin",
            return_value=_cbk_bond_overlay(),
        ),
        patch.object(
            nd_fetcher, "fetch_bond_register", side_effect=RuntimeError("not under test")
        ),
    ):
        payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)

    lenders = [(l.get("lender") or "").lower() for l in _domestic_bonds(payload)]
    aggregate = [l for l in lenders if "treasury bond" in l]
    subsets = [
        l
        for l in lenders
        if any(m in l for m in ("infrastructure", "green bond"))
    ]
    assert aggregate, "the inclusive Treasury-bonds aggregate must survive"
    assert not subsets, (
        "a row CBK's Treasury Bonds column already counts is in the register "
        f"beside it: {subsets}"
    )


def test_the_shipped_fixture_does_not_carry_the_subset_row():
    """The fixture itself, independent of any overlay.

    CBK Table 4.1.4 publishes one Treasury Bonds column and infrastructure and
    green bonds are inside it — the fixture's own Treasury-bonds note says so.
    There is no published figure that would make that row exclusive, so the
    subset is what has to go.
    """
    loans = _shipped_payload()["loans"]
    bonds = [l for l in loans if l.get("debt_category") == "domestic_bonds"]
    subsets = [
        l["lender"]
        for l in bonds
        if any(
            m in l["lender"].lower() for m in ("infrastructure", "green bond")
        )
    ]
    assert not subsets, f"national_debt.json still ships {subsets}"
    assert len(bonds) == 1, f"one bond row expected, got {[l['lender'] for l in bonds]}"


# ── The guard: it holds when something re-adds the row ────────────────────


def test_a_subset_row_added_back_by_an_overlay_is_dropped_loudly(caplog):
    """Deleting the fixture row fixes today. The guard is what stops it
    returning through a re-published fixture or a new overlay."""
    payload = {
        "metadata": {},
        "loans": [
            {
                "lender": "Domestic Treasury Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": CBK_TREASURY_BONDS_KES,
            },
            {
                "lender": "Domestic Infrastructure & Green Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": 300_000_000_000,
            },
            {
                "lender": "Domestic Treasury Bills (91-day, 182-day, 364-day)",
                "debt_category": "domestic_bills",
                "outstanding": 1_090_000_000_000,
            },
        ],
    }
    with caplog.at_level("WARNING"):
        result = nd_fetcher._drop_subsumed_rows(payload)

    lenders = [l["lender"] for l in result["loans"]]
    assert "Domestic Infrastructure & Green Bonds" not in lenders
    assert "Domestic Treasury Bonds" in lenders
    assert "Domestic Treasury Bills (91-day, 182-day, 364-day)" in lenders

    dropped = result["metadata"]["subsumed_rows_dropped"]
    assert len(dropped) == 1
    assert dropped[0]["amount_kes"] == 300_000_000_000
    assert dropped[0]["already_counted_by"] == "Domestic Treasury Bonds"
    assert dropped[0]["reason"], "a drop must say which classification says so"
    assert result["metadata"]["subsumed_rows_dropped_kes"] == 300_000_000_000
    assert any(
        "already counts it" in r.getMessage() for r in caplog.records
    ), "the drop must be visible in the log, not silent"


def test_the_amount_dropped_is_the_gap_between_the_two_headlines():
    """5,879.0Bn published, 5,579.0Bn from CBK. The difference is the row."""
    payload = {
        "loans": [
            {
                "lender": "Domestic Treasury Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": CBK_TREASURY_BONDS_KES,
            },
            {
                "lender": "Domestic Infrastructure & Green Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": 300_000_000_000,
            },
        ]
    }
    before = _sum_kes(payload["loans"])
    after = _sum_kes(nd_fetcher._drop_subsumed_rows(payload)["loans"])
    assert before == Decimal(PUBLISHED_WITH_DOUBLE_COUNT_KES)
    assert after == Decimal(CBK_TREASURY_BONDS_KES)
    assert before - after == Decimal(300_000_000_000)


def test_a_subset_with_no_aggregate_beside_it_is_kept():
    """Dropping it then would understate, not correct. Nothing counts it twice
    when it is the only bond row there is."""
    payload = {
        "loans": [
            {
                "lender": "Domestic Infrastructure & Green Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": 300_000_000_000,
            }
        ]
    }
    result = nd_fetcher._drop_subsumed_rows(payload)
    assert [l["lender"] for l in result["loans"]] == [
        "Domestic Infrastructure & Green Bonds"
    ]
    assert "subsumed_rows_dropped" not in result.get("metadata", {})


def test_the_rule_is_confined_to_its_own_category():
    """Infrastructure bonds are inside CBK's DOMESTIC Treasury Bonds column.
    A row in another category is not covered by that classification."""
    payload = {
        "loans": [
            {
                "lender": "Domestic Treasury Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": CBK_TREASURY_BONDS_KES,
            },
            {
                "lender": "Infrastructure bonds (external issue)",
                "debt_category": "external_commercial",
                "outstanding": 50_000_000_000,
            },
        ]
    }
    lenders = [l["lender"] for l in nd_fetcher._drop_subsumed_rows(payload)["loans"]]
    assert "Infrastructure bonds (external issue)" in lenders


def test_an_untouched_payload_is_returned_unchanged():
    payload = {
        "metadata": {"source": "x"},
        "loans": [
            {
                "lender": "Domestic Treasury Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": CBK_TREASURY_BONDS_KES,
            }
        ],
    }
    result = nd_fetcher._drop_subsumed_rows(payload)
    assert result is payload
    assert "subsumed_rows_dropped" not in result["metadata"]

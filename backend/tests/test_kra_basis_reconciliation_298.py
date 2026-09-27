"""Independent regression for #298: department collections are not tax heads.

The real dashboard is linked from kra.go.ke. Its Customs amount is departmental
revenue, which includes agency levies. KRA's Customs press release of 17 July
2025 includes Road Maintenance Levy in that departmental collection; audited
FY2024/25 accounts PDF page 80 (printed page 15), note 6(a), identifies RML as
agency revenue. With no Customs-to-Exchequer allocation in the source, subtracting
the department total from Exchequer revenue cannot yield Other Tax Revenue.
"""

import gzip
from decimal import Decimal
from pathlib import Path

from seeding.domains.revenue_by_source.fetcher import _overlay_kra_release
from seeding.domains.revenue_by_source.kra_discovery import (
    parse_dashboard_bundle,
    residual_bn,
)


def _real_release():
    fixture = Path(__file__).parent / "fixtures/kra/fy2025_26_dashboard_bundle.js.gz"
    with gzip.open(fixture, "rt") as stream:
        return parse_dashboard_bundle(
            stream.read(),
            url="https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026",
            data_url="https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js",
        )


def test_published_dashboard_collections_remain_available():
    """Positive control: absent allocation must not erase actual source figures."""
    release = _real_release()
    assert release.fiscal_year == "FY 2025/26"
    assert release.heads["PAYE"].amount_bn == Decimal("598.807")
    assert release.heads["VAT"].amount_bn == Decimal("355.255")
    assert release.heads["Corporation Tax"].amount_bn == Decimal("347.066")
    assert release.heads["Excise Duty"].amount_bn == Decimal("61.845")
    assert release.heads["Customs & Import Duty"].amount_bn == Decimal("988.780")


def test_departmental_customs_cannot_generate_exchequer_tax_residual():
    assert residual_bn(_real_release()) is None


def test_overlay_withdraws_existing_mixed_basis_residual():
    rows, _ = _overlay_kra_release(
        [{
            "fiscal_year": "FY 2025/26",
            "revenue_type": "Other Tax Revenue",
            "category": "tax",
            "basis": "residual",
            "amount_billion_kes": 216.25,
            "share_of_total_pct": 8.4,
        }],
        _real_release(),
    )
    residual = next(row for row in rows if row["revenue_type"] == "Other Tax Revenue")
    assert residual["amount_billion_kes"] is None
    assert residual["share_of_total_pct"] is None


def test_overlay_does_not_claim_exchequer_shares_for_incompatible_bases():
    rows, _ = _overlay_kra_release([], _real_release())
    assert all(row.get("share_of_total_pct") is None for row in rows)

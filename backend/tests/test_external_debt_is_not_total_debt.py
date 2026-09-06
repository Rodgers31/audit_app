"""External-only World Bank series were published as national totals.

The nightly quarantined one row and it read like a band that was set too high::

    Quarantined FY 2021/22: debt_service_cost=393B is outside the plausible
    [400, 4,000]B band.

393B is not a correct figure being suppressed. It is a DIFFERENT MEASURE
wearing the right field's name. ``_merge_worldbank_data`` builds fiscal years
that are absent from the fixture out of two World Bank indicators:

    DT.TDS.DECT.CD  Debt service on EXTERNAL debt, total (TDS, current US$)
    DT.DOD.DECT.CD  EXTERNAL debt stocks, total (DOD, current US$)

and writes them to ``debt_service_cost`` and ``actual_debt``. The "total" in
those indicator names means total EXTERNAL — long-term plus IMF plus
short-term — not total including domestic. The local aliases
(``total_debt_service_usd``, ``external_debt_stocks_usd``) lost that.

``debt_service_cost`` is defined by the dataset itself as::

    "Debt service follows the Treasury APDMR definition: interest payments
     PLUS principal redemptions (domestic + external)."

The fixture's own FY2022/23 on that definition is 1,162B. A 393 -> 1,162 jump
in one year is not a debt-service trajectory, it is a change of measure. Kenya's
domestic debt service is the larger half, and it is missing from every one of
these rows.

``actual_debt`` is the figure the repealed KES 10T ceiling was measured
against — total public debt — so external-only stock is the same category
error a second time.

The quarantine caught FY2021/22 only because it is the first year of the band
era, and a quarantined row is never written. Every EARLIER year takes the
``historical`` exemption in trust_guards, skips the band, and IS written — those
rows hold an external-only figure in a total's column today. The comment
justifying that exemption cites "FY2017/18 debt_service_cost 363B" and
"FY2020/21 318B" as "real, curated values that the band FLOORS reject", but the
fixture holds no year before FY2022/23, so both came from this same
external-only path. The exemption was calibrated on the contamination it hid.

To be exact about reach: these rows are NOT on the site. ``/api/v1/fiscal/
summary`` keeps only rows with 3 of its 4 headline fields and a World Bank stub
has 2, so they are dropped before any page sees them. That filter tests
SPARSENESS, not whether a figure means what its column says — it would pass a
stub that gained a third field. This is a fact-table defect with a second gate
happening to stand in front of it, not a published-figure defect.

The fix is not a wider band. It is to stop publishing a figure the source does
not support: the field is omitted, exactly as the USD/KES rate branch three
lines above already does when it cannot convert honestly.
"""

import json

import pytest

from seeding.domains.fiscal_summary.fetcher import (
    _WB_INDICATORS,
    _merge_worldbank_data,
)

# 2022 -> FY 2021/22, the year the nightly quarantined.
WB = {
    "2022": {
        "total_debt_service_usd": 3.45e9,
        "external_debt_stocks_usd": 3.7e10,
        "government_expenditure_lcu": 3.0e12,
        "government_revenue_lcu": 2.0e12,
    }
}


@pytest.fixture()
def merged():
    payload = {
        "fiscal_years": [{"fiscal_year": "FY 2022/23", "debt_service_cost": 1162}]
    }
    out = _merge_worldbank_data(payload, WB)
    return next(fy for fy in out["fiscal_years"] if fy["fiscal_year"] == "FY 2021/22")


class TestTheMeasureIsNotWrittenUnderTheWrongName:
    def test_external_debt_service_is_not_published_as_debt_service_cost(self, merged):
        assert merged.get("debt_service_cost") is None, (
            "DT.TDS.DECT.CD is external-only; debt_service_cost is defined as "
            "interest + redemptions, domestic AND external"
        )

    def test_external_debt_stock_is_not_published_as_actual_debt(self, merged):
        assert merged.get("actual_debt") is None, (
            "DT.DOD.DECT.CD is external-only; actual_debt is the total public "
            "debt the ceiling was measured against"
        )

    def test_a_zero_is_not_substituted_for_the_absent_figure(self, merged):
        """Absence, never a stand-in number."""
        for field in ("debt_service_cost", "actual_debt"):
            assert merged.get(field) in (None,), f"{field} = {merged.get(field)!r}"


class TestTheLegitimateSeriesStillArrive:
    """The branch is not deleted — the government-finance series are real."""

    def test_expenditure_still_maps_to_the_budget(self, merged):
        assert merged["appropriated_budget"] == pytest.approx(3000.0, rel=1e-3)

    def test_revenue_still_maps(self, merged):
        assert merged["total_revenue"] == pytest.approx(2000.0, rel=1e-3)

    def test_the_year_is_still_created(self, merged):
        assert merged["fiscal_year"] == "FY 2021/22"
        assert merged["_source"] == "world_bank_api"


class TestTheIndicatorNamesSayWhatTheyAre:
    def test_the_external_service_alias_no_longer_claims_to_be_total(self):
        """`total_debt_service_usd` is what made the category error readable
        as correct. The name has to carry the scope."""
        alias = _WB_INDICATORS["DT.TDS.DECT.CD"]
        assert "external" in alias, alias

    def test_the_stock_alias_names_its_scope(self):
        assert "external" in _WB_INDICATORS["DT.DOD.DECT.CD"]


class TestTheDatasetDefinitionIsUnchanged:
    def test_debt_service_is_still_declared_as_domestic_plus_external(self):
        """If this ever changes, the whole argument above has to be re-made."""
        import bootstrap  # noqa: F401 - keeps the path resolution consistent
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "seeding"
            / "real_data"
            / "fiscal_summary.json"
        )
        description = json.loads(path.read_text())["metadata"]["description"]
        assert "domestic + external" in description

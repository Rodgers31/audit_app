"""A loan's rate and annual cost come from a publisher, or are absent with a reason.

Issue #235. Measured on production 2026-09-26 (`/api/v1/debt/loans`):

* 45 of 48 register rows published ``0.00%`` and ``KES 0`` a year. The IDS and
  CBK overlays carry no rate; the writer created each row with
  ``interest_rate or Decimal("0")``.
* The domestic rows kept the April-2025 fixture's rates (14.5% bonds, 16%
  bills) forever: the writer only overwrote a rate the live record had, and the
  live record never had one. CBK's 91-day yield that day was 8.778%.
* ``total_annual_service_cost`` — the homepage's "Annual service" — was
  KES 1,022.4Bn: those fixture rates times three balances.
* The 300Bn "Domestic Infrastructure & Green Bonds" row PR #178 removed from
  the fixture was still in the table, still in the headline.

Every test here was run against the pre-fix code and seen to fail there.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from seeding.domains.national_debt import fetcher as debt_fetcher
from seeding.domains.national_debt.cbk_web_tables import (
    CbkTableError,
    KeyRate,
    parse_key_rate,
)
from seeding.domains.national_debt.interest_terms import (
    UNDECLARED_REASON,
    absent_terms,
    published_cost_terms,
    published_rate_terms,
    terms_from_provenance,
    validate_terms,
)
from seeding.domains.national_debt.parser import DebtRecord, parse_debt_payload
from seeding.domains.national_debt.wb_ids_creditors import (
    Creditor,
    EXTERNAL_RATE_ABSENT_REASON,
    IdsCreditorError,
    fetch_interest_paid,
    to_loan_rows,
)
from seeding.domains.national_debt.writer import write_debt_records

_SRC = {"publisher": "Central Bank of Kenya", "title": "t", "url": "https://x.example/"}


# ── The declaration contract ────────────────────────────────────────────────


class TestDeclarationContract:
    def test_a_value_and_a_reason_together_is_refused(self):
        t = published_rate_terms(
            rate_pct=13.4, basis="coupon_weighted_average", label="l",
            source=_SRC, outstanding_kes=100.0, cost_label="c",
        )
        t["rate_absent_reason"] = "also absent?"
        assert any("both" in p for p in validate_terms(t))

    def test_neither_a_value_nor_a_reason_is_refused(self):
        t = absent_terms("x")
        t["rate_absent_reason"] = None
        assert any("neither" in p for p in validate_terms(t))

    def test_a_modelled_cost_needs_a_published_rate(self):
        t = published_cost_terms(cost_kes=5.0, label="l", source=_SRC, rate_reason="r")
        t["annual_cost_basis"] = "modelled"
        assert any("modelled" in p for p in validate_terms(t))

    @pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1.0, 250.0, "14.5"])
    def test_hostile_rates_are_refused(self, bad):
        t = published_rate_terms(
            rate_pct=13.4, basis="coupon_weighted_average", label="l",
            source=_SRC, outstanding_kes=100.0, cost_label="c",
        )
        t["rate_pct"] = bad
        assert validate_terms(t)

    def test_a_row_with_no_declaration_publishes_nothing(self):
        """Every row written before this change has a provenance entry with no
        declaration. Its interest_rate column may hold 14.5 — it must not
        surface."""
        t = terms_from_provenance([{"dataset_id": "national-debt"}])
        assert t["rate_pct"] is None and t["annual_cost_kes"] is None
        assert t["rate_absent_reason"] == UNDECLARED_REASON

    def test_an_invalid_declaration_is_withheld_not_published(self):
        bad = absent_terms("r")
        bad["rate_pct"] = 14.5  # value AND reason
        t = terms_from_provenance([{"interest_terms": bad}])
        assert t["rate_pct"] is None
        assert "failed validation" in t["rate_absent_reason"]

    def test_the_newest_entry_decides(self):
        old = published_cost_terms(cost_kes=5.0, label="l", source=_SRC, rate_reason="r")
        new = absent_terms("gone")
        assert terms_from_provenance([{"interest_terms": old}, {"interest_terms": new}])[
            "annual_cost_kes"
        ] is None


# ── External: World Bank IDS interest paid ─────────────────────────────────


def _ids_rows(series_rows):
    return lambda client, series, year: {
        name: (cid, usd) for name, cid, usd in series_rows.get(series, [])
    }


_INTEREST_2024 = {
    # Real 2024 World totals, captured 2026-09-26. Creditor detail trimmed to
    # rows that sum to World exactly.
    "DT.INT.MLAT.CD": [("World", "WLD", 300.0), ("World Bank-IDA", "905", 200.0), ("African Dev. Bank", "913", 100.0)],
    "DT.INT.BLAT.CD": [("World", "WLD", 362_300_000.0), ("China", "730", 362_300_000.0)],
    "DT.INT.PBND.CD": [("World", "WLD", 485_000_000.0), ("Bondholders", "808", 485_000_000.0)],
    "DT.INT.PCBK.CD": [("World", "WLD", 42_000_000.0), ("Italy", "006", 42_000_000.0)],
    "DT.INT.DIMF.CD": [("World", "WLD", 132_400_000.0), ("International Monetary Fund", "907", 132_400_000.0)],
}


class TestIdsInterestPaid:
    def test_interest_is_keyed_to_the_stock_series_and_creditor(self, monkeypatch):
        monkeypatch.setattr(
            "seeding.domains.national_debt.wb_ids_creditors._fetch_series",
            _ids_rows(_INTEREST_2024),
        )
        paid, checks = fetch_interest_paid(object(), 2024)
        assert paid[("DT.DOD.BLAT.CD", "China")] == 362_300_000.0
        assert paid[("DT.DOD.DIMF.CD", "International Monetary Fund")] == 132_400_000.0
        assert all(c["identity"] == "ok" for c in checks["series"].values())

    def test_interest_rows_that_do_not_sum_to_world_are_refused(self, monkeypatch):
        short = dict(_INTEREST_2024)
        short["DT.INT.MLAT.CD"] = [("World", "WLD", 300.0), ("World Bank-IDA", "905", 200.0)]
        monkeypatch.setattr(
            "seeding.domains.national_debt.wb_ids_creditors._fetch_series",
            _ids_rows(short),
        )
        with pytest.raises(IdsCreditorError, match="DT.INT.MLAT.CD"):
            fetch_interest_paid(object(), 2024)

    def _creditor(self, name="China", series="DT.DOD.BLAT.CD"):
        return Creditor(
            name=name, counterpart_id="730", series=series,
            debt_category="external_bilateral", usd=5.6e9,
            usd_kes_rate=Decimal("130"),
        )

    def test_a_creditor_row_publishes_interest_paid_and_no_rate(self):
        row = to_loan_rows(
            [self._creditor()], 2024, {("DT.DOD.BLAT.CD", "China"): 333_900_000.0}
        )[0]
        t = row["interest_terms"]
        assert validate_terms(t) == []
        assert t["annual_cost_kes"] == pytest.approx(333_900_000.0 * 130)
        assert t["annual_cost_basis"] == "published"
        assert "2024" in t["annual_cost_label"]
        assert "DT.INT.BLAT.CD" in t["annual_cost_source"]["url"]
        assert t["rate_pct"] is None
        assert t["rate_absent_reason"] == EXTERNAL_RATE_ABSENT_REASON

    def test_a_creditor_ids_reports_no_interest_for_is_absent_not_zero(self):
        t = to_loan_rows([self._creditor()], 2024, {})[0]["interest_terms"]
        assert t["annual_cost_kes"] is None
        assert "no interest-paid figure" in t["annual_cost_absent_reason"]

    def test_a_failed_interest_pull_says_so_on_every_row(self):
        t = to_loan_rows([self._creditor()], 2024, None, "IdsCreditorError: short")[0][
            "interest_terms"
        ]
        assert t["annual_cost_kes"] is None
        assert "IdsCreditorError: short" in t["annual_cost_absent_reason"]


# ── Domestic: CBK coupons and the 91-day yield ─────────────────────────────


KEY_RATES_HTML = """
<table class="tg"><tr><th class="tg-hgcj" colspan="4">Key Rates<br></th></tr>
<tr><td colspan="2"><small>Central Bank Rate</small></td><td>8.75%</td><td>11/08/2026</td></tr>
<tr><td colspan="2"><small>182-Day T-Bill</small></td><td>9.100%</td><td>05/10/2026</td></tr>
<tr><td colspan="2"><small>91-Day T-Bill</small></td><td>8.778%</td><td>05/10/2026</td></tr>
</table>
"""


class TestCbkKeyRates:
    def test_reads_the_91_day_row_exactly(self):
        rate = parse_key_rate(KEY_RATES_HTML, "91-Day T-Bill")
        assert rate.rate_pct == 8.778
        assert rate.cbk_date_text == "05/10/2026"
        assert rate.cbk_date.isoformat() == "2026-10-05"

    def test_a_near_miss_label_does_not_stand_in(self):
        html = KEY_RATES_HTML.replace("91-Day T-Bill", "91-Day Treasury Bill")
        with pytest.raises(CbkTableError, match="no '91-Day T-Bill' row"):
            parse_key_rate(html, "91-Day T-Bill")

    def test_a_non_percentage_is_refused(self):
        with pytest.raises(CbkTableError):
            parse_key_rate(KEY_RATES_HTML.replace("8.778%", "N/A"), "91-Day T-Bill")


def _fixture_payload():
    """The shape national_debt.json has, rates and all."""
    return {
        "loans": [
            {"lender": "Domestic Treasury Bonds", "debt_category": "domestic_bonds",
             "outstanding": "5579000000000", "principal": "5579000000000", "interest_rate": 14.5},
            {"lender": "Domestic Treasury Bills (91-day, 182-day, 364-day)",
             "debt_category": "domestic_bills", "outstanding": "1090000000000",
             "principal": "1090000000000", "interest_rate": 16.0},
            {"lender": "CBK Overdraft Facility", "debt_category": "domestic_overdraft",
             "outstanding": "78200000000", "principal": "78200000000", "interest_rate": 0.0},
        ]
    }


_REGISTER = {
    "source_url": "https://www.centralbank.go.ke/bills-bonds/treasury-bonds/",
    "source_title": "CBK — Issues of Treasury Bonds",
    "as_of": "2026-09-26",
    "coverage": {"coverage_ratio": 0.627},
    "securities": [
        {"coupon_rate": 10.0, "face_value_kes": 1_000.0},
        {"coupon_rate": 16.0, "face_value_kes": 3_000.0},
        {"coupon_rate": None, "face_value_kes": 9_999.0},  # unpriced: not averaged
    ],
}
_TBILL = {
    "rate": KeyRate("91-Day T-Bill", 8.778, "05/10/2026", datetime(2026, 10, 5).date()),
    "source_url": "https://www.centralbank.go.ke/project/government-securities/",
    "source_title": "CBK — Key Rates (91-Day T-Bill)",
    "retrieved_at": "2026-09-26",
}


class TestFetcherDeclaresEveryRow:
    def _declared(self, register=_REGISTER, tbill=_TBILL):
        payload = debt_fetcher._strip_fixture_rates(_fixture_payload())
        return {
            l["lender"]: l
            for l in debt_fetcher._declare_interest_terms(payload, register, tbill)["loans"]
        }

    def test_no_fixture_rate_survives(self):
        rows = self._declared(register=None, tbill=None)
        for row in rows.values():
            assert row["interest_rate"] is None
            assert row["interest_terms"]["rate_pct"] is None
            assert row["interest_terms"]["annual_cost_kes"] is None

    def test_bonds_carry_the_face_weighted_register_coupon(self):
        t = self._declared()["Domestic Treasury Bonds"]["interest_terms"]
        assert t["rate_pct"] == pytest.approx((10 * 1000 + 16 * 3000) / 4000)  # 14.5
        assert t["rate_basis"] == "coupon_weighted_average"
        assert "2 bonds" in t["rate_label"] and "63%" in t["rate_label"]
        assert t["annual_cost_basis"] == "modelled"
        assert t["annual_cost_kes"] == pytest.approx(5_579e9 * 0.145)

    def test_bills_carry_the_91_day_yield_labelled_as_one_tenor(self):
        t = self._declared()["Domestic Treasury Bills (91-day, 182-day, 364-day)"][
            "interest_terms"
        ]
        assert t["rate_pct"] == 8.778
        assert "91-day" in t["rate_label"] and "182" in t["rate_label"]
        assert t["annual_cost_basis"] == "modelled"

    def test_a_facility_nobody_prices_is_absent_with_the_reason(self):
        row = self._declared()["CBK Overdraft Facility"]
        assert row["interest_rate"] is None  # the fixture said 0.0
        assert row["interest_terms"]["rate_absent_reason"] == debt_fetcher.NO_PUBLISHED_RATE_REASON

    def test_every_declaration_validates(self):
        for row in self._declared().values():
            assert validate_terms(row["interest_terms"]) == []

    def test_the_mirrored_column_matches_its_precision(self):
        """Numeric(5,2): an unrounded mirror would read as a new rate every run."""
        rate = self._declared()["Domestic Treasury Bills (91-day, 182-day, 364-day)"][
            "interest_rate"
        ]
        assert rate == 8.78


# ── The writer ──────────────────────────────────────────────────────────────


@pytest.fixture()
def national(db_session, seed_country, seed_source_doc):
    from models import Entity, EntityType

    e = Entity(
        country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name="National Government", slug="national-government",
    )
    db_session.add(e)
    db_session.commit()
    return e


def _record(lender, category, outstanding, terms=None, rate=None):
    return DebtRecord(
        entity_name="National Government", entity_type="national", lender=lender,
        principal=Decimal(outstanding), outstanding=Decimal(outstanding),
        issue_date=datetime(2025, 12, 31), maturity_date=None, currency="KES",
        source_title="CBK Statistical Bulletin", debt_category=category,
        interest_rate=rate, interest_terms=terms,
    )


class TestWriter:
    def test_a_row_with_no_rate_is_stored_null_not_zero(self, db_session, national):
        from models import Loan

        write_debt_records(
            db_session, [_record("Bilateral (China)", "external_bilateral", "723e9",
                                 terms=absent_terms("r"))], "national-debt", 1,
        )
        db_session.commit()
        loan = db_session.query(Loan).filter_by(lender="Bilateral (China)").one()
        assert loan.interest_rate is None

    def test_a_stale_stored_rate_is_cleared_when_the_run_has_none(
        self, db_session, national, seed_source_doc
    ):
        from models import DebtCategory, Loan

        db_session.add(Loan(
            entity_id=national.id, lender="Domestic Treasury Bonds",
            debt_category=DebtCategory.DOMESTIC_BONDS, principal=5579e9,
            outstanding=5579e9, interest_rate=Decimal("14.50"),
            issue_date=datetime(2025, 12, 31), currency="KES",
            source_document_id=seed_source_doc.id, provenance=[{"dataset_id": "x"}],
        ))
        db_session.commit()
        # Same balance, no rate this run: the old code kept 14.50.
        write_debt_records(
            db_session, [_record("Domestic Treasury Bonds", "domestic_bonds", "5579e9",
                                 terms=absent_terms("r"))], "national-debt", 2,
        )
        loan = db_session.query(Loan).filter_by(lender="Domestic Treasury Bonds").one()
        assert loan.interest_rate is None
        assert loan.provenance[-1]["interest_terms"]["rate_absent_reason"] == "r"

    def test_a_new_declaration_is_recorded_even_when_the_balance_did_not_move(
        self, db_session, national
    ):
        from models import Loan

        rec = _record("Bilateral (China)", "external_bilateral", "723e9", terms=absent_terms("r"))
        write_debt_records(db_session, [rec], "national-debt", 1)
        db_session.commit()
        paid = published_cost_terms(cost_kes=43e9, label="Interest paid in 2024",
                                    source=_SRC, rate_reason="r")
        write_debt_records(
            db_session,
            [_record("Bilateral (China)", "external_bilateral", "723e9", terms=paid)],
            "national-debt", 2,
        )
        db_session.commit()
        loan = db_session.query(Loan).filter_by(lender="Bilateral (China)").one()
        assert terms_from_provenance(loan.provenance)["annual_cost_kes"] == 43e9

    def test_the_orphan_infrastructure_bond_row_is_deleted_beside_its_aggregate(
        self, db_session, national, seed_source_doc
    ):
        from models import DebtCategory, Loan

        db_session.add(Loan(
            entity_id=national.id, lender="Domestic Infrastructure & Green Bonds",
            debt_category=DebtCategory.DOMESTIC_BONDS, principal=300e9,
            outstanding=300e9, interest_rate=Decimal("13.00"),
            issue_date=datetime(2026, 2, 21), currency="KES",
            source_document_id=seed_source_doc.id,
        ))
        db_session.commit()
        write_debt_records(
            db_session, [_record("Domestic Treasury Bonds", "domestic_bonds", "5579e9",
                                 terms=absent_terms("r"))], "national-debt", 3,
        )
        db_session.commit()
        lenders = {l.lender for l in db_session.query(Loan).all()}
        assert lenders == {"Domestic Treasury Bonds"}

    def test_without_its_aggregate_the_subset_row_is_kept(
        self, db_session, national, seed_source_doc
    ):
        """Deleting it then would understate, not correct."""
        from models import DebtCategory, Loan

        db_session.add(Loan(
            entity_id=national.id, lender="Domestic Infrastructure & Green Bonds",
            debt_category=DebtCategory.DOMESTIC_BONDS, principal=300e9,
            outstanding=300e9, issue_date=datetime(2026, 2, 21), currency="KES",
            source_document_id=seed_source_doc.id,
        ))
        db_session.commit()
        write_debt_records(
            db_session, [_record("Bilateral (China)", "external_bilateral", "723e9",
                                 terms=absent_terms("r"))], "national-debt", 4,
        )
        db_session.commit()
        assert db_session.query(Loan).filter_by(
            lender="Domestic Infrastructure & Green Bonds"
        ).count() == 1

    def test_the_parser_carries_the_declaration_and_keeps_a_real_zero(self):
        recs = parse_debt_payload({"loans": [{
            "entity_name": "National Government", "entity_type": "national",
            "lender": "X", "principal": "1", "outstanding": "1",
            "issue_date": "2025-12-31", "interest_rate": 0.0,
            "interest_terms": absent_terms("r"),
        }]})
        assert recs[0].interest_rate == Decimal("0.0")
        assert recs[0].interest_terms["rate_absent_reason"] == "r"


# ── The API ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def register(db_session, national, seed_source_doc):
    from models import DebtCategory, FiscalSummary, Loan

    bond_terms = published_rate_terms(
        rate_pct=13.41, basis="coupon_weighted_average",
        label="Average coupon of the 56 bonds in CBK's register",
        source=_SRC, outstanding_kes=5579e9, cost_label="Modelled: balance × coupon",
    )
    china_terms = published_cost_terms(
        cost_kes=43.4e9, label="Interest paid in 2024",
        source={"publisher": "World Bank", "title": "IDS", "url": "https://api.worldbank.org/x"},
        rate_reason=EXTERNAL_RATE_ABSENT_REASON,
    )
    rows = [
        # (lender, category, outstanding, stored column, provenance)
        ("Domestic Treasury Bonds", DebtCategory.DOMESTIC_BONDS, 5579e9, Decimal("13.41"),
         [{"interest_terms": bond_terms}]),
        ("Bilateral (China)", DebtCategory.EXTERNAL_BILATERAL, 723.6e9, None,
         [{"interest_terms": china_terms}]),
        # Written before this change: the column says 16.00, nothing declares it.
        ("Domestic Treasury Bills", DebtCategory.DOMESTIC_BILLS, 1090e9, Decimal("16.00"),
         [{"dataset_id": "national-debt"}]),
        # The manufactured zero.
        ("Bilateral (Japan)", DebtCategory.EXTERNAL_BILATERAL, 157.3e9, Decimal("0"),
         [{"dataset_id": "national-debt"}]),
    ]
    for lender, cat, amt, col, prov in rows:
        db_session.add(Loan(
            entity_id=national.id, lender=lender, debt_category=cat, principal=amt,
            outstanding=amt, interest_rate=col, issue_date=datetime(2025, 12, 31),
            currency="KES", source_document_id=seed_source_doc.id, provenance=prov,
        ))
    db_session.add(FiscalSummary(
        fiscal_year="FY 2026/27", appropriated_budget=5_485_700_000_000,
        total_revenue=2_985_700_000_000, debt_service_cost=2_315_900_000_000,
        county_allocation=420_000_000_000,
        page_ref="voted total PDF p.11; CFS summary PDF p.1193",
        meta={
            "budget_basis": "cob_gross",
            "budget_basis_source": {
                "publisher": "The National Treasury",
                "title": "Programme Based Budget FY 2026/27 (Approved)",
                "url": "https://www.treasury.go.ke/sites/default/files/pbb.pdf",
                "page": "voted total PDF p.11",
            },
            "debt_service_source": {
                "publisher": "The National Treasury",
                "title": "Programme Based Budget FY 2026/27 (Approved)",
                "url": "https://www.treasury.go.ke/sites/default/files/pbb.pdf",
                "page": "CFS summary PDF p.1193",
            },
        },
    ))
    db_session.commit()


def _by_lender(payload):
    return {l["lender"]: l for l in payload["loans"]}


@pytest.mark.parametrize("path", ["/api/v1/debt/loans", "/api/v1/debt/top-loans"])
class TestLoansApi:
    def test_no_row_publishes_a_manufactured_zero(self, client, register, path):
        for row in client.get(path).json()["loans"]:
            assert row["interest_rate"] != "0.00%"
            assert row["annual_service_cost"] != 0

    def test_an_undeclared_stored_rate_is_not_published(self, client, register, path):
        bills = _by_lender(client.get(path).json())["Domestic Treasury Bills"]
        assert bills["interest_rate"] is None
        assert bills["annual_service_cost"] is None
        assert bills["interest_rate_absent_reason"] == UNDECLARED_REASON

    def test_a_declared_rate_is_published_with_its_basis(self, client, register, path):
        bonds = _by_lender(client.get(path).json())["Domestic Treasury Bonds"]
        assert bonds["interest_rate"] == "13.41%"
        assert bonds["interest_rate_basis"] == "coupon_weighted_average"
        assert bonds["annual_service_basis"] == "modelled"
        assert bonds["annual_service_cost"] == pytest.approx(5579e9 * 0.1341)

    def test_published_interest_paid_is_published_as_such(self, client, register, path):
        china = _by_lender(client.get(path).json())["Bilateral (China)"]
        assert china["annual_service_cost"] == 43.4e9
        assert china["annual_service_basis"] == "published"
        assert china["interest_rate"] is None

    def test_no_maturity_date_is_not_matured(self, client, register, path):
        for row in client.get(path).json()["loans"]:
            assert row["status"] is None


def test_the_register_total_is_the_published_debt_service(client, register):
    body = client.get("/api/v1/debt/loans").json()
    assert body["total_annual_service_cost"] is None
    assert body["total_annual_service_cost_absent_reason"]
    ads = body["annual_debt_service"]
    assert ads["value_kes"] == 2_315_900_000_000
    assert ads["fiscal_year"] == "FY 2026/27"
    assert ads["source"]["title"] == "Programme Based Budget FY 2026/27 (Approved)"
    assert ads["source"]["page"] == "CFS summary PDF p.1193"  # the CFS page, not the budget's
    # Same year and value the fiscal summary calls current.
    current = client.get("/api/v1/fiscal/summary").json()["current"]
    assert (current["fiscal_year"], current["debt_service_cost"]) == (
        ads["fiscal_year"], ads["value_kes"],
    )


def test_an_empty_register_totals_null_not_zero(client, national):
    body = client.get("/api/v1/debt/loans").json()
    assert body["total_outstanding"] is None
    assert body["total_annual_service_cost"] is None


def test_a_budget_source_is_not_cited_for_debt_service(client, register, db_session):
    """budget_basis_source says where the BUDGET came from. For FY2025/26 that
    is COB's nine-month report while the debt service is the BPS estimate, so
    citing it for debt service mis-cites. No debt-service source, no figure."""
    from models import FiscalSummary

    row = db_session.query(FiscalSummary).filter_by(fiscal_year="FY 2026/27").one()
    row.meta = {k: v for k, v in row.meta.items() if k != "debt_service_source"}
    db_session.commit()
    ads = client.get("/api/v1/debt/loans").json()["annual_debt_service"]
    assert ads["value_kes"] is None
    assert "does not record the document" in ads["absent_reason"]


def test_the_fiscal_writer_keeps_the_debt_service_source(db_session, seed_country):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records

    src = {"title": "PBB", "publisher": "The National Treasury",
           "url": "https://www.treasury.go.ke/x.pdf", "page": "CFS p.1193"}
    records = parse_fiscal_summary_payload({"fiscal_years": [{
        "fiscal_year": "FY 2026/27", "debt_service_cost": 2315.9,
        "debt_service_source": src,
    }]})
    write_fiscal_summary_records(db_session, records, {"source": "t"})
    row = db_session.query(FiscalSummary).filter_by(fiscal_year="FY 2026/27").one()
    assert row.meta["debt_service_source"] == src

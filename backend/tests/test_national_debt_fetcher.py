"""Tests for the national_debt fetcher's fixture+overlay strategy.

The fetcher composes two live overlays (WB IDS for external
creditors, CBK Statistical Bulletin for domestic instruments) onto a
fixture baseline. These tests mock out the HTTP client so the
overlay logic is verified deterministically without depending on
either upstream being reachable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from seeding.config import SeedingSettings
from seeding.domains.national_debt import cbk_bulletin
from seeding.domains.national_debt import fetcher as nd_fetcher
from seeding.domains.national_debt import wb_ids


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


def _baseline_payload() -> Dict[str, Any]:
    """Mimics the existing fixture shape with three lender rows we'll
    expect WB IDS to overlay onto."""
    return {
        "metadata": {"source": "fixture", "units": "kes"},
        "source_url": "file://fixture",
        "source_title": "fixture",
        "loans": [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (World Bank / IDA / IBRD)",
                "debt_category": "external_multilateral",
                "principal": "820000000000.00",
                "outstanding": "805000000000.00",
                "interest_rate": "1.25",
                "issue_date": "2000-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "fixture row",
            },
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Bilateral (China — Exim Bank / CDB)",
                "debt_category": "external_bilateral",
                "principal": "650000000000.00",
                "outstanding": "640000000000.00",
                "interest_rate": "3.00",
                "issue_date": "2014-05-01",
                "maturity_date": "2030-05-01",
                "currency": "KES",
                "notes": "fixture row (no WB IDS overlay)",
            },
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Commercial Banks (Syndicated loans)",
                "debt_category": "external_commercial",
                "principal": "200000000000.00",
                "outstanding": "195000000000.00",
                "interest_rate": "8.00",
                "issue_date": "2020-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "fixture row",
            },
        ],
    }


def _wb_response(value_usd: float, year: str = "2024") -> List[Any]:
    """Minimal WB API response with a single observation."""
    return [
        {"page": 1, "pages": 1, "per_page": 10, "total": 1},
        [
            {
                "indicator": {"id": "X", "value": "x"},
                "country": {"id": "KE", "value": "Kenya"},
                "countryiso3code": "KEN",
                "date": year,
                "value": value_usd,
                "unit": "",
                "obs_status": "",
                "decimal": 0,
            }
        ],
    ]


# ── wb_ids.fetch_external_debt_from_wb_ids ──


class TestWbIdsFetcher:
    def test_emits_one_row_per_curated_creditor(self, settings):
        """Happy path: every WB code returns a value → one loan per
        creditor in the curated list, with KES converted at 130/USD.
        Curated list is currently {WB combined, IMF} = 2 creditors;
        PCBK + bilateral aggregate are intentionally excluded
        (see WB_IDS_CREDITORS comments)."""

        class FakeClient:
            def get(self, url, **_kwargs):
                # Different USD totals depending on indicator so we can
                # tell them apart in assertions.
                if "MIBR" in url:
                    body = _wb_response(8_000_000_000)  # IBRD
                elif "MIDA" in url:
                    body = _wb_response(2_000_000_000)  # IDA combined into the row
                elif "DIMF" in url:
                    body = _wb_response(3_300_000_000)  # IMF
                else:
                    raise AssertionError(f"unexpected URL: {url}")

                class R:
                    def json(self_):
                        return body
                return R()

        loans = wb_ids.fetch_external_debt_from_wb_ids(FakeClient(), settings)

        assert len(loans) == 2  # WB+IDA combined + IMF
        by_lender = {l["lender"]: l for l in loans}
        # World Bank is IBRD + IDA = 10B USD → 1300B KES
        wb = by_lender["Multilateral (World Bank / IDA / IBRD)"]
        assert wb["debt_category"] == "external_multilateral"
        assert Decimal(wb["outstanding"]) == Decimal("1300000000000.00")
        assert wb["currency"] == "KES"
        # Notes record the WB IDS provenance.
        assert "MIBR" in wb["notes"] and "MIDA" in wb["notes"] and "2024" in wb["notes"]

    def test_per_creditor_failure_is_isolated(self, settings):
        """A single 502/timeout doesn't kill the whole pull — other
        creditors are still emitted."""

        class FakeClient:
            def get(self, url, **_kwargs):
                if "DIMF" in url:
                    raise RuntimeError("simulated 502")
                # All others return 1 USD so we can count them.
                class R:
                    def json(self_):
                        return _wb_response(1.0)
                return R()

        loans = wb_ids.fetch_external_debt_from_wb_ids(FakeClient(), settings)
        # IMF is missing; World Bank still comes through.
        lenders = {l["lender"] for l in loans}
        assert "Multilateral (IMF — Extended Credit & Resilience Trust)" not in lenders
        assert "Multilateral (World Bank / IDA / IBRD)" in lenders

    def test_skips_when_value_is_null(self, settings):
        """WB sometimes returns rows with value=null (suppression /
        provisional). Those creditors must be skipped, not emitted as
        zero-stock records."""

        class FakeClient:
            def get(self, url, **_kwargs):
                empty = [
                    {"page": 1, "pages": 1, "per_page": 10, "total": 1},
                    [
                        {"date": "2024", "value": None}
                    ],
                ]
                class R:
                    def json(self_):
                        return empty
                return R()

        loans = wb_ids.fetch_external_debt_from_wb_ids(FakeClient(), settings)
        assert loans == []

    def test_skips_combined_row_when_secondary_fails(self, settings):
        """If the primary indicator (IBRD) succeeds but the
        ``combine_with`` secondary (IDA) fails — e.g. WB API returns
        an intermittent 400 — we MUST NOT emit the IBRD-only value as
        the World Bank total. A real prod run silently undercounted
        WB lending by 7x ($1.9B vs the $13.8B IBRD+IDA combined). The
        whole row is dropped so the fixture stays in place; the next
        run retries."""

        class FakeClient:
            def get(self, url, **_kwargs):
                if "MIDA" in url:  # the combine_with secondary
                    raise RuntimeError("simulated WB API 400")
                # Both MIBR (IBRD primary) and DIMF (IMF) succeed.
                class R:
                    def json(self_):
                        return _wb_response(1_000_000_000)
                return R()

        loans = wb_ids.fetch_external_debt_from_wb_ids(FakeClient(), settings)
        lenders = {l["lender"] for l in loans}
        # WB row dropped because IDA leg unavailable.
        assert "Multilateral (World Bank / IDA / IBRD)" not in lenders
        # IMF (no combine_with) is unaffected.
        assert "Multilateral (IMF — Extended Credit & Resilience Trust)" in lenders


# ── fetcher._overlay_loans ──


class TestOverlayMerge:
    def test_overlay_replaces_baseline_by_lender_match(self):
        baseline = _baseline_payload()
        overlay = [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (World Bank / IDA / IBRD)",
                "debt_category": "external_multilateral",
                "principal": "999999999999.00",
                "outstanding": "888888888888.00",
                "interest_rate": None,
                "issue_date": "2024-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "wb_ids overlay",
            }
        ]
        merged = nd_fetcher._overlay_loans(baseline, overlay)
        loans = merged["loans"]
        # Same row count — overlay replaced, didn't append.
        assert len(loans) == 3
        wb = next(l for l in loans if "World Bank" in l["lender"])
        assert wb["outstanding"] == "888888888888.00"
        assert wb["notes"] == "wb_ids overlay"
        # Untouched fixture rows preserved unchanged.
        china = next(l for l in loans if "China" in l["lender"])
        assert china["outstanding"] == "640000000000.00"

    def test_overlay_appends_unmatched_rows(self):
        """If an overlay row has a lender the fixture doesn't carry,
        it's appended (we'd rather over-include than silently drop)."""
        baseline = _baseline_payload()
        overlay = [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (Brand New Lender)",
                "debt_category": "external_multilateral",
                "principal": "1.00",
                "outstanding": "1.00",
                "interest_rate": None,
                "issue_date": "2024-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "new",
            }
        ]
        merged = nd_fetcher._overlay_loans(baseline, overlay)
        assert len(merged["loans"]) == 4
        assert any("Brand New Lender" in l["lender"] for l in merged["loans"])

    def test_overlay_lender_match_is_whitespace_collapsed(self):
        """Cosmetic whitespace differences in the lender string
        shouldn't fork rows."""
        baseline = _baseline_payload()
        # Same lender, but extra spaces and varied case.
        overlay = [
            {
                "lender": "  multilateral  (world bank /  IDA / IBRD) ",
                "outstanding": "1.00",
                "principal": "1.00",
                "entity_name": "National Government",
                "entity_type": "national",
                "debt_category": "external_multilateral",
                "interest_rate": None,
                "issue_date": "2024-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "overlay",
            }
        ]
        merged = nd_fetcher._overlay_loans(baseline, overlay)
        # Replaced (still 3 loans), not appended (would be 4).
        assert len(merged["loans"]) == 3


# ── cbk_bulletin (parser internals) ──


# A trimmed slice of real Table 4.1.4 page text covering two fiscal
# years and a handful of months — enough to exercise the FY-to-
# calendar-year mapping and the "latest row wins" rule. Numbers are
# from the June 2025 bulletin (KES millions).
_REAL_PAGE_TEXT = """\
4.1 GOVERNMENT FINANCE
Financing and Stock of Government Debt
Table 4.1.4: Composition of Government Gross Domestic Debt
by Instrument Shillings million
Treasury Treasury Government Overdraft at Advances from Other Domestic Total Domestic
Fiscal Year
Bills* Bonds Stocks Central Bank Commercial Banks Debt** Debt***
2023/2024
July 602,312.8 4,097,244.5 0.0 61,117.8 14,531.3 98,320.9 4,873,527.3
August 584,879.9 4,139,722.8 0.0 72,054.1 16,246.8 99,435.4 4,912,338.9
2024/2025
July 667,963.1 4,637,887.2 0.0 60,529.1 2,487.1 84,129.1 5,452,995.5
June 1,052,945.0 5,110,010.0 0.0 67,628.8 14,791.8 80,633.7 6,326,009.3
* The stock of Treasury bills includes Repos.
"""


class TestCbkBulletinParserInternals:
    def test_picks_last_month_row_in_page(self):
        """The latest data point in the page is the only one we keep —
        prior months are observable history but only the most recent
        bulletin row drives the overlay."""
        result = cbk_bulletin._parse_latest_month_row(_REAL_PAGE_TEXT)
        assert result is not None
        measurement_date, fy_start, values = result
        # Last row in the page text is "June ..." inside FY 2024/2025.
        assert measurement_date == date(2025, 6, 1)
        assert fy_start == 2024
        # Values match the June 2025 line: bills, bonds, stocks,
        # overdraft, advances, other, total.
        assert values == [
            Decimal("1052945.0"),
            Decimal("5110010.0"),
            Decimal("0.0"),
            Decimal("67628.8"),
            Decimal("14791.8"),
            Decimal("80633.7"),
            Decimal("6326009.3"),
        ]

    def test_jul_dec_rows_use_first_calendar_year_of_fy(self):
        """FY 2024/2025 → July rows are calendar 2024, June rows are
        calendar 2025. This catches accidental off-by-one in the
        FY→calendar mapping (a real bug we'd silently ship otherwise)."""
        july_only = """\
Table 4.1.4: Composition of Government Gross Domestic Debt
2024/2025
July 1.0 2.0 0.0 3.0 4.0 5.0 15.0
"""
        result = cbk_bulletin._parse_latest_month_row(july_only)
        assert result is not None
        measurement_date, fy_start, _ = result
        assert measurement_date == date(2024, 7, 1)
        assert fy_start == 2024

    def test_returns_none_when_no_month_rows(self):
        """A page that has the title but no data rows (e.g. a
        renumbered bulletin where only the heading lines up) should
        be a clean None, not a crash."""
        bare = """\
Table 4.1.4: Composition of Government Gross Domestic Debt
no usable rows here
"""
        assert cbk_bulletin._parse_latest_month_row(bare) is None

    def test_returns_none_when_month_rows_lack_fy_header(self):
        """If we somehow read month rows without ever passing through
        a fiscal-year header, we can't infer calendar year — bail
        rather than guess."""
        no_fy = """\
Table 4.1.4: Composition of Government Gross Domestic Debt
June 1.0 2.0 0.0 3.0 4.0 5.0 15.0
"""
        assert cbk_bulletin._parse_latest_month_row(no_fy) is None

    def test_build_loan_records_skips_zero_columns(self):
        """Columns that come in at zero (e.g. Government Stocks
        always) shouldn't emit noisy zero-stock loans. Same applies
        to a temporarily-zero overdraft month."""
        # Only Bills + Bonds non-zero.
        values = [
            Decimal("100"),    # bills
            Decimal("200"),    # bonds
            Decimal("0"),      # gov stocks (always skipped via mapping)
            Decimal("0"),      # overdraft
            Decimal("0"),      # advances
            Decimal("0"),      # other
            Decimal("300"),    # total (always skipped via mapping)
        ]
        loans = cbk_bulletin._build_loan_records(
            measurement_date=date(2025, 6, 1),
            fiscal_year_start=2024,
            values=values,
            source_url="file://fake.pdf",
        )
        lenders = {l["lender"] for l in loans}
        assert lenders == {
            "Domestic Treasury Bills (91-day, 182-day, 364-day)",
            "Domestic Treasury Bonds",
        }

    def test_build_loan_records_uses_fy_start_as_issue_date(self):
        """issue_date pins to fiscal-year-start so within-FY pulls
        UPDATE the same writer row (dedupe key entity+lender+date)
        instead of forking new rows. Measurement month is preserved
        in notes."""
        loans = cbk_bulletin._build_loan_records(
            measurement_date=date(2025, 6, 1),
            fiscal_year_start=2024,
            values=[Decimal("1")] * 7,
            source_url="file://fake.pdf",
        )
        assert all(l["issue_date"] == "2024-07-01" for l in loans)
        assert all("month-end 2025-06-01" in l["notes"] for l in loans)


# ── cbk_bulletin.fetch_domestic_debt_from_cbk_bulletin (boundary) ──


class TestCbkBulletinFetcher:
    def test_returns_empty_when_url_not_configured(self, settings):
        """Default config (URL unset) means CBK overlay is opt-in.
        Must NOT attempt any download."""
        settings.cbk_statistical_bulletin_url = None
        # If anything tried to download, this would raise — proves we
        # short-circuit before touching the client.
        loans = cbk_bulletin.fetch_domestic_debt_from_cbk_bulletin(
            client=None, settings=settings
        )
        assert loans == []

    def test_returns_empty_when_pdf_lacks_table(self, settings):
        """If CBK renumbers the table or the wrong PDF is configured,
        we get an empty result instead of a crash."""
        settings.cbk_statistical_bulletin_url = "file:///fake.pdf"
        with (
            patch.object(cbk_bulletin, "_download_pdf", return_value=b"%PDF-fake"),
            patch.object(
                cbk_bulletin,
                "_extract_domestic_debt_page_text",
                return_value=None,
            ),
        ):
            loans = cbk_bulletin.fetch_domestic_debt_from_cbk_bulletin(
                client=None, settings=settings
            )
        assert loans == []

    def test_returns_empty_when_download_fails(self, settings):
        """A 404 / network drop on the bulletin URL must degrade
        silently — fixture stays in play."""
        settings.cbk_statistical_bulletin_url = "https://cbk.example/missing.pdf"
        with patch.object(
            cbk_bulletin, "_download_pdf", side_effect=RuntimeError("404")
        ):
            loans = cbk_bulletin.fetch_domestic_debt_from_cbk_bulletin(
                client=None, settings=settings
            )
        assert loans == []

    def test_end_to_end_against_synthetic_page_text(self, settings):
        """Full fetcher path with a synthetic page text — verifies
        the loan-record shape, KES scaling, and the row count."""
        settings.cbk_statistical_bulletin_url = "file:///fake.pdf"
        with (
            patch.object(cbk_bulletin, "_download_pdf", return_value=b"%PDF-fake"),
            patch.object(
                cbk_bulletin,
                "_extract_domestic_debt_page_text",
                return_value=_REAL_PAGE_TEXT,
            ),
        ):
            loans = cbk_bulletin.fetch_domestic_debt_from_cbk_bulletin(
                client=None, settings=settings
            )
        # 5 non-zero columns expected (Stocks=0 skipped; Total skipped).
        assert len(loans) == 5
        by_lender = {l["lender"]: l for l in loans}
        # Treasury Bonds: 5,110,010.0 KES million → 5.11013e12 KES.
        bonds = by_lender["Domestic Treasury Bonds"]
        assert Decimal(bonds["outstanding"]) == Decimal("5110010000000.00")
        assert bonds["debt_category"] == "domestic_bonds"
        assert bonds["currency"] == "KES"
        # All rows share the same FY-start issue_date.
        assert all(l["issue_date"] == "2024-07-01" for l in loans)


# ── fetcher.fetch_debt_payload (integration) ──


class TestFetchDebtPayload:
    def test_falls_back_to_fixture_when_wb_returns_nothing(self, settings):
        """If WB IDS yields zero rows (whole API down), we just return
        the fixture payload unchanged."""

        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=[]),
            patch.object(nd_fetcher, "fetch_domestic_debt_from_cbk_bulletin", return_value=[]),
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        assert len(payload["loans"]) == 3
        # Marker NOT set when we couldn't overlay anything.
        assert "wb_ids_overlay_applied" not in payload.get("metadata", {})
        assert "cbk_bulletin_overlay_applied" not in payload.get("metadata", {})

    def test_overlay_applied_metadata_set_on_success(self, settings):
        wb_overlay = [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (World Bank / IDA / IBRD)",
                "debt_category": "external_multilateral",
                "principal": "1.00",
                "outstanding": "1.00",
                "interest_rate": None,
                "issue_date": "2024-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "wb",
            }
        ]
        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=wb_overlay),
            patch.object(nd_fetcher, "fetch_domestic_debt_from_cbk_bulletin", return_value=[]),
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        meta = payload.get("metadata", {})
        assert meta.get("wb_ids_overlay_applied") is True
        assert meta.get("wb_ids_overlay_count") == 1

    def test_cbk_overlay_applied_metadata_set_on_success(self, settings):
        cbk_overlay = [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Domestic Treasury Bills (91-day, 182-day, 364-day)",
                "debt_category": "domestic_bills",
                "principal": "1.00",
                "outstanding": "1.00",
                "interest_rate": None,
                "issue_date": "2024-07-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "cbk",
            },
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Advances from Commercial Banks",
                "debt_category": "domestic_overdraft",
                "principal": "2.00",
                "outstanding": "2.00",
                "interest_rate": None,
                "issue_date": "2024-07-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "cbk",
            },
        ]
        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=[]),
            patch.object(
                nd_fetcher,
                "fetch_domestic_debt_from_cbk_bulletin",
                return_value=cbk_overlay,
            ),
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        meta = payload.get("metadata", {})
        assert meta.get("cbk_bulletin_overlay_applied") is True
        assert meta.get("cbk_bulletin_overlay_count") == 2

    def test_skips_overlay_when_live_fetch_disabled(self, settings):
        """Both overlays gate behind live_pdf_fetch_enabled — neither
        should be invoked when it's False."""
        settings.live_pdf_fetch_enabled = False
        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids") as mock_wb,
            patch.object(nd_fetcher, "fetch_domestic_debt_from_cbk_bulletin") as mock_cbk,
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        mock_wb.assert_not_called()
        mock_cbk.assert_not_called()
        assert "wb_ids_overlay_applied" not in payload.get("metadata", {})
        assert "cbk_bulletin_overlay_applied" not in payload.get("metadata", {})

    def test_continues_when_wb_raises_unexpectedly(self, settings):
        """A bug in the WB module shouldn't take down the whole
        domain — we degrade to fixture and log."""
        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(
                nd_fetcher, "fetch_external_debt_from_wb_ids",
                side_effect=RuntimeError("kaboom"),
            ),
            patch.object(nd_fetcher, "fetch_domestic_debt_from_cbk_bulletin", return_value=[]),
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        # Same fixture, no overlay marker.
        assert len(payload["loans"]) == 3
        assert "wb_ids_overlay_applied" not in payload.get("metadata", {})

    def test_continues_when_cbk_raises_unexpectedly(self, settings):
        """Same story for the CBK side — a parser bug or PDF-layout
        change must not take down the whole domain. WB IDS overlay
        still applies in that case."""
        wb_overlay = [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (World Bank / IDA / IBRD)",
                "debt_category": "external_multilateral",
                "principal": "1.00",
                "outstanding": "1.00",
                "interest_rate": None,
                "issue_date": "2024-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": "wb",
            }
        ]
        with (
            patch.object(nd_fetcher, "load_json_resource", return_value=_baseline_payload()),
            patch.object(nd_fetcher, "fetch_external_debt_from_wb_ids", return_value=wb_overlay),
            patch.object(
                nd_fetcher, "fetch_domestic_debt_from_cbk_bulletin",
                side_effect=RuntimeError("pdf parse exploded"),
            ),
        ):
            payload = nd_fetcher.fetch_debt_payload(client=None, settings=settings)
        meta = payload.get("metadata", {})
        # WB overlay still landed; CBK marker absent.
        assert meta.get("wb_ids_overlay_applied") is True
        assert "cbk_bulletin_overlay_applied" not in meta

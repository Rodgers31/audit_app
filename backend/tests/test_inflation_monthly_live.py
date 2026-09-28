"""Monthly CPI inflation from CBK, end to end (issue #232).

/budget captioned the World Bank's calendar-2025 annual average (4.1%) as
"KNBS Consumer Price Index" while KNBS's August 2026 headline was 6.59%. These
tests pin the live monthly source, its cross-check, the supersession sweep,
the freshness gate, and — through the real domain runner and the real
endpoint — what the strip is handed.

The CBK page fixture is the verbatim ``<table>`` element fetched 2026-09-26,
swapped June 2024 row included: a sanitised table would hide exactly the
defect the cross-check exists for.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from models import EconomicIndicator, Entity, EntityType, SourceDocument

from seeding import freshness
from seeding.config import SeedingSettings
from seeding.domains.economic_indicators import cbk_inflation, fetcher, writer
from seeding.types import DomainRunContext

FIXTURE = Path(__file__).parent / "fixtures" / "cbk" / "inflation_rates_2026-09-26.html"
CBK_HTML = FIXTURE.read_text(encoding="utf-8")

# World Bank values as the API returned them on 2026-09-26 (lastupdated
# 2026-07-13), trimmed to the years the assertions need.
WB = {
    "NY.GDP.MKTP.CN": [
        (2025, 17577557000000), (2024, 16232295000000), (2023, 15033610000000)
    ],
    "NY.GDP.MKTP.KD.ZG": [
        (2025, 4.63261093844984), (2024, 4.66019594571891), (2023, 5.71999241214208)
    ],
    "FP.CPI.TOTL.ZG": [
        (2025, 4.06912878540729), (2024, 4.48978854243448), (2023, 7.67139634029402)
    ],
    "SL.UEM.TOTL.ZS": [(2025, 5.449), (2024, 5.487), (2023, 5.409)],
}


class _Resp:
    def __init__(self, *, json_data=None, text=""):
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class FakeClient:
    """World Bank JSON and the CBK page, no network."""

    def __init__(self, *, wb=WB, cbk=CBK_HTML):
        self.wb = wb
        self.cbk = cbk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, raise_for_status=False, **_):
        if url == cbk_inflation.CBK_INFLATION_URL:
            if isinstance(self.cbk, Exception):
                raise self.cbk
            return _Resp(text=self.cbk)
        code = url.rsplit("/", 1)[1]
        rows = self.wb.get(code, [])
        return _Resp(
            json_data=[{"page": 1}, [{"date": str(y), "value": v} for y, v in rows]]
        )


# ── The parser, on the real page ─────────────────────────────────────────


class TestParseRealCbkTable:
    def test_newest_month_is_august_2026_twelve_month_rate(self):
        result = cbk_inflation.parse_cbk_inflation(CBK_HTML)
        newest = result.records[0]
        assert newest["reference_month"] == "2026-08"
        assert newest["date"] == "2026-08-31"
        assert newest["value"] == 6.59  # the 12-month column, not 5.25
        assert newest["annual_average_pct"] == 5.25

    def test_every_record_declares_its_provenance(self):
        result = cbk_inflation.parse_cbk_inflation(CBK_HTML)
        for rec in result.records:
            assert rec["indicator_type"] == "inflation_rate_12m"
            assert rec["source_label"] == "KNBS CPI, via Central Bank of Kenya"
            assert rec["measure"] == "12-month CPI inflation"
            assert rec["publisher"] == "Central Bank of Kenya"
            assert rec["source_url"] == cbk_inflation.CBK_INFLATION_URL

    def test_swapped_june_2024_row_is_withheld_not_published(self):
        result = cbk_inflation.parse_cbk_inflation(CBK_HTML)
        months = {r["reference_month"] for r in result.records}
        assert "2024-06" not in months
        reasons = dict(result.rejected)
        assert "columns likely swapped" in reasons["2024-06"]
        # Its neighbours are fine and published.
        assert {"2024-05", "2024-07"} <= months

    def test_the_withheld_set_is_exactly_the_swap_plus_unverifiable_2005(self):
        result = cbk_inflation.parse_cbk_inflation(CBK_HTML)
        assert sorted(m for m, _ in result.rejected) == [
            f"2005-{m:02d}" for m in range(1, 12)
        ] + ["2024-06"]
        assert len(result.records) == 260 - 12

    def test_columns_are_found_by_header_name_not_position(self):
        # Same four columns, reordered. A positional parser would publish the
        # Year column as the rate; the 12-month rate here is 7.0 throughout
        # and the annual average 6.0 — within tolerance of each other only if
        # read by name (mean of twelve 7.0s is 7.0, |6.0 - 7.0| = 1.0).
        months = [
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        ]
        body = "".join(
            f"<tr><td>7.00</td><td>{m}</td><td>{y}</td><td>6.50</td></tr>"
            for y, m in [(2025, m) for m in months] + [(2026, "January")]
        )
        html = (
            "<table><thead><tr><th>12-Month Inflation</th><th>Month</th>"
            "<th>Year</th><th>Annual Average Inflation</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )
        result = cbk_inflation.parse_cbk_inflation(html)
        assert [(r["reference_month"], r["value"], r["annual_average_pct"])
                for r in result.records] == [("2026-01", 7.0, 6.5), ("2025-12", 7.0, 6.5)]

    def test_renamed_table_fails_loudly(self):
        with pytest.raises(cbk_inflation.CbkTableNotFound):
            cbk_inflation.parse_cbk_inflation(
                CBK_HTML.replace("12-Month Inflation", "Headline")
            )


# ── The fetcher: provenance and supersession coverage ────────────────────


class TestFetcher:
    def setup_method(self):
        freshness.reset("economic_indicators")

    def test_both_sources_live(self):
        payload = fetcher.fetch_economic_payload(FakeClient(), SeedingSettings())
        types = {r["indicator_type"] for r in payload.records}
        assert "inflation_rate_12m" in types and "inflation_rate" in types
        assert "2026-08-31" in payload.coverage["inflation_rate_12m"]
        assert payload.coverage["inflation_rate"] == {
            "2023-12-31", "2024-12-31", "2025-12-31"
        }
        assert payload.errors == []
        rec = freshness.get("economic_indicators")
        assert rec["mode"] == "live"
        assert "CBK inflation: 248 month(s), newest 2026-08" in rec["detail"]

    def test_world_bank_rows_declare_world_bank(self):
        payload = fetcher.fetch_economic_payload(FakeClient(), SeedingSettings())
        wb = [r for r in payload.records if r["indicator_type"] == "inflation_rate"]
        assert wb and all(
            r["source_label"] == "World Bank, World Development Indicators"
            and r["measure"] == "CPI inflation, annual average"
            for r in wb
        )

    def test_cbk_down_is_a_run_error_not_silence(self):
        payload = fetcher.fetch_economic_payload(
            FakeClient(cbk=RuntimeError("503")), SeedingSettings()
        )
        assert payload.errors and "CBK inflation-rates fetch failed" in payload.errors[0]
        assert "inflation_rate_12m" not in payload.coverage
        assert "cbk_inflation=failed" in freshness.get("economic_indicators")["detail"]

    def test_world_bank_down_cbk_up_is_partial(self):
        payload = fetcher.fetch_economic_payload(
            FakeClient(wb={}), SeedingSettings()
        )
        assert freshness.get("economic_indicators")["mode"] == "partial"
        assert "inflation_rate_12m" in payload.coverage

    def test_fixture_row_of_another_measure_is_not_merged(self):
        base = [
            # The 12-month figure the fixture used to file under the World
            # Bank's annual-average key.
            {"indicator_type": "inflation_rate", "date": "2025-01-31", "value": 3.3},
            # Before the span the World Bank delivered: kept.
            {"indicator_type": "inflation_rate", "date": "2019-12-31", "value": 5.2},
        ]
        live = [
            {"indicator_type": "inflation_rate", "date": "2024-12-31", "value": 4.5},
            {"indicator_type": "inflation_rate", "date": "2025-12-31", "value": 4.1},
        ]
        merged = fetcher._merge_indicators(base, live)
        assert [(r["date"], r["value"]) for r in merged] == [
            ("2024-12-31", 4.5),
            ("2025-12-31", 4.1),
            ("2019-12-31", 5.2),
        ]


# ── The writer: publisher and supersession sweep ─────────────────────────


def _ind(kind, day, value, entity_id=None, meta=None):
    return EconomicIndicator(
        indicator_type=kind,
        indicator_date=datetime.fromisoformat(day),
        value=value,
        entity_id=entity_id,
        unit="percent",
        meta=meta or {},
    )


class TestSupersessionSweep:
    def test_removes_only_off_date_rows_in_covered_years(self, db_session, seed_country):
        county = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi",
            slug="nairobi",
        )
        db_session.add(county)
        db_session.flush()
        db_session.add_all(
            [
                _ind("inflation_rate", "2024-06-30", 4.6, meta={"bootstrap": True}),
                _ind("inflation_rate", "2025-01-31", 3.3),
                _ind("inflation_rate", "2025-12-31", 4.1),
                _ind("inflation_rate", "2019-12-31", 5.2),  # delivered
                _ind("inflation_rate", "2026-03-31", 5.0),  # after the span
                _ind("inflation_rate", "2025-03-31", 9.9, entity_id=county.id),
                _ind("gdp_growth_rate", "2025-06-30", 1.0),  # type not covered
            ]
        )
        db_session.flush()
        removed, errors = writer.remove_superseded_rows(
            db_session, {"inflation_rate": {"2019-12-31", "2024-12-31", "2025-12-31"}}
        )
        assert errors == []
        assert sorted(removed) == [
            ("inflation_rate", "2024-06-30", 4.6),
            ("inflation_rate", "2025-01-31", 3.3),
        ]
        db_session.flush()
        left = {
            (r.indicator_type, r.indicator_date.date().isoformat())
            for r in db_session.query(EconomicIndicator).all()
        }
        assert left == {
            ("inflation_rate", "2025-12-31"),
            ("inflation_rate", "2019-12-31"),
            ("inflation_rate", "2026-03-31"),
            ("inflation_rate", "2025-03-31"),
            ("gdp_growth_rate", "2025-06-30"),
        }

    def test_no_coverage_deletes_nothing(self, db_session, seed_country):
        db_session.add(_ind("inflation_rate", "2025-01-31", 3.3))
        db_session.flush()
        assert writer.remove_superseded_rows(db_session, {}) == ([], [])

    def test_a_truncated_page_does_not_condemn_the_rest_of_the_year(
        self, db_session, seed_country
    ):
        # CBK serves only its newest month: the months before it this year
        # are outside what was delivered, not contradicted by it.
        db_session.add_all(
            [_ind("inflation_rate_12m", f"2026-0{m}-28", 5.0) for m in range(1, 8)]
        )
        db_session.flush()
        removed, errors = writer.remove_superseded_rows(
            db_session, {"inflation_rate_12m": {"2026-08-31"}}
        )
        assert (removed, errors) == ([], [])

    def test_a_sweep_too_large_to_be_plausible_is_refused_and_reported(
        self, db_session, seed_country
    ):
        # A page serving 2005 and 2026 with many off-cycle rows in between
        # proposes more deletions than the cap allows. Refuse, and say so.
        db_session.add_all(
            [
                _ind("inflation_rate_12m", f"{y}-06-15", 5.0)
                for y in range(2010, 2024)
            ]
        )
        db_session.flush()
        removed, errors = writer.remove_superseded_rows(
            db_session, {"inflation_rate_12m": {"2005-12-31", "2026-08-31"}}
        )
        assert removed == []
        assert errors and "Refused to remove 14 superseded inflation_rate_12m" in errors[0]
        assert db_session.query(EconomicIndicator).count() == 14


# ── The whole domain, then the endpoint the strip reads ──────────────────


def test_domain_run_puts_august_2026_on_the_budget_strip(
    client, db_session, seed_country, monkeypatch
):
    import seeding.domains.economic_indicators as domain

    # What production holds today: the bootstrap literal and the fixture's
    # mismeasured 12-month row, both under the annual-average key.
    db_session.add_all(
        [
            _ind("inflation_rate", "2024-06-30", 4.6, meta={"bootstrap": True}),
            _ind("inflation_rate", "2025-01-31", 3.3),
        ]
    )
    db_session.commit()

    monkeypatch.setattr(domain, "create_http_client", lambda settings: FakeClient())
    freshness.reset("economic_indicators")
    result = domain.run(
        db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
    )
    db_session.commit()

    assert result.errors == []
    removed = {(r["date"], r["value"]) for r in result.metadata["superseded_rows_removed"]}
    assert {("2024-06-30", 4.6), ("2025-01-31", 3.3)} <= removed
    assert all(
        isinstance(r["id"], int) and isinstance(r["stored_value"], str)
        for r in result.metadata["superseded_rows_removed"]
    )
    assert "2025-12-31" in result.metadata["supersession_coverage"]["inflation_rate"]

    # World Bank source documents are no longer filed under KNBS.
    wb_doc = (
        db_session.query(SourceDocument)
        .filter(SourceDocument.url.like("%worldbank%FP.CPI.TOTL.ZG%"))
        .one()
    )
    assert wb_doc.publisher == "World Bank"

    ec = client.get("/api/v1/budget/enhanced").json()["economic_context"]
    assert ec["inflation_pct"] == 6.59
    assert ec["inflation_as_of"].startswith("2026-08-31")
    assert ec["inflation_source"] == "KNBS CPI, via Central Bank of Kenya"
    assert ec["inflation_measure"] == "12-month CPI inflation"
    assert ec["gdp_billion_kes"] == pytest.approx(17577.557)
    assert ec["gdp_as_of"].startswith("2025-12-31")
    assert ec["gdp_source"] == "World Bank, World Development Indicators"
    assert ec["gdp_growth_pct"] == 4.6
    assert ec["gdp_growth_as_of"].startswith("2025-12-31")
    assert ec["gdp_growth_source"] == "World Bank, World Development Indicators"


# ── The freshness gate ───────────────────────────────────────────────────


class TestSeriesFreshnessGate:
    NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)

    def _finding(self, db_session):
        from seeding.staleness import check_series_freshness

        (finding,) = [
            f
            for f in check_series_freshness(db_session, self.NOW)
            if "inflation" in f.label.lower()
        ]
        return finding

    def test_current_month_is_ok(self, db_session):
        db_session.add(_ind("inflation_rate_12m", "2026-08-31", 6.59))
        db_session.flush()
        assert self._finding(db_session).level == "OK"

    def test_a_missed_release_warns(self, db_session):
        db_session.add(_ind("inflation_rate_12m", "2026-07-15", 6.49))
        db_session.flush()
        f = self._finding(db_session)
        assert f.level == "WARN"
        assert "73 days old" in f.message

    def test_no_series_warns(self, db_session):
        assert self._finding(db_session).level == "WARN"

    def test_a_fresh_county_row_does_not_hide_a_stale_national_series(
        self, db_session, seed_country
    ):
        county = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Mombasa",
            slug="mombasa",
        )
        db_session.add(county)
        db_session.flush()
        db_session.add_all(
            [
                _ind("inflation_rate_12m", "2026-01-31", 4.4),
                _ind("inflation_rate_12m", "2026-08-31", 6.6, entity_id=county.id),
            ]
        )
        db_session.flush()
        assert self._finding(db_session).level == "WARN"

    def test_run_all_includes_it(self, db_session):
        from seeding.staleness import run_all

        labels = [f.label for f in run_all(db_session, now=self.NOW)]
        assert "Monthly inflation (CBK 12-month CPI)" in labels

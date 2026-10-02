"""#433: source numbers must be valid before rounding or scale conversion.

Transport is synthetic; parsing, registered handlers, CLI, transactions and
freshness gates are real. PostgreSQL fixtures require an owned loopback DB.
"""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import GDPData, IngestionJob, IngestionStatus, PovertyIndex, SourceDocument
from seeding import freshness
from seeding.domains import national_gdp as domain
from seeding.domains.national_gdp import fetcher
from seeding.staleness import check_ingestion_freshness, hollow_run_findings, OK, WARN, FAIL
from seeding.types import DomainRunContext
from test_national_gdp_failure_observability import invoke_cli, settings
from test_national_gdp_observation_identity import seed, http
from test_national_gdp_source_creation import pg, snapshot, country

GDP, HC, GINI = "NY.GDP.MKTP.CN", "SI.POV.NAHC", "SI.POV.GINI"
BAD_NUMBERS = [True, False, -1, -0.001, float("nan"), float("inf"),
               float("-inf"), "39", "NaN", [], {}, "invalid"]
BAD_PERCENT = BAD_NUMBERS + [100.001, Decimal("100.000000000000000000000001")]


def payload(value, year="2022"):
    return [{"pages": 1}, [{"date": year, "value": value}]]


class Publisher:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def get(self, url, **kwargs):
        indicator = url.split("/indicator/")[1].split("?")[0]
        value = self.overrides.get(indicator, {GDP: 18, HC: 39, GINI: 38.5}[indicator])
        response = payload(value, "2024" if indicator == GDP else "2022")
        return type("Response", (), {"json": lambda _: response})()


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_direct_gdp_parser_rejects_invalid_raw_value(value):
    with pytest.raises(ValueError):
        fetcher._parse_wb_gdp(payload(value, "2024"))


@pytest.mark.parametrize("value", BAD_PERCENT)
def test_direct_poverty_parser_rejects_invalid_raw_value(value):
    with pytest.raises(ValueError):
        fetcher._parse_wb_series(payload(value))


@pytest.mark.parametrize("parser", [fetcher._parse_wb_gdp, fetcher._parse_wb_series])
@pytest.mark.parametrize("response", [None, {}, [], [{}, None], [{}, {}],
    [{}, [None]], [{}, [1]], [{}, [{}]], [{}, [{"date": "2022"}]],
    [{}, [{"value": 1}]], [{}, [{"date": "bad", "value": 1}]]])
def test_malformed_source_shape_is_not_an_empty_observation(parser, response):
    with pytest.raises(ValueError):
        parser(response)


@pytest.mark.parametrize("parser", [fetcher._parse_wb_gdp, fetcher._parse_wb_series])
def test_absent_and_empty_observations_remain_absent(parser):
    assert parser([{}, []]) == {}
    assert parser(payload(None)) == {}


def test_valid_raw_precision_and_gdp_units():
    assert fetcher._parse_wb_gdp(payload(16_224_478_000_000, "2024")) == {2024: 16_224_478_000_000}
    assert fetcher._parse_wb_gdp(payload(18.6, "2024")) == {2024: 19}
    assert fetcher._parse_wb_gdp(payload(0)) == {2022: 0}
    # No invented GDP ceiling; this is parser behavior, not DB capacity.
    assert fetcher._parse_wb_gdp(payload(10**30)) == {2022: 10**30}
    assert fetcher._parse_wb_series(payload(39.876)) == {2022: 39.876}


@pytest.mark.parametrize("indicator", [HC, GINI])
@pytest.mark.parametrize("value", BAD_PERCENT)
def test_poverty_fetcher_refuses_before_normalization(tmp_path, indicator, value):
    with pytest.raises(ValueError):
        fetcher.fetch_kenya_poverty(Publisher({indicator: value}), settings(tmp_path))


@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_fixture_cannot_bypass_raw_gdp_validation(tmp_path, monkeypatch, value):
    monkeypatch.setattr(fetcher, "load_json_resource", lambda **kw: {"gdp": [{"year": 2024, "gdp_kes": value}]})
    cfg = settings(tmp_path)
    cfg.enrich_with_worldbank = False
    freshness.reset("national_gdp")
    with pytest.raises(ValueError):
        fetcher.fetch_national_gdp_kes(Publisher(), cfg)
    assert freshness.get("national_gdp").get("mode") != "live"


@pytest.mark.parametrize("value", [True, False, -0.001, float("nan")])
def test_invalid_live_gdp_uses_valid_fixture_with_honest_reason(tmp_path, monkeypatch, value):
    monkeypatch.setattr(fetcher, "load_json_resource", lambda **kw: {"gdp": [{"year": 2024, "gdp_kes": 17}]})
    freshness.reset("national_gdp")
    assert fetcher.fetch_national_gdp_kes(Publisher({GDP: value}), settings(tmp_path)) == {2024: 17}
    receipt = freshness.get("national_gdp")
    assert receipt["mode"] == "fixture"
    assert "invalid" in receipt["reason"]


def test_real_gdp_fixture_remains_valid_fallback(tmp_path):
    freshness.reset("national_gdp")
    result = fetcher.fetch_national_gdp_kes(Publisher({GDP: True}), settings(tmp_path))
    assert result[2024] == 16_224_478_000_000 and len(result) == 7
    assert freshness.get("national_gdp")["mode"] == "fixture"
    assert "invalid" in freshness.get("national_gdp")["reason"]


@pytest.mark.parametrize("overrides,expected", [
    ({HC: 39.876, GINI: 38.765}, {2022: {"headcount": Decimal("39.88"), "gini": Decimal("0.3876")}}),
    ({HC: 0, GINI: 0}, {2022: {"headcount": Decimal(0), "gini": Decimal(0)}}),
    ({HC: 100, GINI: 100}, {2022: {"headcount": Decimal(100), "gini": Decimal(1)}}),
    ({HC: None}, {2022: {"gini": Decimal("0.385")}}),
    ({GINI: None}, {2022: {"headcount": Decimal(39)}}),
    ({HC: None, GINI: None}, {}),
])
def test_poverty_fetcher_preserves_valid_precision_zero_and_absence(tmp_path, overrides, expected):
    assert fetcher.fetch_kenya_poverty(Publisher(overrides), settings(tmp_path)) == expected


INGESTION_BAD = [(GDP, True), (GDP, False), (GDP, -0.001),
                 (HC, True), (HC, False), (HC, -0.001), (HC, 100.001),
                 (GINI, True), (GINI, False), (GINI, -0.001), (GINI, 100.001),
                 (HC, float("nan")), (GINI, float("inf"))]


def observation_snapshot(db, table):
    return db.execute(text(f"SELECT row_to_json(r)::text FROM {table} r ORDER BY id")).scalars().all()


@pytest.mark.parametrize("overrides,gdp,headcount,gini", [
    ({}, 18, Decimal(39), Decimal("0.385")),
    ({GDP: 0, HC: 0, GINI: 0}, 0, Decimal(0), Decimal(0)),
    ({HC: None}, 18, None, Decimal("0.385")),
    ({GINI: None}, 18, Decimal(39), None),
    ({HC: None, GINI: None}, 18, Decimal("38.6"), Decimal("0.387")),
    ({GDP: 18.6, HC: 39.876, GINI: 38.765}, 19, Decimal("39.88"), Decimal("0.388")),
])
def test_cli_coherent_sparse_precision_and_zero_controls(pg, tmp_path, monkeypatch, overrides, gdp, headcount, gini):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(Publisher(overrides)))
    with Session(pg) as db:
        seed(db, poverty=True)
        docs = snapshot(db)
    assert invoke_cli(pg, tmp_path, monkeypatch) == 0
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.COMPLETED and not job.errors
        assert job.meta["source_mode"] == "live"
        assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == OK
        assert db.get(GDPData, 400).gdp_value == gdp
        row = db.get(PovertyIndex, 500)
        assert row.poverty_headcount_rate == headcount and row.gini_coefficient == gini
        assert row.extreme_poverty_rate is None
        assert snapshot(db) == docs


def test_raw_poverty_refusal_dry_run_keeps_observations_and_verdict(pg, tmp_path, monkeypatch):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(Publisher({GINI: 100.001})))
    with Session(pg) as db:
        seed(db, poverty=True)
        old_gdp = observation_snapshot(db, "gdp_data")
        old_poverty = observation_snapshot(db, "poverty_indices")
        docs = snapshot(db)
    assert invoke_cli(pg, tmp_path, monkeypatch, dry_run=True) == 0
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS and len(job.errors) == 1
        assert job.meta["source_mode"] == "partial" and job.meta["poverty_source"]["mode"] == "refused"
        assert observation_snapshot(db, "gdp_data") == old_gdp
        assert observation_snapshot(db, "poverty_indices") == old_poverty
        assert snapshot(db) == docs


@pytest.mark.parametrize("indicator,value", INGESTION_BAD)
def test_cli_commit_refuses_raw_number_keeps_valid_progress_and_retry(pg, tmp_path, monkeypatch, indicator, value):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(Publisher({indicator: value})))
    # An invalid fallback must not rescue invalid live GDP.
    monkeypatch.setattr(fetcher, "load_json_resource", lambda **kw: {"gdp": [{"year": 2024, "gdp_kes": True}]})
    with Session(pg) as db:
        seed(db, poverty=True)
        db.add(IngestionJob(domain="national_gdp", status=IngestionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc) - timedelta(days=1), dry_run=False,
            errors=[], meta={"source_mode": "live"}))
        db.commit()
        docs = snapshot(db)
        old = observation_snapshot(db, "gdp_data" if indicator == GDP else "poverty_indices")
    assert invoke_cli(pg, tmp_path, monkeypatch) == 0
    with Session(pg) as db:
        job = db.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS and len(job.errors) == 1
        assert job.meta["source_mode"] == "partial"
        assert job.meta["gdp_source" if indicator == GDP else "poverty_source"]["mode"] == "refused"
        assert observation_snapshot(db, "gdp_data" if indicator == GDP else "poverty_indices") == old
        assert snapshot(db) == docs
        assert db.query(GDPData).count() == db.query(PovertyIndex).count() == 1
        assert db.get(GDPData, 400).gdp_value == (17 if indicator == GDP else 18)
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("39" if indicator == GDP else "38.6")
        assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == WARN
        assert hollow_run_findings([job])[0].level == WARN
    # Public GDP sees the surviving valid value after commit/reopen.
    assert Decimal(str(http(pg)[0]["gdp_value"])) == (17 if indicator == GDP else 18)
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(Publisher()))
    assert invoke_cli(pg, tmp_path, monkeypatch) == 0
    with Session(pg) as db:
        job = db.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        assert job.status == IngestionStatus.COMPLETED and job.errors == []
        assert job.meta["source_mode"] == "live"
        assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == OK
        assert db.get(GDPData, 400).gdp_value == 18
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == 39
        assert snapshot(db) == docs


@pytest.mark.parametrize("direct", [False, True])
def test_total_raw_refusal_creates_no_invalid_source_or_observation(pg, tmp_path, monkeypatch, direct):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(Publisher({GDP: True, HC: -0.001})))
    monkeypatch.setattr(fetcher, "load_json_resource", lambda **kw: {"gdp": [{"year": 2024, "gdp_kes": False}]})
    with Session(pg) as db:
        db.add(country())
        db.commit()
        if direct:
            result = domain.run(db, settings(tmp_path), DomainRunContext(since=None, dry_run=False))
            assert len(result.errors) == 2 and result.items_created == result.items_updated == 0
            db.commit()
    if not direct:
        assert invoke_cli(pg, tmp_path, monkeypatch) == 0
    with Session(pg) as db:
        assert db.query(SourceDocument).count() == db.query(GDPData).count() == db.query(PovertyIndex).count() == 0
        assert freshness.get("national_gdp")["mode"] == "refused"
        if not direct:
            job = db.query(IngestionJob).one()
            assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS and len(job.errors) == 2
            assert job.meta["source_mode"] == "refused"
            assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == FAIL

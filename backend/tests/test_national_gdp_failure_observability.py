"""#137: source-shaped HTTP -> registered handler -> durable CLI job controls."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import httpx
from sqlalchemy.orm import Session, sessionmaker

from models import GDPData, IngestionJob, IngestionStatus, PovertyIndex, SourceDocument
from seeding import cli, freshness
from seeding.config import SeedingSettings
from seeding.domains import national_gdp as domain
from seeding.staleness import check_ingestion_freshness, hollow_run_findings, WARN, OK, FAIL
from seeding.types import DomainRunContext
from test_national_gdp_source_creation import pg, snapshot, country
from test_national_gdp_observation_identity import seed


class Publisher:
    """Stub transport only; execute the real World Bank parsers and fetchers."""
    def __init__(self, case="success", failed_indicator="SI.POV.GINI"):
        self.case = case
        self.failed_indicator = failed_indicator

    def get(self, url, **kwargs):
        indicator = url.split("/indicator/")[1].split("?")[0]
        if self.case in {"outage", "malformed"} and indicator == self.failed_indicator:
            if self.case == "outage":
                raise RuntimeError("owned synthetic provider outage")
            return httpx.Response(200, json={"unexpected": []}, headers={"content-type": "application/json"}, request=httpx.Request("GET", url))
        value = {"NY.GDP.MKTP.CN": 18, "SI.POV.NAHC": 39, "SI.POV.GINI": 38.5}[indicator]
        if indicator != "NY.GDP.MKTP.CN":
            if self.case == "empty" or (self.case == "missing" and indicator == "SI.POV.GINI"):
                value = None
            if self.case == "zero":
                value = 0
        payload = [{"page": 1, "pages": 1, "total": 1}, [{"indicator": {"id": indicator}, "countryiso3code": "KEN", "date": "2024" if indicator == "NY.GDP.MKTP.CN" else "2022", "value": value}]]
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"}, request=httpx.Request("GET", url))


def settings(tmp_path):
    return SeedingSettings(storage_path=tmp_path, cache_path=tmp_path,
                           http_cache_enabled=False, enrich_with_worldbank=True,
                           domain_timeout_seconds=60, total_timeout_seconds=0)


def install(monkeypatch, publisher):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(publisher))


@pytest.mark.parametrize("case", ["outage", "malformed"])
@pytest.mark.parametrize("indicator", ["SI.POV.NAHC", "SI.POV.GINI"])
def test_poverty_failure_is_visible_without_losing_valid_progress(pg, tmp_path, monkeypatch, case, indicator):
    install(monkeypatch, Publisher(case, indicator))
    freshness.reset("national_gdp")
    with Session(pg) as db:
        seed(db, poverty=True)
        before = snapshot(db)
        old_poverty = db.get(PovertyIndex, 500).meta.copy()
        result = domain.run(db, settings(tmp_path), DomainRunContext(since=None, dry_run=False))
        db.commit()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 18
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")
        assert db.get(PovertyIndex, 500).meta == old_poverty
        assert snapshot(db) == before
    assert result.items_updated == 1 and result.items_processed == 1
    assert len(result.errors) == 1 and result.errors[0].startswith("Poverty fetch failed:")
    assert result.metadata["poverty_source"]["mode"] == "refused"
    assert freshness.get("national_gdp")["mode"] == "partial"


@pytest.mark.parametrize("case", ["success", "missing", "empty", "zero"])
def test_coherent_sparse_empty_and_zero_are_successful_checks(pg, tmp_path, monkeypatch, case):
    install(monkeypatch, Publisher(case))
    freshness.reset("national_gdp")
    with Session(pg) as db:
        seed(db, poverty=True)
        result = domain.run(db, settings(tmp_path), DomainRunContext(since=None, dry_run=False))
        db.commit()
    assert result.errors == []
    assert result.metadata["poverty_source"]["mode"] == "live"
    assert result.metadata["poverty_source"]["observed_years"] == ([] if case == "empty" else [2022])
    assert freshness.get("national_gdp")["mode"] == "live"
    with Session(pg) as db:
        row = db.get(PovertyIndex, 500)
        assert row.poverty_headcount_rate == Decimal("38.6" if case == "empty" else "0" if case == "zero" else "39")
        assert row.gini_coefficient == (None if case == "missing" else Decimal("0" if case == "zero" else "0.387" if case == "empty" else "0.385"))
        repeat = domain.run(db, settings(tmp_path), DomainRunContext(since=None, dry_run=False))
        # New acquisitions append metadata receipts even when observed values hold.
        assert repeat.errors == [] and repeat.items_created == 0
        assert repeat.items_updated == (1 if case == "empty" else 2)
        db.commit()


def invoke_cli(pg, tmp_path, monkeypatch, dry_run=False):
    monkeypatch.setattr(cli, "SessionLocal", sessionmaker(bind=pg))
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    args = cli.build_parser().parse_args(["seed", "--domain", "national_gdp", "--dry-run" if dry_run else "--no-dry-run"])
    assert cli.REGISTRY.get("national_gdp") is domain.run
    return cli.run_seed_command(args, settings(tmp_path))


@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_persists_failure_and_freshness_then_retry_clears_it(pg, tmp_path, monkeypatch, dry_run):
    with Session(pg) as db:
        seed(db, poverty=True)
        db.add(IngestionJob(domain="national_gdp", status=IngestionStatus.COMPLETED,
                            started_at=datetime.now(timezone.utc) - timedelta(days=1),
                            dry_run=False, errors=[], meta={"source_mode": "live"}))
        db.commit()
    install(monkeypatch, Publisher("outage"))
    assert invoke_cli(pg, tmp_path, monkeypatch, dry_run) == 0  # existing partial-success exit contract
    with Session(pg) as db:
        job = db.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert job.errors[0].startswith("Poverty fetch failed:")
        assert job.meta["source_mode"] == "partial"
        assert job.meta["poverty_source"]["mode"] == "refused"
        run_findings = hollow_run_findings([job])
        assert len(run_findings) == 1 and run_findings[0].level == WARN
        assert "fixture" not in run_findings[0].message.lower()
        assert db.get(GDPData, 400).gdp_value == (17 if dry_run else 18)
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")
        findings = check_ingestion_freshness(db, domains=["national_gdp"])
        assert len(findings) == 1 and findings[0].level == WARN
        assert "poverty" in findings[0].message.lower()
    install(monkeypatch, Publisher())
    assert invoke_cli(pg, tmp_path, monkeypatch) == 0
    with Session(pg) as db:
        job = db.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        assert job.status == IngestionStatus.COMPLETED and job.errors == []
        assert job.meta["poverty_source"]["mode"] == "live"
        assert job.meta["source_mode"] == "live"
        assert db.get(GDPData, 400).gdp_value == 18
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == 39
        assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == OK


def test_gdp_failure_still_allows_valid_poverty(pg, tmp_path, monkeypatch):
    install(monkeypatch, Publisher("outage", "NY.GDP.MKTP.CN"))
    def no_fixture(**kwargs):
        raise RuntimeError("owned synthetic GDP fixture unavailable")
    monkeypatch.setattr(domain.fetcher, "load_json_resource", no_fixture)
    freshness.reset("national_gdp")
    with Session(pg) as db:
        seed(db, poverty=True)
        result = domain.run(db, settings(tmp_path), DomainRunContext(since=None, dry_run=False))
        db.commit()
    assert len(result.errors) == 1 and result.errors[0].startswith("GDP fetch failed:")
    assert freshness.get("national_gdp")["mode"] == "partial"
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 17
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == 39


@pytest.mark.parametrize("fixture", [False, True])
def test_both_providers_fail_or_gdp_uses_fixture(pg, tmp_path, monkeypatch, fixture):
    class FailedPublisher(Publisher):
        def get(self, url, **kwargs):
            raise RuntimeError("owned synthetic all-provider outage")
    install(monkeypatch, FailedPublisher())
    def fallback(**kwargs):
        if fixture:
            return {"gdp": [{"year": 2024, "gdp_kes": 18}]}
        raise ValueError("owned synthetic missing fixture")
    monkeypatch.setattr(domain.fetcher, "load_json_resource", fallback)
    with Session(pg) as db:
        seed(db, poverty=True)
    invoke_cli(pg, tmp_path, monkeypatch)
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert len(job.errors) == (1 if fixture else 2)
        assert job.meta["source_mode"] == ("fixture" if fixture else "refused")
        assert job.meta["poverty_source"]["mode"] == "refused"
        assert check_ingestion_freshness(db, domains=["national_gdp"])[0].level == (WARN if fixture else FAIL)
        assert db.get(GDPData, 400).gdp_value == (18 if fixture else 17)
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")


def test_late_poverty_authority_refusal_keeps_entire_savepoint_and_reports_refused(pg, tmp_path, monkeypatch):
    install(monkeypatch, Publisher())
    with Session(pg) as db:
        seed(db, poverty=True)
        row = db.get(PovertyIndex, 500)
        row.meta = {"scope": "county", "note": "preserve"}
        db.commit()
        before = snapshot(db)
    invoke_cli(pg, tmp_path, monkeypatch)
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.errors and job.items_created == job.items_updated == 0
        assert job.meta["source_mode"] == "refused"
        assert job.meta["source_fallback_reason"] == "domain_write_refused"
        assert snapshot(db) == before
        assert db.get(GDPData, 400).gdp_value == 17
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")


def test_dry_fixture_job_keeps_same_verdict_as_committed_job(pg, tmp_path, monkeypatch):
    install(monkeypatch, Publisher("outage", "NY.GDP.MKTP.CN"))
    monkeypatch.setattr(domain.fetcher, "load_json_resource", lambda **kw: {"gdp": [{"year": 2024, "gdp_kes": 18}]})
    with Session(pg) as db:
        seed(db, poverty=True)
    invoke_cli(pg, tmp_path, monkeypatch, dry_run=True)
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert len(job.errors) == 1 and "served from fixture" in job.errors[0]
        assert job.meta["source_mode"] == "fixture"
        assert job.meta["poverty_source"]["mode"] == "live"
        assert db.get(GDPData, 400).gdp_value == 17
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")


def test_total_fetch_refusal_creates_no_source_scaffold(pg, tmp_path, monkeypatch):
    class FailedPublisher(Publisher):
        def get(self, url, **kwargs):
            raise RuntimeError("owned synthetic all-provider outage")
    install(monkeypatch, FailedPublisher())
    def no_fixture(**kw):
        raise RuntimeError("owned synthetic missing fixture")
    monkeypatch.setattr(domain.fetcher, "load_json_resource", no_fixture)
    with Session(pg) as db:
        db.add(country())
        db.commit()
    invoke_cli(pg, tmp_path, monkeypatch)
    with Session(pg) as db:
        job = db.query(IngestionJob).one()
        assert job.meta["source_mode"] == "refused" and len(job.errors) == 2
        assert db.query(SourceDocument).count() == 0
        assert db.query(GDPData).count() == db.query(PovertyIndex).count() == 0

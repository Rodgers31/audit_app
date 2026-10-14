"""OAG previews plan discovery without claiming fixture or refreshed data."""
import argparse

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Audit, Base, Country, Extraction, IngestionJob, IngestionStatus, SourceDocument
from seeding import cli, freshness
from seeding.config import SeedingSettings
from seeding.domains import audits
from seeding.types import DomainRunContext
from test_audits_domain_county_ingest import DISCOVERY, NATIONAL, harness


PLAN = {
    "mode": "discovery_only",
    "extraction": "not_requested",
    "publication": "not_requested",
}


def national_success(_client, *, diagnostics):
    diagnostics.update(attempted_queries=3, successful_queries=3)
    return [NATIONAL]


def no_extraction(*_args, **_kwargs):
    pytest.fail("discovery-only preview attempted extraction or publication")


@pytest.fixture
def preview(harness, monkeypatch):
    monkeypatch.setattr(audits.fetcher, "_discover_audit_pdfs_via_wp_api", national_success)
    monkeypatch.setattr("seeding.fetch_documents.fetch_document", no_extraction)
    monkeypatch.setattr("seeding.extractors.get_parser", lambda _id: no_extraction)
    monkeypatch.setattr("seeding.domains.audits.loader.load_blue_book_extractions", no_extraction)
    freshness.reset("audits")
    yield harness
    freshness.reset("audits")


@pytest.mark.parametrize("prior", ["live", "fixture", "unknown"])
def test_actual_oag_preview_neither_uses_fixture_nor_certifies_fresh_data(preview, prior):
    if prior == "live":
        freshness.mark_live("audits", detail="previous invocation")
    elif prior == "fixture":
        freshness.mark_fixture("audits", reason="previous_invocation")
    session = preview["session"]
    before = [session.query(model).count() for model in (SourceDocument, Extraction, Audit)]

    result = audits.run(session, SeedingSettings(), DomainRunContext(since=None, dry_run=True))

    assert result.errors == []
    assert result.dry_run is True
    assert result.metadata.get("dry_run_plan") == PLAN
    assert freshness.get("audits") == {"mode": "unknown"}
    assert freshness.is_stale("audits") is True
    assert result.items_created == result.items_updated == result.items_processed == 0
    assert result.metadata["oag_national_discovery"]["successful_queries"] == 3
    assert any(NATIONAL in doc["candidates"] for doc in result.metadata["documents"])
    assert [session.query(model).count() for model in (SourceDocument, Extraction, Audit)] == before
    assert preview["fetched"] == preview["loads"] == []


@pytest.fixture
def native_cli(preview, tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'oag-preview.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as db:
        db.add(Country(name="Kenya", iso_code="KEN", currency="KES", timezone="Africa/Nairobi", default_locale="en-KE"))
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    yield factory
    engine.dispose()


@pytest.mark.parametrize("failure", [None, "county", "national", "both", "empty"])
def test_native_cli_records_preview_success_and_preserves_discovery_errors(native_cli, monkeypatch, failure):
    from seeding import oag_discovery as od

    if failure in ("county", "both", "empty"):
        discovery = od.CountyAuditDiscovery(
            documents=[] if failure == "empty" else DISCOVERY.documents,
            errors=[] if failure == "empty" else ["synthetic county listing unavailable"],
        )
        monkeypatch.setattr(od, "discover_county_audit_documents", lambda _client: discovery)
    if failure in ("national", "both"):
        def unavailable(_client, **_kwargs):
            raise RuntimeError("synthetic national search unavailable")
        monkeypatch.setattr(audits.fetcher, "_discover_audit_pdfs_via_wp_api", unavailable)
    elif failure == "empty":
        def empty(_client, *, diagnostics):
            diagnostics.update(attempted_queries=3, successful_queries=3)
            return []
        monkeypatch.setattr(audits.fetcher, "_discover_audit_pdfs_via_wp_api", empty)

    args = argparse.Namespace(domain=["audits"], all=False, dry_run=True, since=None)
    assert cli.run_seed_command(args, SeedingSettings(log_path=None, total_timeout_seconds=0)) == 0
    with native_cli() as db:
        job = db.scalars(select(IngestionJob)).one()
        assert job.status == (IngestionStatus.COMPLETED_WITH_ERRORS if failure in ("county", "national", "both") else IngestionStatus.COMPLETED)
        assert job.dry_run is True and job.finished_at is not None
        assert job.meta.get("dry_run_plan") == PLAN
        assert job.meta["source_mode"] == "unknown"
        assert "source_fallback_reason" not in job.meta
        assert not any("served from fixture" in error for error in job.errors)
        assert bool(job.errors) is (failure in ("county", "national", "both"))
        if failure in ("county", "both"):
            assert any("synthetic county listing unavailable" in error for error in job.errors)
        if failure in ("national", "both"):
            assert any("synthetic national search unavailable" in error for error in job.errors)
        assert db.query(SourceDocument).count() == db.query(Extraction).count() == db.query(Audit).count() == 0


def test_real_non_dry_no_extraction_still_records_fixture_failure(native_cli, monkeypatch):
    from seeding import oag_discovery as od

    monkeypatch.setattr(od, "discover_county_audit_documents", lambda _client: od.CountyAuditDiscovery())
    monkeypatch.setattr(audits, "_known_document_urls", lambda *_args: [])
    monkeypatch.setattr(audits.fetcher, "_discover_audit_pdfs_via_wp_api", lambda *_args, **_kwargs: [])
    args = argparse.Namespace(domain=["audits"], all=False, dry_run=False, since=None)
    cli.run_seed_command(args, SeedingSettings(log_path=None, total_timeout_seconds=0))
    with native_cli() as db:
        job = db.scalars(select(IngestionJob)).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert job.meta["source_mode"] == "fixture"
        assert job.meta["source_fallback_reason"] == "no_document_extracted"
        assert "dry_run_plan" not in job.meta
        assert any("served from fixture" in error for error in job.errors)

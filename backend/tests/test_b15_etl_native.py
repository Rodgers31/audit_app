"""Actual API -> dispatch -> native CLI -> Treasury parser/writer on PostgreSQL."""
from contextlib import nullcontext
import os
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

import database
import supabase_auth
from admin_etl_dispatch_adapter import execute
from admin_etl_dispatch_worker import claim, finish, heartbeat, register_worker
from models import BudgetLine, Country, Entity, EntityType, EtlDispatchWorker, FiscalSummary, IngestionJob, IngestionStatus, SeedingDomainClaim
from routers import etl_admin, admin
from seeding.domains import fiscal_summary
from seeding.freshness import mark_live
from services import trust_guards
from seeding import generation_dispatch
from seeding.domains import counties_budget

from b15_etl_fixture import postgres


@pytest.fixture(scope="module")
def pg():
    with postgres() as value:
        with value[0].begin() as db:
            db.add(Country(iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en"))
        yield value


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("guard_failure", [True, False])
def test_real_treasury_chain_preserves_terminal_failure_and_effects(pg, monkeypatch, dry_run, guard_failure):
    factory, engine = pg
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", "treasury")
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("inert@example.invalid", ["admin"]))
    monkeypatch.setattr(fiscal_summary, "create_http_client", lambda settings: nullcontext(None))
    payload = {"metadata": {"source": "B15 inert native control"}, "fiscal_years": [{
        "fiscal_year": "FY 2025/26", "appropriated_budget": 4000,
        "total_revenue": 3000, "tax_revenue": 2800, "non_tax_revenue": 200,
        "recurrent_spending": 2500, "development_spending": 1000,
    }]}
    def fetch(*args):
        mark_live("fiscal_summary", detail="Sanitized bounded fixture; no publisher request")
        return payload
    monkeypatch.setattr(fiscal_summary.fetcher, "fetch_fiscal_summary_payload", fetch)
    if guard_failure:
        def broken(record):
            raise RuntimeError("private diagnostics")
        monkeypatch.setattr(trust_guards, "check_fiscal_summary", broken)
    app = FastAPI()
    app.include_router(etl_admin.router)
    with factory() as db:
        worker = db.get(EtlDispatchWorker, 1)
        generation = worker.generation if worker else None
        before = [(r.fiscal_year, r.appropriated_budget) for r in db.scalars(select(FiscalSummary))]
    if generation is None:
        generation = register_worker(factory)
    else:
        assert heartbeat(factory, generation)
    headers = {"Authorization": "Bearer inert", "Idempotency-Key": str(uuid4())}
    with TestClient(app) as client:
        accepted = client.post("/api/v1/admin/etl/trigger/treasury", headers=headers,
                               json={"dry_run": dry_run, "dispatch_generation": str(generation)})
        assert accepted.status_code == 202, accepted.text
        command_id = UUID(accepted.json()["command"]["id"])
        owned = claim(factory, generation)
        assert owned[0] == command_id
        code = execute(factory, engine, *owned, generation)
        assert code == (1 if guard_failure else 0)
        assert heartbeat(factory, generation)
        assert finish(factory, generation, *owned, code)
        final = client.get(f"/api/v1/admin/etl/commands/{command_id}", headers=headers)
        assert final.status_code == 200
        assert final.json()["status"] == ("failed" if guard_failure else "completed")
        with factory() as db:
            job = db.get(IngestionJob, final.json()["job_id"])
            assert job.status == (IngestionStatus.FAILED if guard_failure else IngestionStatus.COMPLETED)
            assert job.dry_run is dry_run
            assert job.meta["dispatch_command_id"] == str(command_id)
            assert job.meta["dispatch_claim_token"] == str(owned[1])
            assert db.get(SeedingDomainClaim, owned[1]).released_at is not None
            rows = db.scalars(select(FiscalSummary)).all()
            if guard_failure or dry_run:
                assert [(r.fiscal_year, r.appropriated_budget) for r in rows] == before
            else:
                assert len(rows) == 1
                assert float(rows[0].appropriated_budget) == 4_000_000_000_000


@pytest.mark.parametrize("mode", ["disabled", "ineligible", "failed", "malformed_flag", "dry_run", "timed_out", "bad_result", "source_exception"])
def test_native_cob_commit_precedes_generation_and_preserves_outcomes(pg, monkeypatch, mode):
    factory, engine = pg
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", "cob,treasury")
    monkeypatch.setenv("SOCIAL_GENERATION_HOOK_ENABLED", "false" if mode == "disabled" else "TRUE" if mode == "malformed_flag" else "true")
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("inert@example.invalid", ["admin"]))
    slug = "inert-" + uuid4().hex
    with factory.begin() as db:
        kenya = db.scalar(select(Country).where(Country.iso_code == "KEN"))
        db.add(Entity(country_id=kenya.id, type=EntityType.COUNTY, slug=slug, canonical_name="Nairobi County"))
    monkeypatch.setattr(counties_budget, "create_http_client", lambda settings: nullcontext(None))
    def fetch(*args):
        mark_live("counties_budget", detail="Sanitized native parser/writer fixture")
        return [{"entity_slug": slug, "entity": "Nairobi County", "period_label": "FY2025/26",
                 "start_date": "2025-07-01", "end_date": "2026-06-30", "category": "Total",
                 "allocated_amount": 1000000, "actual_amount": 0, "data_quality": "official",
                 "source_url": "https://cob.go.ke/" + slug + ".pdf", "page_ref": "PDF p.7"}]
    monkeypatch.setattr(counties_budget.fetcher, "fetch_budget_payload", fetch)
    calls = []
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS b15_generation_effects(job_id integer)"))
    def hook(actual_factory, ids, ingestion_id):
        with actual_factory() as db:
            job = db.get(IngestionJob, ingestion_id)
            assert job.status == IngestionStatus.COMPLETED and job.dry_run is False
            assert ids and all(db.get(BudgetLine, id).actual_spent == 0 for id in ids)
        calls.append(ids)
        if mode in ("failed", "timed_out", "source_exception"):
            with actual_factory.begin() as db:
                db.execute(text("INSERT INTO b15_generation_effects VALUES (:job)"), {"job": ingestion_id})
        if mode == "timed_out":
            import time
            time.sleep(5)
        if mode == "failed":
            raise RuntimeError("inert generation failure after commit")
        if mode == "source_exception":
            from seeding.source_observations import SourceObservationUnavailable
            raise SourceObservationUnavailable("inert late refusal after a committed generation record")
        return {"state": "completed" if mode == "bad_result" else "unavailable", "reason": "SOURCE_EVIDENCE_INELIGIBLE", "processed": len(ids),
                "drafts_created": 0, "baselines": 0, "unchanged": 0, "refused": len(ids)}
    monkeypatch.setattr(generation_dispatch, "_invoke", hook)
    if mode == "timed_out":
        from seeding import cli
        from seeding.generation_limits import generation_envelope_seconds
        envelope = generation_envelope_seconds('counties_budget',
            include_reports=os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED','false') != 'false')
        original = cli._domain_timeout
        monkeypatch.setattr(cli, "_domain_timeout", lambda seconds: original(1 if seconds == envelope else seconds))
    with factory() as db:
        worker = db.get(EtlDispatchWorker, 1)
        generation = worker.generation if worker else None
    generation = generation or register_worker(factory)
    assert heartbeat(factory, generation)
    app = FastAPI(); app.include_router(etl_admin.router); app.include_router(admin.router)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer inert", "Idempotency-Key": str(uuid4())}
        accepted = client.post("/api/v1/admin/etl/trigger/cob", headers=headers,
                               json={"dry_run": mode == "dry_run", "dispatch_generation": str(generation)})
        assert accepted.status_code == 202, accepted.text
        owned = claim(factory, generation)
        assert execute(factory, engine, *owned, generation) == 0
        assert finish(factory, generation, *owned, 0)
        final = client.get(f"/api/v1/admin/etl/commands/{owned[0]}", headers=headers).json()
        assert final["status"] == "completed"
        with factory() as db:
            job = db.get(IngestionJob, final["job_id"])
            assert job.status == IngestionStatus.COMPLETED
            if mode in ("disabled", "dry_run"):
                assert not calls
                skipped = job.meta['post_commit_generation']
                assert skipped['state'] == ('disabled' if mode == 'disabled' else 'unavailable')
                assert skipped['reason'] == ('environment_disabled' if mode == 'disabled' else 'ingestion_not_eligible')
                assert skipped['processed'] == 0
            else:
                receipt = job.meta["post_commit_generation"]
                uncertain = mode in ("failed", "timed_out", "bad_result", "source_exception")
                assert receipt["state"] == ("failed" if uncertain else "unavailable")
                assert receipt["reason"] == ("invalid_generation_hook_flag" if mode == "malformed_flag" else "generation_timeout_execution_unverified" if mode == "timed_out" else "generation_execution_unverified" if uncertain else "SOURCE_EVIDENCE_INELIGIBLE")
                if uncertain:
                    assert receipt["execution_unverified"] is True
                    assert receipt["processed"] is None and receipt["drafts_created"] is None
                if mode in ("failed", "timed_out", "source_exception"):
                    assert db.scalar(text("SELECT count(*) FROM b15_generation_effects WHERE job_id=:id"), {"id": job.id}) == 1
                assert len(calls) == (0 if mode == "malformed_flag" else 1)
        detail = client.get(f"/api/v1/admin/ingestion-jobs/{final['job_id']}", headers=headers)
        assert detail.status_code == 200, detail.text
        if mode not in ("disabled", "dry_run"):
            public = detail.json()["metadata"]["post_commit_generation"]
            assert public["state"] == ("failed" if mode in ("failed", "timed_out", "bad_result", "source_exception") else "unavailable")
            assert public["reason"] == receipt["reason"].lower()

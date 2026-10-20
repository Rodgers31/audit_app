"""Owned PostgreSQL + actual PDF/parser/writer + integrated generation code.

Sanitized captured-response fixtures prove code, never real publisher acceptance.
No provider call, post publication, upload or production credential is used.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
from social.generation.contracts import GenerationControlsCommand
from social.generation.service import GenerationService
from social.generation.models import SourceEvent
from social.models import SocialPost, SocialPublication
from social.service import SocialService

from models import BudgetLine, Country, Entity, EntityType, IngestionJob, IngestionStatus, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.counties_budget.writer import persist_budget_records
from seeding.generation_dispatch import dispatch_committed_generation
from seeding.source_observations import read_county_budget_record_ids, read_county_budget_observation, SourceObservationUnavailable
from seeding.types import DomainRunContext
from test_cob_publication_producer import acquired

IMAGE = 'sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
PORT = 55424
URL = 'postgresql+psycopg2://b15_cobq:inert-owned-control@127.0.0.1:55424/b15_cobq'


@contextmanager
def owned_postgres():
    if any(k.startswith('PG') for k in os.environ):
        raise RuntimeError('Ambient PostgreSQL redirects refused')
    name = 'b15-cobq-' + uuid4().hex
    def docker(*args):
        return subprocess.check_output(['docker', *args], text=True, timeout=45).strip()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', PORT))
    docker('image', 'inspect', IMAGE)
    created, engine = False, None
    try:
        docker('run', '--pull=never', '-d', '--name', name,
            '-p', f'127.0.0.1:{PORT}:5432', '--tmpfs', '/var/lib/postgresql/data',
            '-e', 'POSTGRES_USER=b15_cobq', '-e', 'POSTGRES_PASSWORD=inert-owned-control',
            '-e', 'POSTGRES_DB=b15_cobq', IMAGE)
        created = True
        engine = create_engine(URL, connect_args={'connect_timeout': 2})
        deadline = time.monotonic() + 25
        while True:
            try:
                with engine.connect() as db:
                    if tuple(db.execute(text('SELECT current_database(),current_user')).one()) != ('b15_cobq', 'b15_cobq'):
                        raise RuntimeError('Owned fixture identity mismatch')
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(.1)
        env = {'PATH': os.environ['PATH'], 'PYTHONPATH': str(BACKEND_ROOT),
            'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'DATABASE_URL': URL}
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND_ROOT,
            env=env, check=True, timeout=90, capture_output=True)
        yield sessionmaker(bind=engine, expire_on_commit=False), engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            docker('rm', '-f', name)
            if docker('ps', '-aq', '--filter', 'name=^/' + name + '$'):
                raise RuntimeError('Owned PostgreSQL cleanup incomplete')
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', PORT))


@pytest.fixture(scope='module')
def pg():
    with owned_postgres() as value:
        yield value


def setup(factory):
    with factory.begin() as db:
        db.execute(text('TRUNCATE TABLE countries RESTART IDENTITY CASCADE'))
        db.execute(text('TRUNCATE TABLE social_generation_controls CASCADE'))
        country = Country(iso_code='KEN', name='Kenya', currency='KES', timezone='Africa/Nairobi', default_locale='en')
        db.add(country); db.flush()
        for name in ('Nairobi', 'Mombasa', 'Kisumu'):
            db.add(Entity(country_id=country.id, type=EntityType.COUNTY,
                canonical_name=('Nairobi City County' if name == 'Nairobi' else name + ' County'),
                slug=name.lower() + '-county'))
    with factory() as db:
        svc = SocialService(db)
        body = GenerationControlsCommand(expected_version=1, drafts_enabled=True, shadow_enabled=False,
            source_allowlist=['cob'], targets=[], reason='Owned end-to-end producer control')
        svc.command(actor=uuid4(), route='coordinator-fixture', key=uuid4(), body=body.model_dump(mode='json'),
            request_id=uuid4(), action=lambda: GenerationService(svc).set_controls(body), status=200)


def ingest(factory, tmp_path, *, amount='0', label='Publication date: 2026-07-01', enabled=True, mutate=None):
    _, _, records, _, _ = acquired(tmp_path, actual=amount, label=label)
    if mutate:
        mutate(records)
    settings = SeedingSettings(storage_path=tmp_path/'store', cache_path=tmp_path/'cache',
        log_path=tmp_path/'logs/seed.log', cob_verified_qualification_enabled=enabled)
    with factory.begin() as db:
        job = IngestionJob(domain='counties_budget', status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode': 'live'})
        db.add(job); db.flush()
        stats = persist_budget_records(db, records, settings, DomainRunContext(None, False, job.id))
        assert not stats.errors
        job.status = IngestionStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job.meta = {**job.meta, 'verified_qualification': getattr(stats, 'qualification', {'state': 'not_implemented'})}
        job_id = job.id
    return job_id, stats


def test_actual_pdf_writer_two_ingestions_generate_then_replay(pg, tmp_path, monkeypatch):
    factory, _ = pg
    setup(factory)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    first, stats = ingest(factory, tmp_path)
    with factory() as db:
        assert all(db.scalars(select(BudgetLine.publishable))), 'Actual producer rows must be explicitly qualified'
    assert stats.qualification['qualified'] == 3
    result = dispatch_committed_generation(factory, domain='counties_budget', ingestion_id=first, dry_run=False)
    assert result['state'] == 'completed' and result['baselines'] == 3
    second, stats = ingest(factory, tmp_path, amount='1.25')
    assert stats.qualification['qualified'] == 3
    result = dispatch_committed_generation(factory, domain='counties_budget', ingestion_id=second, dry_run=False)
    assert result['state'] == 'completed' and result['drafts_created'] == 3, result
    third, stats = ingest(factory, tmp_path, amount='1.25')
    assert stats.qualification['qualified'] == 3
    for _ in range(2):
        result = dispatch_committed_generation(factory, domain='counties_budget', ingestion_id=third, dry_run=False)
        assert result['state'] == 'completed' and result['unchanged'] == 3, result
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceEvent)) == 3
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 3
        assert set(db.scalars(select(SocialPost.editorial_state))) == {'pending_review'}
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
        assert all(len(row.provenance) == 3 for row in db.scalars(select(BudgetLine)))
    for record in read_county_budget_record_ids(factory, ingestion_id=first):
        with pytest.raises(SourceObservationUnavailable):
            read_county_budget_observation(factory, record_id=record, ingestion_id=first)


def test_changed_records_require_explicit_qualification_and_source_identity(pg, tmp_path):
    factory, _ = pg
    setup(factory)
    ingest(factory, tmp_path)
    _, same = ingest(factory, tmp_path, enabled=False)
    assert same.qualification['withheld'] == 0
    with factory() as db:
        assert all(db.scalars(select(BudgetLine.publishable)))
    _, stats = ingest(factory, tmp_path, amount='1.25', enabled=False)
    assert stats.qualification['reasons'] == {'changed_qualification_disabled': 3}
    with factory() as db:
        assert not any(db.scalars(select(BudgetLine.publishable)))


@pytest.mark.parametrize('mode', ['disabled', 'missing_date', 'json_forgery', 'mutated_date', 'changed_receipt', 'quarantine', 'plain_false_hold'])
def test_writer_never_promotes_ineligible_or_existing_holds(pg, tmp_path, mode):
    factory, _ = pg
    setup(factory)
    mutate = None
    if mode == 'json_forgery':
        def mutate(records):
            for row in records:
                row.publication_evidence = dict(row.publication_evidence.value)
    if mode == 'mutated_date':
        def mutate(records):
            for row in records:
                row.publication_evidence.value['publication_date'] = '2026-06-30'
    if mode == 'changed_receipt':
        def mutate(records):
            for row in records:
                row.publication_evidence.receipt['request_url'] = 'https://cob.go.ke/unrelated.pdf'
    job, stats = ingest(factory, tmp_path, enabled=mode != 'disabled',
        label='September 2026' if mode == 'missing_date' else 'Publication date: 2026-07-01', mutate=mutate)
    if mode in ('quarantine', 'plain_false_hold'):
        with factory.begin() as db:
            for row in db.scalars(select(BudgetLine)):
                row.publishable = False
                row.quarantine_reason = 'manual-review-hold' if mode == 'quarantine' else None
        job, stats = ingest(factory, tmp_path, amount='1.25')
        assert stats.qualification['reasons'] == {'existing_publication_hold': 3}
    with factory() as db:
        assert not any(db.scalars(select(BudgetLine.publishable)))
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    for record in read_county_budget_record_ids(factory, ingestion_id=job):
        with pytest.raises(SourceObservationUnavailable):
            read_county_budget_observation(factory, record_id=record, ingestion_id=job)


@pytest.mark.parametrize('mode', ['ambiguous_lineage', 'wrong_artifact', 'date_receipt_missing', 'wrong_date_artifact'])
def test_committed_reader_refuses_ambiguous_or_nonmatching_lineage(pg, tmp_path, mode):
    from copy import deepcopy
    factory, _ = pg
    setup(factory)
    job, _ = ingest(factory, tmp_path)
    ids = read_county_budget_record_ids(factory, ingestion_id=job)
    with factory.begin() as db:
        for row in db.scalars(select(BudgetLine)):
            if mode == 'ambiguous_lineage':
                row.provenance = [*row.provenance, deepcopy(row.provenance[0])]
            elif mode == 'wrong_artifact':
                provenance = deepcopy(row.provenance)
                provenance[0]['artifact_sha256'] = 'a' * 64
                row.provenance = provenance
            else:
                doc = db.get(SourceDocument, row.source_document_id)
                meta = deepcopy(doc.meta)
                if mode == 'date_receipt_missing':
                    meta['publication_date_evidence']['extraction_id'] = 2147483647
                else:
                    meta['publication_date_evidence']['digest'] = 'a' * 64
                doc.meta = meta
    for record in ids:
        with pytest.raises(SourceObservationUnavailable):
            read_county_budget_observation(factory, record_id=record, ingestion_id=job)

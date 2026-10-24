"""Executed projection/semantic controls; PostgreSQL is an owned opt-in fixture.

B66_QUERY_POSTGRES=1 uses ONLY b66_queries on loopback:56971 (no DSN input).
No provider connection, object storage, media inspector, or social writer runs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
import importlib
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import MetaData, create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import database
import main
from models import (
    Base, Country, DebtCategory, DocumentType, EconomicIndicator, Entity,
    EntityType, Loan, PopulationData, SourceDocument,
)
from social.media.config import MediaConfig
from social.media.contracts import MediaLibrary
from social.media.models import SocialMediaUpload
from social.media.service import MediaService
from social.models import SocialMediaAsset
from social.service import SocialError


@pytest.fixture(params=['sqlite', 'postgresql'])
def compact_db(request, tmp_path):
    if request.param == 'postgresql':
        if os.environ.get('B66_QUERY_POSTGRES') != '1':
            pytest.skip('Owned PostgreSQL: B66_QUERY_POSTGRES=1, b66_queries on 127.0.0.1:56971')
        admin = create_engine('postgresql+psycopg2://postgres@127.0.0.1:56971/b66_queries', pool_size=1, max_overflow=0,
                              connect_args={'hostaddr': '127.0.0.1', 'connect_timeout': 3})
        schema = 'b66_queries_' + uuid4().hex
        with admin.begin() as conn:
            assert conn.scalar(text('SELECT current_database()')) == 'b66_queries'
            conn.execute(text('CREATE SCHEMA ' + schema))
        engine = create_engine(admin.url, pool_size=2, max_overflow=0,
                               connect_args={'hostaddr': '127.0.0.1', 'options': '-csearch_path=' + schema})
    else:
        admin, schema = None, None
        engine = create_engine('sqlite:///' + str(tmp_path / 'compact.sqlite'))
    try:
        # Historical nullable-date control; relax ONLY the disposable schema.
        metadata = MetaData()
        needed = {Entity.__table__, PopulationData.__table__, EconomicIndicator.__table__,
                  Loan.__table__, SourceDocument.__table__, SocialMediaAsset.__table__,
                  SocialMediaUpload.__table__}
        while True:
            parents = {fk.column.table for table in needed for fk in table.foreign_keys}
            if parents <= needed:
                break
            needed |= parents
        for table in Base.metadata.sorted_tables:
            if table in needed:
                table.to_metadata(metadata)
        metadata.tables['economic_indicators'].c.indicator_date.nullable = True
        metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        if admin is not None:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
            admin.dispose()


@contextmanager
def capture(engine):
    """Capture real DBAPI columns and SQL, including unexpected lazy loads."""
    records = []
    def after(conn, cursor, statement, parameters, context, executemany):
        if cursor.description:
            records.append({'sql': statement, 'parameters': parameters,
                            'columns': [c[0] for c in cursor.description]})
    event.listen(engine, 'after_cursor_execute', after)
    try:
        yield records
    finally:
        event.remove(engine, 'after_cursor_execute', after)


def selected_value_bytes(engine, records):
    """Replay captured synthetic SELECTs; not protocol or provider bytes."""
    total = 0
    with engine.connect() as conn:
        cursor = conn.connection.driver_connection.cursor()
        try:
            for record in records:
                cursor.execute(record['sql'], record['parameters'])
                total += sum(len(str(v).encode()) for row in cursor.fetchall() for v in row if v is not None)
        finally:
            cursor.close()
    return total


@pytest.fixture
def snapshot_runtime(compact_db, monkeypatch):
    seeder = importlib.import_module('services.auto_seeder')
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=compact_db))
    monkeypatch.setattr(seeder, 'get_seeder_status', lambda: {'is_running': False})
    real_import = main.importlib.import_module
    monkeypatch.setattr(main.importlib, 'import_module', lambda name: SimpleNamespace() if name == 'etl.kenya_pipeline' else real_import(name))
    return compact_db


def seed_snapshot(engine, nullable_date=False):
    with Session(engine) as db:
        country = Country(name='Synthetic country', iso_code='ZZZ', currency='ZZZ', timezone='UTC', default_locale='en')
        db.add(country); db.flush()
        entities = [Entity(country_id=country.id, type=t, canonical_name=str(i), slug='b66-' + str(i),
                           meta={'unused': 'e' * 65536}) for i, t in enumerate([EntityType.COUNTY, EntityType.NATIONAL])]
        db.add_all(entities); db.flush()
        doc = SourceDocument(country_id=country.id, publisher='inert', title='synthetic',
                             fetch_date=datetime(2025, 1, 1), doc_type=DocumentType.REPORT, meta={'unused': 'd' * 65536})
        db.add(doc); db.flush()
        db.add_all([PopulationData(year=y, total_population=1, meta={'unused': 'p' * 65536}) for y in [0, 2025, 2025]])
        db.add_all([EconomicIndicator(indicator_type='inert', indicator_date=d, value=0,
                                     meta={'unused': 'x' * 65536}) for d in [datetime(2024, 1, 1), datetime(2026, 1, 1)] + ([None] if nullable_date else [])])
        for i, category in enumerate([DebtCategory.OTHER, DebtCategory.OTHER, None]):
            # Explicit SQL NULL bypasses the ORM's OTHER insert default.
            db.add(Loan(entity_id=entities[0].id, source_document_id=doc.id, lender=str(i),
                        debt_category=category if category else text('NULL'), principal=0, outstanding=0,
                        issue_date=datetime(2025, 1, 1), currency='ZZZ'))
        db.commit()


def legacy_stats(db):
    """Frozen query contract, including DESC NULL ordering and DISTINCT NULL."""
    national = db.query(Entity).filter(Entity.type == EntityType.NATIONAL).first()
    pop = db.query(PopulationData).order_by(PopulationData.year.desc()).first()
    econ = db.query(EconomicIndicator).order_by(EconomicIndicator.indicator_date.desc()).first()
    return {'entities': {'total': db.query(Entity).count(), 'counties': db.query(Entity).filter(Entity.type == EntityType.COUNTY).count(), 'has_national': national is not None},
            'population': {'records': db.query(PopulationData).count(), 'latest_year': pop.year if pop else None},
            'economic_indicators': {'records': db.query(EconomicIndicator).count(), 'latest_year': econ.indicator_date.year if econ and econ.indicator_date else None},
            'debt_categories': {'records': db.query(Loan.debt_category).distinct().count()},
            'loans': {'records': db.query(Loan).count()}, 'source_documents': {'records': db.query(SourceDocument).count()}}


@pytest.mark.parametrize('shape', ['empty', 'populated', 'null_date'])
def test_snapshot_complete_semantics_and_compact_sql(snapshot_runtime, shape):
    engine = snapshot_runtime
    if shape != 'empty':
        seed_snapshot(engine, nullable_date=shape == 'null_date')
    with capture(engine) as old_sql, Session(engine) as db:
        expected = legacy_stats(db)
    with capture(engine) as sql:
        actual = main._pipeline_health_snapshot()
    assert actual['database'] == expected
    if shape != 'empty':
        assert expected['debt_categories']['records'] == 2  # includes NULL
        assert expected['population']['latest_year'] == 2025
        if shape == 'null_date' and engine.dialect.name == 'postgresql':
            assert expected['economic_indicators']['latest_year'] is None
    assert len(old_sql) == 10, 'reference query observation channel must be alive'
    assert len(sql) == 1, f'cold snapshot requires {len(sql)} SQL round trips'
    assert all('metadata' not in r['sql'] for r in sql)
    assert all('provenance' not in r['sql'] for r in sql)
    assert len(sql[0]['columns']) == 10
    if shape != 'empty':
        assert selected_value_bytes(engine, sql) < selected_value_bytes(engine, old_sql) / 100
    if shape == 'empty':
        assert len(actual['alerts']) == 4
        assert all(a['level'] == 'warning' for a in actual['alerts'])


def test_snapshot_database_errors_are_not_empty_success(snapshot_runtime):
    engine = snapshot_runtime
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE population_data' + (' CASCADE' if engine.dialect.name == 'postgresql' else '')))
    answer = main._pipeline_health_snapshot()
    assert answer['database'] == {}
    assert any(a['level'] == 'error' and a['source'] == 'database' for a in answer['alerts'])


def asset(i, **updates):
    values = dict(id=UUID(int=i), storage_provider='inert', bucket='inert', storage_key='inert/' + str(i),
                  original_filename='photo-' + str(i) + '.png', mime_type='image/png', byte_size=123,
                  sha256='a' * 64, state='ready', created_by=UUID(int=999),
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), default_alt_text=None,
                  codec_metadata={'unused': 'm' * 65536}, lease_epoch=0)
    return SocialMediaAsset(**(values | updates))


def seed_library(engine):
    with Session(engine) as db:
        rows = [asset(i) for i in range(1, 56)]
        rows += [asset(101, state='pending'), asset(102, state='failed'), asset(103, deleted_at=datetime(2026, 1, 2)),
                 asset(104, mime_type='text/plain'), asset(105, mime_type=None, state='pending'),
                 asset(106, original_filename=r'literal%_\name.png', default_alt_text=''),
                 asset(107, mime_type='video/mp4', duration_ms=1, width=1, height=1)]
        db.add_all(rows); db.flush()
        for row in rows:
            if row.id.int % 2 == 0:
                db.add(SocialMediaUpload(asset_id=row.id, actor_id=UUID(int=999), initiation_key=row.id,
                                         request_hash='b' * 64, quarantine_key='q/' + str(row.id),
                                         declared_mime_type='image/png', declared_size=123, version=7,
                                         expires_at=datetime(2026, 1, 2), grant_renewal_deadline=datetime(2026, 1, 2),
                                         reserved_bytes=246, retained_write_fence=None))
        db.commit()


def service(engine):
    # Default OFF config; library is an admin read, never invokes storage.
    return MediaService(Session(engine), SimpleNamespace(config=MediaConfig()))


def legacy_library(svc, page=1, page_size=20, query='', kind=None):
    with svc.db.begin():
        conditions = [SocialMediaAsset.state == 'ready', SocialMediaAsset.deleted_at.is_(None), SocialMediaAsset.mime_type.in_(['image/jpeg', 'image/png', 'video/mp4'])]
        if query:
            conditions.append(SocialMediaAsset.original_filename.ilike('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
        if kind:
            conditions.append(SocialMediaAsset.mime_type.like(kind + '/%'))
        total = svc.db.scalar(select(func.count()).select_from(SocialMediaAsset).where(*conditions))
        rows = svc.db.execute(select(SocialMediaAsset, SocialMediaUpload).outerjoin(SocialMediaUpload, SocialMediaUpload.asset_id == SocialMediaAsset.id).where(*conditions).order_by(SocialMediaAsset.created_at.desc(), SocialMediaAsset.id).offset((page - 1) * page_size).limit(page_size)).all()
        return MediaLibrary(assets=tuple(svc._dto(a, u) for a, u in rows), total=total, page=page, page_size=page_size, has_more=page * page_size < total)


@pytest.mark.parametrize('filters', [{}, {'page_size': 50}, {'page': 2}, {'page': 4}, {'page': 100},
                                     {'query': '%'}, {'query': '_'}, {'query': '\\'}, {'query': "' OR 1=1 --"},
                                     {'query': 'PHOTO-'}, {'kind': 'video'}, {'kind': 'image'}])
def test_library_complete_output_and_selected_columns(compact_db, filters):
    engine = compact_db
    seed_library(engine)
    old, new = service(engine), service(engine)
    try:
        with capture(engine) as old_sql:
            expected = legacy_library(old, **filters).model_dump(mode='json')
        with capture(engine) as sql:
            result = new.library(**filters)
            actual = result.model_dump(mode='json')
        assert actual == expected
        assert len(sql) == len(old_sql) == 2
        assert 'codec_metadata' in ' '.join(old_sql[1]['columns']), 'full-row observation channel must be alive'
        excluded = ['codec_metadata', 'storage_key', 'lease_token', 'lease_epoch', 'quarantine_key',
                    'retained_write_fence', 'fenced_copies', 'completion_hash', 'request_hash', 'declared_size']
        assert all(field not in sql[1]['columns'] for field in excluded), sql[1]['columns']
        assert len(sql[1]['columns']) == 14  # 12 DTO asset fields + upload identity/version
        assert not new.db.identity_map, 'list projection must not hydrate/defer ORM records'
        if actual['assets']:
            assert selected_value_bytes(engine, sql) < selected_value_bytes(engine, old_sql) / 20
        if not filters:
            assert actual['assets'][0]['version'] == 1  # absent upload
            assert actual['assets'][1]['version'] == 7
            assert actual['assets'][0]['width'] is None
            assert actual['has_more'] is True and actual['total'] == 57
        if filters == {'query': '%'}:
            assert len(actual['assets']) == 1 and actual['assets'][0]['default_alt_text'] == ''
    finally:
        old.db.close(); new.db.close()


def test_empty_library_is_not_a_savings_measurement(compact_db):
    svc = service(compact_db)
    try:
        assert svc.library().model_dump(mode='json') == {'assets': [], 'total': 0, 'page': 1, 'page_size': 20, 'has_more': False}
    finally:
        svc.db.close()


@pytest.mark.parametrize('filters', [{'page': True}, {'page': 0}, {'page_size': 51}, {'page_size': float('nan')},
                                     {'query': None}, {'query': 'x' * 101}, {'kind': 'audio'}])
def test_library_rejects_filters_before_sql(compact_db, filters):
    svc = service(compact_db)
    try:
        with capture(compact_db) as sql, pytest.raises(SocialError) as error:
            svc.library(**filters)
        assert error.value.status == 422 and error.value.code == 'INVALID_REQUEST'
        assert not sql
    finally:
        svc.db.close()


def test_malformed_persisted_dto_is_not_silently_dropped(compact_db):
    with Session(compact_db) as db:
        db.add(asset(1, sha256='not-a-sha256'))
        db.commit()
    svc = service(compact_db)
    try:
        with pytest.raises(ValidationError):
            svc.library()
    finally:
        svc.db.close()


def test_zero_population_year_and_only_null_debt(snapshot_runtime):
    engine = snapshot_runtime
    seed_snapshot(engine)
    with Session(engine) as db:
        db.query(PopulationData).delete()
        db.add(PopulationData(year=0, total_population=0))
        db.query(Loan).filter(Loan.debt_category.is_not(None)).delete()
        db.query(Entity).filter(Entity.type == EntityType.NATIONAL).delete()
        db.commit()
    answer = main._pipeline_health_snapshot()['database']
    assert answer['entities']['has_national'] is False
    assert answer['population'] == {'records': 1, 'latest_year': 0}
    assert answer['debt_categories'] == {'records': 1}


@pytest.mark.parametrize('version', [0, None])
def test_existing_upload_invalid_version_is_not_missing_upload(compact_db, version):
    # Historical schema drift is deliberate and confined to this owned fixture.
    # Current production constraints forbid these rows; do not repair on read.
    if compact_db.dialect.name == 'postgresql':
        with compact_db.begin() as conn:
            conn.execute(text('ALTER TABLE social_media_uploads DROP CONSTRAINT ck_social_media_upload_bounds'))
            conn.execute(text('ALTER TABLE social_media_uploads ALTER COLUMN version DROP NOT NULL'))
    elif version is None:
        # SQLite cannot ALTER NOT NULL; direct row DTO control still covers None.
        svc = service(compact_db)
        try:
            with pytest.raises(ValidationError):
                svc._dto(asset(1), SimpleNamespace(version=None))
        finally:
            svc.db.close()
        return
    else:
        with compact_db.begin() as conn:
            conn.execute(text('PRAGMA ignore_check_constraints=ON'))
    seed_library(compact_db)
    with compact_db.begin() as conn:
        conn.execute(text('UPDATE social_media_uploads SET version=:version'), {'version': version})
    old, new = service(compact_db), service(compact_db)
    try:
        with pytest.raises(ValidationError):
            legacy_library(old)
        with pytest.raises(ValidationError):
            new.library()
    finally:
        old.db.close(); new.db.close()


@pytest.mark.parametrize('compact_db', ['postgresql'], indirect=True)
def test_postgres_snapshot_does_not_mix_concurrent_commits(snapshot_runtime):
    """Gate a real SELECT inside PostgreSQL, then commit a competing writer."""
    import concurrent.futures
    import time

    engine = snapshot_runtime
    seed_snapshot(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE entities RENAME TO entities_backing'))
        conn.execute(text('''CREATE FUNCTION b66_snapshot_gate() RETURNS boolean
            LANGUAGE plpgsql VOLATILE AS $$ BEGIN
            PERFORM pg_advisory_xact_lock(660481); RETURN true; END $$'''))
        conn.execute(text('CREATE VIEW entities AS SELECT * FROM entities_backing WHERE b66_snapshot_gate()'))
    inspector = create_engine(engine.url, pool_size=1, max_overflow=0, connect_args={'hostaddr': '127.0.0.1'})
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    with engine.connect() as gate:
        gate.execute(text('SELECT pg_advisory_lock(660481)')); gate.commit()
        future = pool.submit(main._pipeline_health_snapshot)
        try:
            deadline = time.monotonic() + 3
            while True:
                with inspector.connect() as conn:
                    blocked = conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname='b66_queries' AND wait_event='advisory'"))
                if blocked:
                    break
                if time.monotonic() > deadline:
                    pytest.fail('snapshot never reached owned server-side gate')
                time.sleep(0.005)
            # Write on the gate connection while the reader's SQL snapshot lives.
            gate.execute(text('INSERT INTO population_data(year,total_population) VALUES(2027,1)'))
            gate.commit()
            gate.execute(text('SELECT pg_advisory_unlock(660481)')); gate.commit()
            actual = future.result(timeout=3)['database']
            assert actual['population'] == {'records': 3, 'latest_year': 2025}
            assert main._pipeline_health_snapshot()['database']['population'] == {'records': 4, 'latest_year': 2027}
        finally:
            gate.execute(text('SELECT pg_advisory_unlock_all()')); gate.commit()
            pool.shutdown(wait=True)
            inspector.dispose()

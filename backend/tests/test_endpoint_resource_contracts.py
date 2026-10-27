"""Request-to-resource regressions using inert data and an owned runtime."""
import asyncio
import time
from datetime import datetime

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event

import main
from models import DebtCategory, DebtInstrument, Entity, EntityType, Loan


def test_identical_cold_cache_requests_do_one_fill(monkeypatch):
    monkeypatch.setattr(main, 'redis_cache', None)
    calls = []

    @main.cached('resource-cold-flight')
    async def endpoint(value):
        calls.append(value)
        await asyncio.sleep(.02)
        return {'value': value}

    async def exercise():
        result = await asyncio.gather(*(endpoint(value=7) for _ in range(5)))
        assert result == [{'value': 7}] * 5
    asyncio.run(exercise())
    assert calls == [7], 'identical concurrent misses duplicated expensive work'


def test_public_health_database_failure_does_not_disclose_driver_details(monkeypatch):
    from routers import health
    class FailedDB:
        def execute(self, statement):
            raise RuntimeError('fixture-user@private-host.example database=private-db SQL=secret-query')
    monkeypatch.setattr(health.cache, 'health_check', lambda: {'status': 'healthy'})
    body = asyncio.run(health.detailed_health_check(db=FailedDB()))
    assert body['status'] == 'degraded'
    assert body['components']['database']['status'] == 'unhealthy'
    assert 'private-host' not in str(body) and 'secret-query' not in str(body)


@pytest.mark.parametrize('params', [{'page': 10002, 'limit': 1}, {'page': 102, 'limit': 100}])
def test_entities_refuses_deep_offset_before_database(client, db_session, params):
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', record)
    try:
        response = client.get('/api/v1/entities', params=params)
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', record)
    assert response.status_code == 422, response.text
    assert not statements, statements


def test_entities_does_not_count_unused_total(client, db_session):
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(db_session.bind, 'before_cursor_execute', record)
    try:
        response = client.get('/api/v1/entities')
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', record)
    assert response.status_code == 200 and response.json() == []
    assert not any('count(' in sql and 'entities' in sql for sql in statements), statements


def seed_loans(db, country, doc, count):
    entity = Entity(country_id=country.id, type=EntityType.NATIONAL,
                    canonical_name='National fixture', slug='national-fixture')
    db.add(entity)
    db.flush()
    for i in range(count):
        db.add(Loan(entity_id=entity.id, lender=f'Fixture {i}', principal=100,
                    outstanding=100+i, debt_category=DebtCategory.OTHER,
                    issue_date=datetime(2020, 1, 1), currency='KES',
                    source_document_id=doc.id))
    db.flush()


def test_national_register_never_publishes_truncated_financial_totals(client, db_session, seed_country, seed_source_doc, monkeypatch):
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_ROWS', 2, raising=False)
    seed_loans(db_session, seed_country, seed_source_doc, 3)
    response = client.get('/api/v1/debt/loans')
    assert response.status_code == 503, response.text[:300]
    assert 'total_outstanding' not in response.json()
    assert response.headers.get('cache-control') == 'no-store'


def test_bond_register_refuses_oversize_including_withheld_rows(client, db_session, monkeypatch):
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_ROWS', 2, raising=False)
    for i in range(3):
        db_session.add(DebtInstrument(isin=f'KE{i:010d}', issue_no='fixture',
            instrument_type='fixed_coupon_bond', face_value=100, unit='KES',
            maturity_date=datetime(2030+i, 1, 1), tranches=1, publishable=False))
    db_session.flush()
    response = client.get('/api/v1/debt/instruments')
    assert response.status_code == 503, response.text[:300]
    assert 'instruments' not in response.json()


def test_cache_cold_peer_provider_keeps_event_loop_responsive(db_session, monkeypatch):
    calls = []
    def slow(**kwargs):
        calls.append(1)
        time.sleep(.12)
        return []
    monkeypatch.setattr(main, '_get_regional_peers', slow)
    async def exercise():
        task = asyncio.create_task(main.get_debt_sustainability(main._debt_sustainability_snapshot(db_session)))
        start = time.monotonic()
        await asyncio.sleep(.01)
        elapsed = time.monotonic() - start
        body = await task
        assert body['status'] == 'no_data'
        assert elapsed < .08, f'provider blocked serving loop for {elapsed:.3f}s'
    asyncio.run(exercise())
    assert calls == [1]


def test_audit_reader_pool_has_no_overflow_and_bounded_checkout(monkeypatch):
    from services import admin_audit_storage as storage
    storage.reader_engine.cache_clear()
    engine = storage.reader_engine('postgresql://fixture@127.0.0.1/fixture')
    try:
        assert engine.pool.size() == 1
        assert engine.pool._max_overflow == 0
        assert engine.pool.timeout() <= .5
    finally:
        engine.dispose()
        storage.reader_engine.cache_clear()


def test_imf_body_budget_is_checked_before_whole_json(monkeypatch):
    real_client = httpx.Client
    def handler(request):
        return httpx.Response(200, json={'values': {'GGXWDG_NGDP': {}}, 'padding': 'a' * (1024 * 1024)})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(main.httpx, 'get', lambda url, **kw: real_client(transport=transport).get(url))
    monkeypatch.setattr(main.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(ValueError, match='budget'):
        main._imf_fetch_debt_to_gdp(2025)


def test_entities_database_failure_is_not_a_successful_empty_population(monkeypatch, client):
    from database import get_db
    class FailedDB:
        def query(self, *args):
            raise RuntimeError('inert database failure')
    main.app.dependency_overrides[get_db] = lambda: FailedDB()
    response = client.get('/api/v1/entities')
    assert response.status_code == 503, response.text
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('params', [{'page': 0}, {'page': -1}, {'page': 'nan'},
                                  {'limit': 0}, {'limit': -1}, {'limit': 101}, {'limit': 'true'}])
def test_entities_explicit_invalid_pagination(client, params):
    assert client.get('/api/v1/entities', params=params).status_code == 422


def test_register_at_row_limit_preserves_every_loan_and_complete_total(client, db_session, seed_country, seed_source_doc, monkeypatch):
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_ROWS', 3)
    seed_loans(db_session, seed_country, seed_source_doc, 3)
    response = client.get('/api/v1/debt/loans')
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body['loans']) == body['total_loans'] == 3
    assert {r['lender'] for r in body['loans']} == {'Fixture 0', 'Fixture 1', 'Fixture 2'}
    assert body['total_outstanding'] == 303
    assert body['total_annual_service_cost'] is None


def test_register_response_byte_limit_refuses_whole_response(client, db_session, seed_country, seed_source_doc, monkeypatch):
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_BYTES', 128, raising=False)
    seed_loans(db_session, seed_country, seed_source_doc, 1)
    response = client.get('/api/v1/debt/loans')
    assert response.status_code == 503, response.text
    assert 'byte budget' in response.json()['detail']
    assert 'loans' not in response.json()


def test_cache_follower_cancellation_does_not_cancel_leader_and_results_detach():
    from services.endpoint_resources import BoundedFlights
    flights = BoundedFlights()
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def work():
            calls.append(1)
            started.set()
            await release.wait()
            return {'rows': []}
        leader = asyncio.create_task(flights.run('key', work))
        await started.wait()
        cancelled = asyncio.create_task(flights.run('key', work))
        follower = asyncio.create_task(flights.run('key', work))
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        release.set()
        a, b = await asyncio.gather(leader, follower)
        a['rows'].append('mutated')
        assert b == {'rows': []} and calls == [1]
        assert not flights._pending
    asyncio.run(exercise())


@pytest.mark.parametrize('failure', [RuntimeError('inert failure'), asyncio.CancelledError()])
def test_cache_leader_failure_and_cancellation_release_key_for_retry(failure):
    from services.endpoint_resources import BoundedFlights
    flights = BoundedFlights()
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        async def work():
            started.set()
            await release.wait()
            raise failure
        leader = asyncio.create_task(flights.run('key', work))
        await started.wait()
        follower = asyncio.create_task(flights.run('key', work))
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(type(failure)):
            await leader
        with pytest.raises(HTTPException if isinstance(failure, asyncio.CancelledError) else RuntimeError):
            await follower
        assert not flights._pending
        assert await flights.run('key', lambda: asyncio.sleep(0, result=7)) == 7
    asyncio.run(exercise())


def test_cache_admission_refuses_extra_keys_and_followers_without_queue():
    from services.endpoint_resources import BoundedFlights
    flights = BoundedFlights(max_fills=1, max_followers=1)
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        async def work():
            started.set()
            await release.wait()
            return 7
        leader = asyncio.create_task(flights.run('key', work))
        await started.wait()
        follower = asyncio.create_task(flights.run('key', work))
        await asyncio.sleep(0)
        for key in ('another', 'key'):
            with pytest.raises(HTTPException) as refused:
                await flights.run(key, work)
            assert refused.value.status_code == 503
        assert len(flights._pending) == 1
        release.set()
        assert await asyncio.gather(leader, follower) == [7, 7]
        assert not flights._pending
    asyncio.run(exercise())


def test_cancelled_peer_caller_keeps_physical_worker_slot_until_completion():
    import threading
    from services.endpoint_resources import SingleWorker
    worker = SingleWorker()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def work():
        started.set()
        if not release.wait(2):
            raise RuntimeError('fixture release missing')
        finished.set()
        return 7
    async def exercise():
        leader = asyncio.create_task(worker.run(work))
        for _ in range(100):
            if started.is_set(): break
            await asyncio.sleep(.005)
        assert started.is_set()
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        with pytest.raises(HTTPException) as refused:
            await worker.run(work)
        assert refused.value.status_code == 503
        release.set()
        for _ in range(100):
            if finished.is_set(): break
            await asyncio.sleep(.005)
        assert finished.is_set()
    try:
        asyncio.run(exercise())
    finally:
        release.set()
        worker.close()


def test_loan_query_projects_only_used_columns_and_bounds_database_transfer(client, db_session, seed_country, seed_source_doc):
    seed_loans(db_session, seed_country, seed_source_doc, 2)
    # Evict fixture instances: loaded identity-map values must not mask a
    # deferred-column access or make the projection fixture falsely green.
    db_session.expunge_all()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        if 'FROM loans' in statement:
            statements.append((statement, parameters))
    event.listen(db_session.bind, 'before_cursor_execute', record)
    try:
        response = client.get('/api/v1/debt/loans')
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', record)
    assert response.status_code == 200, response.text
    assert len(statements) == 1, statements
    sql, params = statements[0]
    assert 'LIMIT' in sql and main.MAX_PUBLIC_REGISTER_ROWS + 1 in params
    assert 'loans.created_at' not in sql and 'loans.confidence_score' not in sql
    assert response.json()['total_outstanding'] == 201


def test_bond_projection_excludes_unused_row_json_and_preserves_complete_ladder(client, db_session, seed_source_doc):
    for i in range(3):
        db_session.add(DebtInstrument(isin=f'KE{i:010d}', issue_no='fixture',
            instrument_type='fixed_coupon_bond', face_value=100+i, unit='KES',
            maturity_date=datetime(2030, 1, 1), tranches=1, publishable=True,
            source_document_id=seed_source_doc.id, meta={'unused': 'a' * 100000}))
    db_session.flush()
    db_session.expunge_all()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))
    event.listen(db_session.bind, 'before_cursor_execute', record)
    try:
        response = client.get('/api/v1/debt/instruments')
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['instrument_count'] == 3 and len(body['instruments']) == 3
    assert body['is_debt_total'] is False
    assert body['ladder'] == [{'year': 2030, 'face_value': 303, 'instruments': 3}]
    register_sql = [sql for sql, params in statements if 'FROM debt_instruments' in sql]
    assert len(register_sql) == 1 and 'LIMIT' in register_sql[0]
    assert 'debt_instruments.metadata' not in register_sql[0]
    assert len(statements) == 2, 'bond source lookup regressed to per-row lazy reads'


def test_mounted_sustainability_releases_owned_db_before_provider_await(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import get_db
    from models import Base
    engine = create_engine(f'sqlite:///{tmp_path / "snapshot.sqlite"}',
                          pool_size=1, max_overflow=0, pool_timeout=.1)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    active = []
    states = []
    def sessions():
        with factory() as db:
            active.append(True)
            try:
                yield db
            finally:
                active[-1] = False
    async def provider(**kwargs):
        states.append((any(active), engine.pool.checkedout()))
        await asyncio.sleep(0)
        return []
    monkeypatch.setattr(main, 'get_db', sessions)
    monkeypatch.setattr(main, '_read_regional_peers', provider)
    app = FastAPI()
    app.get('/api/v1/debt/sustainability')(main.get_debt_sustainability)
    app.dependency_overrides[get_db] = sessions
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/debt/sustainability')
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'no_data'
        assert states == [(False, 0)], 'provider await retained a request transaction/connection'
    finally:
        engine.dispose()


def test_snapshot_builder_does_not_commit_or_rollback_a_borrowed_session(db_session):
    before = db_session.begin()
    body, arguments = main._debt_sustainability_snapshot(db_session)
    assert body['status'] == 'no_data' and arguments == {}
    assert db_session.get_transaction() is before
    assert db_session.in_transaction()

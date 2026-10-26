"""Request pool/transaction policy; no database socket needed for these controls."""
from types import SimpleNamespace
from time import monotonic

import pytest
from sqlalchemy.exc import TimeoutError


def test_http_dependency_uses_bounded_pool_without_premature_transaction():
    import database
    from middleware.request_resources import request_deadline
    token = request_deadline.set(monotonic() + 30)
    dependency = database.get_db()
    db = next(dependency)
    try:
        assert db.get_bind().pool.timeout() <= 2
        assert db.get_bind().pool._max_overflow == 0
        assert not db.in_transaction()
        with db.begin():
            assert db.in_transaction()
        assert database.SessionLocal.kw['bind'] is database.engine
        assert db.get_bind() is not database.engine, 'The request policy changed the shared seeding engine'
    finally:
        dependency.close()
        request_deadline.reset(token)


def invoke_policy(engine, sql, cursor):
    transaction = object()
    connection = SimpleNamespace(info={}, get_transaction=lambda: transaction)
    for callback in engine.dispatch.before_cursor_execute:
        callback(connection, cursor, sql, (), SimpleNamespace(), False)


def test_derived_request_connections_clamp_local_work_and_keep_reader_preamble():
    from request_database import create_request_engine
    from middleware.request_resources import request_deadline
    engine = create_request_engine('postgresql+psycopg2://fixture:fixture@127.0.0.1:1/fixture', {})
    calls = []
    cursor = SimpleNamespace(execute=lambda *args:calls.append(args),
        fetchone=lambda: (None, None, *calls[-1][1][2:]))
    try:
        invoke_policy(engine, 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY', cursor)
        assert calls == [], 'The committed reader preamble must precede all queries'
        token = request_deadline.set(monotonic() + .1)
        try:
            invoke_policy(engine, 'SELECT 1', cursor)
        finally:
            request_deadline.reset(token)
        assert len(calls) == 1
        assert calls[0][1][:2] == (True, True)
        assert 1 <= int(calls[0][1][2]) <= 100
        assert 1 <= int(calls[0][1][3]) <= 100
        token = request_deadline.set(monotonic() - 1)
        try:
            with pytest.raises(TimeoutError, match='Request database time budget exceeded'):
                invoke_policy(engine, 'SELECT 1', cursor)
        finally:
            request_deadline.reset(token)
        assert len(calls) == 1, 'Expired work reached the database cursor'
    finally:
        engine.dispose()


def test_pipeline_snapshot_thread_retains_request_factory_and_deadline(monkeypatch):
    import asyncio
    import main
    import database
    from middleware.request_resources import request_deadline
    selected = []
    class Session:
        def __init__(self,label): self.label=label
        def __enter__(self): selected.append((self.label,request_deadline.get()));return self
        def __exit__(self,*args): pass
    monkeypatch.setattr(database,'SessionLocal',lambda:Session('seed_worker'))
    monkeypatch.setattr(database,'RequestSessionLocal',lambda:Session('request'))
    monkeypatch.setattr(main,'_pipeline_health_database_stats',lambda db:{
        'entities':{'counties':47},'population':{'records':1},
        'economic_indicators':{'records':1},'loans':{'records':1}})
    deadline = monotonic()+2
    async def exercise():
        token = request_deadline.set(deadline)
        try:
            await main._read_pipeline_health_snapshot(include_legacy_module=False)
        finally:
            request_deadline.reset(token)
    asyncio.run(exercise())
    assert selected == [('request',deadline)]

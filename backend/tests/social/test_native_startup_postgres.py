"""Real CLI, composition, queue scan and stopped heartbeat on migrated PostgreSQL."""
from contextlib import asynccontextmanager
import httpx
import pytest
from sqlalchemy import text
from test_domain_postgres import pg_engine
from test_media_migration_postgres import upgrade
from test_native_startup import ready


def test_explicit_native_cli_scans_once_stops_and_closes_on_postgresql(pg_engine, monkeypatch):
    import social.worker.__main__ as cli
    from social.worker.startup import native_runtime
    upgrade(pg_engine)
    module = ready(monkeypatch)
    media = module.load_media_runtime({})
    closed = []
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            pytest.fail('An empty paused scan must not contact Meta')
        async def aclose(self): closed.append('http')
    media.storage.client.close.side_effect = lambda: closed.append('storage')
    @asynccontextmanager
    async def composition(engine):
        async with native_runtime(engine, environ={'SOCIAL_NATIVE_ENABLED':'true',
                'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'}, transport_factory=Transport) as registry:
            yield registry
    monkeypatch.setattr(cli, 'native_runtime', composition)
    monkeypatch.setattr(cli, 'create_worker_engine', lambda config: pg_engine)
    assert cli.main(['--database-url','postgresql://postgres@127.0.0.1:62124/social_domain_test',
                     '--deployment-version','isolated-fixture','--once','--native-meta']) == 0
    assert closed == ['http','http','storage']
    with pg_engine.begin() as conn:
        row = conn.execute(text('SELECT state,active_claims,last_scan_at FROM social_worker_heartbeats')).one()
        assert row.state == 'stopped' and row.active_claims == 0 and row.last_scan_at is not None
        assert conn.execute(text('SELECT count(*) FROM social_publish_attempts')).scalar() == 0

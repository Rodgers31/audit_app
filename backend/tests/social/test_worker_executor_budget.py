"""Credential/media offloads must share the native CLI's two-thread budget."""
import asyncio
from contextlib import asynccontextmanager
import os
import threading
from types import SimpleNamespace

from sqlalchemy import create_engine

from social.worker import __main__ as cli
from social.worker import ownership


def test_native_cli_db_and_material_offloads_share_exactly_two_threads(monkeypatch):
    observed = {}
    engine = create_engine('sqlite://')
    monkeypatch.setattr(cli, 'create_worker_engine', lambda config: engine)
    monkeypatch.setattr(cli, 'verify_worker_role', lambda *args: None)
    monkeypatch.setattr(cli, 'validate_worker_native_environment', lambda values: None)

    def acquire(engine, owner, version):
        authority = ownership.RuntimeAuthority(owner, 1)
        monkeypatch.setitem(ownership._issued, (os.getpid(), id(authority)), authority)
        return authority
    monkeypatch.setattr(cli, 'acquire_authority', acquire)

    class Repository:
        def __init__(self, engine, config, owner, *, authority):
            self.config, self.authority = config, authority
            self.admission_stopped = threading.Event()

        def check_authority(self):
            pass  # This unit seam measures executors; PostgreSQL is covered separately.

        def drained(self):
            return True
    monkeypatch.setattr(cli, 'QueueRepository', Repository)

    @asynccontextmanager
    async def native(engine):
        yield SimpleNamespace(adapters={}, credential_loader=None, media_access=None)
    monkeypatch.setattr(cli, 'native_runtime', native)

    async def run(worker, *, once=False):
        barrier = threading.Barrier(2)
        def identify():
            barrier.wait(timeout=3)
            return threading.get_ident()
        database_threads = await asyncio.gather(worker.db(identify), worker.db(identify))
        # This is the actual asyncio mechanism used by credential/media material.
        material_thread = await asyncio.to_thread(threading.get_ident)
        observed['threads'] = {*database_threads, material_thread}
        observed['shared'] = asyncio.get_running_loop()._default_executor is worker.executor
    monkeypatch.setattr(cli.SocialWorker, '_run', run)
    assert cli.main(['--database-url', 'postgresql://inert@invalid/fixture', '--native-meta',
                     '--worker-role', 'inert_worker', '--once']) == 0
    assert len(observed['threads']) == 2
    assert observed['shared'] is True

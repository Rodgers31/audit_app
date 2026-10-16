"""Independent CLI lifecycle checks with explicit inert preflight/owner seams."""
import asyncio
from contextlib import contextmanager, asynccontextmanager
import logging
import signal
from types import SimpleNamespace

import pytest

from social.worker import __main__ as cli

DSN = 'postgresql://inert@127.0.0.1/inert'


def native_args(*, once=True):
    return ['--database-url', DSN, '--native-meta', '--worker-role', 'inert_worker'] + (['--once'] if once else [])


@pytest.fixture
def f(monkeypatch):
    events, configs, instances, handlers = [], [], [], {}
    originals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def set_signal(sig, handler):
        events.append(('restore_signal' if handler is originals[sig] else 'install_signal', sig))
        handlers[sig] = handler

    monkeypatch.setattr(cli.signal, 'signal', set_signal)
    monkeypatch.setenv('SOCIAL_NATIVE_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED', 'true')

    @contextmanager
    def connect():
        events.append('diagnostic_scan')
        yield SimpleNamespace(execute=lambda *args: SimpleNamespace(scalar_one=lambda: False))

    engine = SimpleNamespace(dispose=lambda: events.append('dispose'), connect=connect)

    def create_engine(config):
        configs.append(config)
        return engine

    monkeypatch.setattr(cli, 'create_worker_engine', create_engine)
    monkeypatch.setattr(cli, 'verify_worker_role', lambda *args: events.append('role_verified'))

    def validate(values):
        assert values['SOCIAL_NATIVE_ENABLED'] == values['SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED'] == 'true'
        events.append('preflight')

    monkeypatch.setattr(cli, 'validate_worker_native_environment', validate)

    def acquire(engine, owner, version):
        events.append('acquire')
        return SimpleNamespace(owner_id=owner, generation=1)

    monkeypatch.setattr(cli, 'acquire_authority', acquire)

    def repository(engine, config, owner, *, authority):
        assert authority.owner_id == owner
        return SimpleNamespace(config=config, check_authority=lambda: events.append('authority_checked'),
                               drained=lambda: events.append('drained') or True)

    monkeypatch.setattr(cli, 'QueueRepository', repository)
    registration = SimpleNamespace(adapters={('fake', 'fake'): object()}, credential_loader=object(), media_access=object())

    @asynccontextmanager
    async def runtime(engine):
        events.append('native_enter')
        try:
            yield registration
        finally:
            events.append('native_exit')

    monkeypatch.setattr(cli, 'native_runtime', runtime)

    class Worker:
        failed = False

        def __init__(self, repository, **kwargs):
            self.kwargs = kwargs
            instances.append(self)
            events.append('construct')

        def stop(self):
            events.append('stop')

        async def run(self, *, once):
            events.append(('run', once))

        async def close(self):
            events.append('worker_close')

    monkeypatch.setattr(cli, 'SocialWorker', Worker)
    return SimpleNamespace(events=events, config=configs, instances=instances, engine=engine,
                           registration=registration, handlers=handlers, originals=originals)


@pytest.mark.parametrize('native,once', [(False, False), (False, True), (True, False), (True, True)])
def test_cli_opt_in_and_once_semantics(f, native, once):
    args = native_args(once=once) if native else ['--database-url', DSN] + (['--once'] if once else [])
    assert cli.main(args) == (0 if native or once else 1)
    assert ('native_enter' in f.events) is native
    if native:
        assert ('run', once) in f.events
        assert f.instances[0].kwargs['adapters'] is f.registration.adapters
        assert f.events.index('role_verified') < f.events.index('preflight') < f.events.index('acquire')
        assert f.events.index('acquire') < f.events.index('authority_checked') < f.events.index('native_enter')
        assert f.events.index('worker_close') < f.events.index('native_exit') < f.events.index('drained') < f.events.index('dispose')
    else:
        assert not f.instances and 'acquire' not in f.events and 'preflight' not in f.events
        assert ('diagnostic_scan' in f.events) is once
    assert f.handlers == f.originals


def test_native_flag_cannot_succeed_when_registration_is_disabled(f, monkeypatch, caplog):
    @asynccontextmanager
    async def disabled(engine):
        yield None
    monkeypatch.setattr(cli, 'native_runtime', disabled)
    with caplog.at_level(logging.ERROR):
        assert cli.main(native_args()) == 1
    assert not f.instances and 'acquire' in f.events and 'dispose' in f.events
    assert 'drained' not in f.events and f.handlers == f.originals
    assert 'WORKER_UNAVAILABLE' in caplog.text


def test_partial_signal_installation_restores_first_before_any_resource_construction(f, monkeypatch, caplog):
    original = cli.signal.signal
    count = 0

    def install(sig, handler):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError('PRIVATE_SIGNAL_MARKER')
        return original(sig, handler)

    monkeypatch.setattr(cli.signal, 'signal', install)
    assert cli.main(native_args()) == 1
    assert len([x for x in f.events if x[0] == 'restore_signal']) == 2
    assert not f.config and not f.instances and 'native_enter' not in f.events
    assert f.handlers == f.originals and 'PRIVATE_SIGNAL_MARKER' not in caplog.text


def test_worker_failure_is_logged_sanitized_and_cleanup_runs(f, monkeypatch, caplog):
    class Bad(cli.SocialWorker):
        async def run(self, *, once):
            raise RuntimeError('PRIVATE_WORKER_MARKER')
    monkeypatch.setattr(cli, 'SocialWorker', Bad)
    with caplog.at_level(logging.ERROR):
        assert cli.main(native_args()) == 1
    assert 'PRIVATE_WORKER_MARKER' not in caplog.text
    assert f.events.index('worker_close') < f.events.index('native_exit') < f.events.index('dispose')
    assert 'drained' not in f.events and f.handlers == f.originals


@pytest.mark.parametrize('error,code', [(asyncio.CancelledError, 1), (KeyboardInterrupt, 130)])
def test_worker_interruption_returns_nonzero_after_cleanup(f, monkeypatch, caplog, error, code):
    class Interrupted(cli.SocialWorker):
        async def run(self, *, once):
            raise error('PRIVATE_INTERRUPT_MARKER')
    monkeypatch.setattr(cli, 'SocialWorker', Interrupted)
    assert cli.main(native_args()) == code
    assert f.events.index('worker_close') < f.events.index('native_exit') < f.events.index('dispose')
    assert 'drained' not in f.events and f.handlers == f.originals
    assert 'PRIVATE_INTERRUPT_MARKER' not in caplog.text


def test_signal_removal_failure_still_closes_worker_and_native_resources(f, monkeypatch, caplog):
    original = cli.signal.signal

    def restore(sig, handler):
        original(sig, handler)
        if handler is f.originals[sig]:
            raise RuntimeError('PRIVATE_SIGNAL_REMOVAL_MARKER')

    monkeypatch.setattr(cli.signal, 'signal', restore)
    assert cli.main(native_args()) == 1
    assert f.events.index('worker_close') < f.events.index('native_exit') < f.events.index('dispose')
    assert len([x for x in f.events if isinstance(x, tuple) and x[0] == 'restore_signal']) == 2
    assert f.handlers == f.originals and 'PRIVATE_SIGNAL_REMOVAL_MARKER' not in caplog.text


def test_real_signal_callback_stops_worker_and_wakes_selector(f, monkeypatch):
    original = cli.SocialWorker

    class Signalled(original):
        async def run(self, *, once):
            f.handlers[signal.SIGTERM](signal.SIGTERM, None)
            await super().run(once=once)

    monkeypatch.setattr(cli, 'SocialWorker', Signalled)
    assert cli.main(native_args()) == 0
    assert 'stop' in f.events and f.handlers == f.originals

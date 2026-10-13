"""Independent cleanup controls never hide uncertain creation or setup failure."""
from types import SimpleNamespace

import pytest

from tests.admin_audit_epoch import resource_cleanup as cleanup


NAME = 'batch12_audit_storage_' + 'a' * 32
DATABASE = (123, 'inert', '111')
ROLE = (456, False, False, True)


class Engine:
    def __init__(self, label, seen, failure=None):
        self.label, self.seen, self.failure = label, seen, failure

    def dispose(self):
        self.seen.append('dispose:' + self.label)
        if self.failure:
            raise self.failure


class Control(Engine):
    def __init__(self, seen, fail_drop=None):
        super().__init__('control', seen)
        self.url = SimpleNamespace(drivername='postgresql+psycopg2', host='127.0.0.1',
            port=55545, username='inert', password='inert', database='issue611', query={})
        self.resources = {NAME: DATABASE, NAME + '_r': ROLE, NAME + '_w': ROLE}
        self.fail_drop = fail_drop

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def scalar(self, statement):
        assert 'pg_control_system' in str(statement)
        return '111'

    def execute(self, statement):
        sql = str(statement)
        if sql == 'SELECT current_database(),current_user':
            return SimpleNamespace(one=lambda: ('issue611', 'inert'))
        name = sql.split('"')[1]
        self.seen.append('drop:' + name)
        if name == self.fail_drop:
            raise OSError('controlled drop failure')
        del self.resources[name]


def controls(monkeypatch, failure=None):
    seen = []
    admin = Control(seen, fail_drop=failure if failure in (NAME, NAME + '_r') else None)
    engines = [Engine('reader', seen, OSError('controlled disposal') if failure == 'reader' else None),
               Engine('writer', seen), Engine('owner', seen)]
    monkeypatch.setattr(cleanup, 'database_identity', lambda c, name: c.resources.get(name))
    monkeypatch.setattr(cleanup, 'role_identity', lambda c, name: c.resources.get(name))
    return seen, admin, engines


@pytest.mark.parametrize('failure', [NAME, NAME + '_r', 'reader'])
def test_cleanup_attempts_every_independent_resource(failure, monkeypatch, capsys):
    seen, admin, engines = controls(monkeypatch, failure)
    with pytest.raises(ExceptionGroup, match='cleanup remains unverified'):
        cleanup.cleanup_owned(admin, engines, NAME, True, DATABASE,
            {NAME + '_r': ROLE, NAME + '_w': ROLE})
    assert seen == ['dispose:reader', 'dispose:writer', 'dispose:owner', 'drop:' + NAME,
                    'drop:' + NAME + '_r', 'drop:' + NAME + '_w', 'dispose:control']
    assert '"cleanup": false' in capsys.readouterr().out


def test_primary_setup_failure_and_cleanup_failure_both_survive(monkeypatch):
    _, admin, engines = controls(monkeypatch, NAME)
    primary = ValueError('controlled setup failure')
    with pytest.raises(ExceptionGroup) as caught:
        try:
            raise primary
        finally:
            cleanup.cleanup_owned(admin, engines, NAME, True, DATABASE, {})
    assert caught.value.exceptions[0] is primary
    assert isinstance(caught.value.exceptions[1], ExceptionGroup)


def test_success_and_no_creation_are_verified(monkeypatch, capsys):
    seen, admin, engines = controls(monkeypatch)
    cleanup.cleanup_owned(admin, engines, NAME, True, DATABASE,
        {NAME + '_r': ROLE, NAME + '_w': ROLE})
    assert admin.resources == {}
    assert '"cleanup": true' in capsys.readouterr().out
    seen.clear()
    cleanup.cleanup_owned(admin, (), NAME, False, None, {})
    assert seen == ['dispose:control']


def test_unknown_create_outcome_is_retained_and_reported(monkeypatch, capsys):
    seen, admin, engines = controls(monkeypatch)
    with pytest.raises(ExceptionGroup):
        cleanup.cleanup_owned(admin, engines, NAME, True, None, {NAME + '_r': None})
    assert not any(value.startswith('drop:') for value in seen)
    assert admin.resources[NAME] == DATABASE
    assert seen[-1] == 'dispose:control'
    assert '"cleanup": false' in capsys.readouterr().out


def test_changed_identity_refuses_before_drop_and_preserves_other_cleanup(monkeypatch):
    seen, admin, engines = controls(monkeypatch)
    with pytest.raises(ExceptionGroup):
        cleanup.cleanup_owned(admin, engines, NAME, True, (999, 'inert', '111'),
            {NAME + '_r': ROLE, NAME + '_w': ROLE})
    assert 'drop:' + NAME not in seen
    assert NAME in admin.resources
    assert seen[-3:] == ['drop:' + NAME + '_r', 'drop:' + NAME + '_w', 'dispose:control']


def test_replaced_cluster_refuses_database_and_role_drops(monkeypatch, capsys):
    seen, admin, engines = controls(monkeypatch)
    admin.scalar = lambda statement: '222'
    with pytest.raises(ExceptionGroup):
        cleanup.cleanup_owned(admin, engines, NAME, True, DATABASE,
            {NAME + '_r': ROLE, NAME + '_w': ROLE})
    assert not any(value.startswith('drop:') for value in seen)
    assert len(admin.resources) == 3
    assert seen[-1] == 'dispose:control'
    assert '"cleanup": false' in capsys.readouterr().out


def test_cleanup_interruption_attempts_other_resources_and_is_preserved(monkeypatch, capsys):
    seen, admin, engines = controls(monkeypatch)
    interrupt = KeyboardInterrupt('controlled cleanup interruption')
    engines[0].failure = interrupt
    with pytest.raises(BaseExceptionGroup) as caught:
        cleanup.cleanup_owned(admin, engines, NAME, True, DATABASE,
            {NAME + '_r': ROLE, NAME + '_w': ROLE})
    assert caught.value.exceptions == (interrupt,)
    assert seen[-4:] == ['drop:' + NAME, 'drop:' + NAME + '_r', 'drop:' + NAME + '_w', 'dispose:control']
    assert '"cleanup": false' in capsys.readouterr().out

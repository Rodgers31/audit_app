"""Optional provider authority preserves the composed policy and worker contract."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import dialect

from social.worker import __main__ as cli, role_admin, role_contract as contract


BASE_READ = frozenset({'social_controls', 'social_accounts', 'social_publications', 'social_post_targets',
    'social_post_revisions', 'social_publish_attempts', 'social_credentials', 'social_media_assets',
    'social_worker_heartbeats', 'social_worker_runtime_ownership', 'social_worker_runtime_history',
    'social_posts', 'social_source_events', 'social_source_cursors',
    'social_automation_rule_versions', 'social_policy_operating_evidence',
    'social_authorized_policy_snapshots', 'social_policy_selection', 'social_policy_decisions'})
EXTRA_READ = frozenset({'social_platform_credentials', 'social_platform_budgets', 'social_platform_event_inbox'})


def test_default_matrix_matches_meta_baseline_and_opt_in_is_additive():
    baseline = contract.selected_contract()
    assert baseline.read_tables == BASE_READ == contract.READ_TABLES
    assert baseline.tables == BASE_READ | {'social_audit_events'} == contract.TABLES
    assert not EXTRA_READ & baseline.updates.keys()
    assert not EXTRA_READ & baseline.lock_tables
    extended = contract.selected_contract(platforms=True)
    assert extended.read_tables == BASE_READ | EXTRA_READ
    assert extended.lock_tables == baseline.lock_tables | {'social_platform_credentials'}
    assert dict(extended.inserts) == dict(baseline.inserts)
    assert extended.updates['social_platform_credentials'] == {'id'}
    assert extended.updates['social_platform_budgets'] == {'reserved_microusd', 'version'}
    assert extended.updates['social_platform_event_inbox'] == {'processing_state', 'processed_at'}
    for table, fields in baseline.updates.items():
        assert extended.updates[table] == fields
    assert not {'social_platform_oauth_flows', 'social_platform_connection_budgets'} & extended.tables
    with pytest.raises(TypeError):
        extended.updates['social_controls'] = frozenset({'publishing_enabled'})


@pytest.mark.parametrize('value', [None, 0, 1, '', 'false', 'true', [], {}])
def test_platform_selection_requires_boolean_not_truthiness(value):
    with pytest.raises(contract.WorkerRoleError): contract.selected_contract(platforms=value)


def test_optional_policies_include_lock_only_fence_and_no_oauth_authority():
    base = {(p.table, p.name): p for p in contract._policies()}
    extra = {(p.table, p.name): p for p in contract._policies(platforms=True)}
    assert set(base) <= set(extra)
    assert all(extra[key] == value for key, value in base.items())
    lock = extra['social_platform_credentials', 'scw_update_fence']
    assert lock.permissive is False and lock.using == 'true' and lock.check == 'false'
    assert extra['social_platform_budgets', 'scw_update_fence'].check == 'true'
    assert extra['social_platform_event_inbox', 'scw_update_fence'].check == 'true'
    assert all(not p.table.endswith(('oauth_flows', 'connection_budgets')) for p in extra.values())


@pytest.mark.parametrize('platforms', [False, True])
def test_installer_emits_only_selected_matrix_and_threads_verification(monkeypatch, platforms):
    statements, calls = [], []
    conn = SimpleNamespace(dialect=dialect(), execute=lambda sql, *args: statements.append(str(sql)))
    class Engine:
        @contextmanager
        def begin(self): yield conn
    monkeypatch.setattr(contract, 'Engine', Engine)
    monkeypatch.setattr(contract, '_limits', lambda c: None)
    monkeypatch.setattr(contract, '_identity', lambda *a, **kw: 99)
    monkeypatch.setattr(contract, '_triggers', lambda *a, **kw: calls.append(('triggers', kw)))
    monkeypatch.setattr(contract, '_grants', lambda *a, **kw: calls.append(('grants', kw)))
    monkeypatch.setattr(contract, '_check_policies', lambda *a, **kw: calls.append(('policies', kw)) or set())
    monkeypatch.setattr(contract, '_verify', lambda *a, **kw: calls.append(('verify', kw)))
    contract.install_worker_role(Engine(), 'fixture_worker', 'fixture_schema', platforms=platforms)
    for table in EXTRA_READ:
        assert any(sql.startswith('GRANT SELECT ON') and table in sql for sql in statements) is platforms
    assert all(call[1]['platforms'] is platforms for call in calls)
    assert [call[0] for call in calls].count('verify') == 2
    assert not any('social_platform_connection_budgets' in sql or 'social_platform_oauth_flows' in sql for sql in statements)


@pytest.mark.parametrize('platforms', [False, True])
def test_verifier_threads_explicit_selection_through_actual_entrypoint(monkeypatch, platforms):
    calls = []
    class Engine:
        @contextmanager
        def begin(self): yield object()
    monkeypatch.setattr(contract, 'Engine', Engine)
    monkeypatch.setattr(contract, '_limits', lambda c: None)
    monkeypatch.setattr(contract, '_verify', lambda *a, **kw: calls.append(kw))
    contract.verify_worker_role(Engine(), 'fixture_worker', platforms=platforms)
    assert calls == [{'current': True, 'platforms': platforms}]


@pytest.mark.parametrize('platforms', [False, True])
@pytest.mark.parametrize('install', [False, True])
def test_operator_cli_selects_optional_contract_only_with_flag(monkeypatch, capsys, platforms, install):
    calls = []
    engine = SimpleNamespace(dispose=lambda: calls.append('disposed'))
    monkeypatch.setenv('INERT_PLATFORM_ROLE_DSN', 'postgresql://inert@localhost/inert')
    monkeypatch.setattr(role_admin, 'create_worker_engine', lambda c: engine)
    def entry(*args, **kw): calls.append((args, kw))
    monkeypatch.setattr(role_admin, 'install_worker_role' if install else 'verify_worker_role', entry)
    args = ['--database-url-env', 'INERT_PLATFORM_ROLE_DSN', '--role', 'fixture_worker', '--schema', 'fixture_schema', '--install' if install else '--verify']
    assert role_admin.main(args + (['--native-platforms'] if platforms else [])) == 0
    assert calls == [((engine, 'fixture_worker', 'fixture_schema'), {'platforms': True} if platforms else {}), 'disposed']
    assert '"status":"ok"' in capsys.readouterr().out


@pytest.mark.parametrize('platforms', [False, True])
def test_worker_cli_selects_optional_role_contract_before_authority(monkeypatch, platforms):
    calls = []
    engine = SimpleNamespace(dispose=lambda: calls.append('disposed'))
    monkeypatch.setattr(cli, 'create_worker_engine', lambda c: engine)
    def stop(*args, **kw):
        calls.append((args, kw))
        raise contract.WorkerRoleError('inert refusal')
    monkeypatch.setattr(cli, 'verify_worker_role', stop)
    monkeypatch.setattr(cli, 'acquire_authority', lambda *a: pytest.fail('role refusal must precede authority'))
    args = ['--database-url', 'postgresql://inert@localhost/inert', '--worker-role', 'fixture_worker', '--native-platforms' if platforms else '--native-meta', '--once']
    assert cli.main(args) == 1
    assert calls == [((engine, 'fixture_worker', 'public'), {'platforms': True} if platforms else {}), 'disposed']


def test_meta_flag_alone_refuses_enabled_platform_environment_before_authority(monkeypatch):
    import social.platform_runtime as runtime
    calls = []
    monkeypatch.setattr(cli, 'create_worker_engine', lambda c: SimpleNamespace(dispose=lambda: calls.append('disposed')))
    monkeypatch.setattr(cli, 'verify_worker_role', lambda *a: calls.append('baseline_role'))
    monkeypatch.setattr(runtime, 'load_platform_settings', lambda values: SimpleNamespace(adapters={'threads': SimpleNamespace(ready=True)}))
    monkeypatch.setattr(cli, 'validate_worker_native_environment', lambda *a: pytest.fail('environment opt-in must precede native preflight'))
    monkeypatch.setattr(cli, 'acquire_authority', lambda *a: pytest.fail('environment opt-in must precede authority'))
    monkeypatch.setattr(cli, 'native_runtime', lambda *a: pytest.fail('environment opt-in must precede providers'))
    assert cli.main(['--database-url', 'postgresql://inert@localhost/inert', '--worker-role', 'fixture_worker', '--native-meta', '--once']) == 1
    assert calls == ['baseline_role', 'disposed']

"""Execute recovery and hostile file/parser boundaries with inert material."""
import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID
import pytest
from scripts.social_meta_recovery import fixture_drill, main
from social.connections.recovery import (MAX_BACKUP_BYTES, RecoveryError, RecoveryKeyring,
    RecoveryProbe, encode_keyring, parse_keyring, read_keyring_backup, verify_restoration, write_keyring_backup)

KEY1 = base64.urlsafe_b64encode(bytes(range(32))).decode('ascii')
KEY2 = base64.urlsafe_b64encode(bytes(range(32, 64))).decode('ascii')
OWNER = UUID('11111111-1111-4111-8111-111111111111')

@pytest.fixture
def ring(): return RecoveryKeyring('v1', {'v1': KEY1, 'v2': KEY2})

def probe(ring):
    version, data = ring.cipher().encrypt(OWNER, 'facebook_page', {'access_token': 'fixture-private-marker'})
    return RecoveryProbe(OWNER, 'facebook_page', version, data)

def test_recovery_fixture_executes_backups_restarts_old_new_material():
    result = fixture_drill()
    assert result['status'] == 'VERIFIED_BY_EXECUTION'
    assert result['envelopes_decrypted'] == result['purposes_verified'] == 4
    assert result['negative_controls_rejected'] == 4
    assert result['production_authorized'] is result['digest_keys_verified'] is False

@pytest.mark.parametrize('raw', [None, '', b'', b'[]', b'null', b'false', b'1', b'NaN', b'{}',
    b'{"secret":"fixture"', b'\xff', b'[' * 2000, b'x' * (MAX_BACKUP_BYTES + 1)])
def test_recovery_parser_refuses_shapes_without_decoder_context(raw):
    with pytest.raises(RecoveryError) as error: parse_keyring(raw)
    assert str(error.value) == 'CREDENTIAL_RECOVERY_REFUSED'
    assert error.value.__context__ is error.value.__cause__ is None

@pytest.mark.parametrize('change', [dict(schema_version=True), dict(schema_version=2), dict(purpose='meta_subject_digest'),
    dict(active_version=[]), dict(active_version='missing'), dict(keys={}), dict(keys=[]), dict(keys={'v1': True}),
    dict(keys={'v1': 'bad'}), dict(keys={'invalid key': KEY1}), dict(extra='fixture-private-marker')])
def test_recovery_parser_refuses_unsupported_settings(change, ring):
    value = json.loads(encode_keyring(ring)); value.update(change)
    with pytest.raises(RecoveryError): parse_keyring(json.dumps(value).encode())

@pytest.mark.parametrize('raw', [b'{"schema_version":1,"schema_version":1}',
    b'{"schema_version":1,"purpose":"meta_credential_envelopes","active_version":"v1","keys":{"v1":"x","v1":"y"}}'])
def test_recovery_duplicate_json_never_overwrites_keys(raw):
    with pytest.raises(RecoveryError): parse_keyring(raw)

@pytest.mark.parametrize('kind', ['missing', 'empty', 'oversize', 'directory', 'symlink', 'pipe', 'public', 'hardlink'])
def test_recovery_file_refuses_untrusted_objects(tmp_path, ring, kind):
    path = tmp_path / 'backup'
    if kind == 'directory': path.mkdir()
    elif kind == 'pipe': os.mkfifo(path)
    elif kind != 'missing':
        write_keyring_backup(path, ring)
        if kind == 'empty': path.write_bytes(b'')
        elif kind == 'oversize': path.write_bytes(b'x' * (MAX_BACKUP_BYTES + 1))
        elif kind == 'symlink':
            alias = tmp_path / 'alias'; alias.symlink_to(path); path = alias
        elif kind == 'hardlink': os.link(path, tmp_path / 'alias')
        elif kind == 'public': path.chmod(0o644)
    with pytest.raises(RecoveryError) as failure: read_keyring_backup(path)
    assert failure.value.__context__ is None

@pytest.mark.parametrize('failure_point', ['file_fsync', 'directory_fsync', 'write', 'open'])
def test_recovery_failed_persist_restart_keeps_previous_backup(tmp_path, monkeypatch, ring, failure_point):
    prior, candidate = tmp_path / 'prior', tmp_path / 'candidate'
    write_keyring_backup(prior, ring)
    rotated = replace(ring, active_version='v2')
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs): raise OSError('fixture-secret-error')
        if failure_point == 'open': patch.setattr(os, 'open', fail)
        elif failure_point == 'write': patch.setattr(os, 'fdopen', fail)
        else:
            actual = os.fsync; calls = []
            def fsync(fd):
                calls.append(fd)
                if failure_point == 'file_fsync' or len(calls) == 2: fail()
                return actual(fd)
            patch.setattr(os, 'fsync', fsync)
        with pytest.raises(RecoveryError) as failure: write_keyring_backup(candidate, rotated)
        assert failure.value.__context__ is None
    assert not candidate.exists()
    restarted = read_keyring_backup(prior)
    assert restarted.active_version == 'v1'
    assert verify_restoration(ring, restarted, [probe(ring)])['envelopes_decrypted'] == 1

def test_recovery_export_refuses_overwrite_and_symlink(tmp_path, ring):
    path = tmp_path / 'backup'; write_keyring_backup(path, ring); original = path.read_bytes()
    for target in (path, tmp_path / 'alias'):
        if target != path: target.symlink_to(path)
        with pytest.raises(RecoveryError): write_keyring_backup(target, replace(ring, active_version='v2'))
        assert path.read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600
    assert KEY1 not in repr(ring) and KEY1 not in repr(parse_keyring(original))

@pytest.mark.parametrize('change', [dict(owner=UUID('22222222-2222-4222-8222-222222222222')),
    dict(owner=None), dict(purpose='facebook_user'), dict(purpose=None), dict(key_version='v2'),
    dict(key_version='missing'), dict(key_version=[]), dict(ciphertext=b'corrupt'), dict(ciphertext=None)])
def test_recovery_exact_owner_purpose_version_ciphertext_required(ring, change):
    with pytest.raises(RecoveryError) as error:
        verify_restoration(ring, parse_keyring(encode_keyring(ring)), [replace(probe(ring), **change)])
    assert error.value.__context__ is None

@pytest.mark.parametrize('probes', [None, [], (), {}, [None], [False]])
def test_recovery_no_vacuous_verification(ring, probes):
    with pytest.raises(RecoveryError): verify_restoration(ring, ring, probes)

def test_recovery_retirement_requires_matching_ciphertext_versions(ring):
    old = probe(ring); restored = parse_keyring(encode_keyring(replace(ring, active_version='v2')))
    assert verify_restoration(ring, restored, [old])['versions_decrypted'] == ['v1']
    version, data = restored.cipher().rotate(old.owner, old.purpose, old.key_version, old.ciphertext)
    new = replace(old, key_version=version, ciphertext=data); retired = RecoveryKeyring('v2', {'v2': KEY2})
    assert verify_restoration(restored, retired, [new])['versions_decrypted'] == ['v2']
    for first, second, material in ((ring, retired, old), (ring, RecoveryKeyring('v1', {'v1': KEY2}), old),
        (restored, RecoveryKeyring('v1', {'v1': KEY1}), new)):
        with pytest.raises(RecoveryError): verify_restoration(first, second, [material])

@pytest.mark.parametrize('argv', [[], ['--keyring', 'fixture-private-path'], ['--fixture-drill', 'extra'],
    [None], None, '--fixture-drill', ['x' * 65], ['\n']])
def test_recovery_cli_no_implicit_secrets_and_sanitized_errors(argv, capsys, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['social_meta_recovery'])
    assert main(argv) == 2
    output = capsys.readouterr()
    assert 'fixture-private-path' not in output.out + output.err
    assert 'production_authorized": false' in output.out

def test_recovery_cli_runs_without_configured_environment():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', '-m', 'scripts.social_meta_recovery', '--fixture-drill'], cwd=root,
        env={'PATH': os.environ['PATH'], 'PYTHONPATH': '.', 'PYTHON_DOTENV_DISABLED': '1'},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'VERIFIED_BY_EXECUTION'
    assert all(v not in result.stdout + result.stderr for v in (KEY1, KEY2, 'INERT-RECOVERY-MARKER'))

@pytest.mark.parametrize('fail_commit', [True, False])
def test_recovery_service_rotation_reconstructed_after_commit_or_failure(tmp_path, fail_commit, monkeypatch):
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine, event, select
    from sqlalchemy.orm import Session
    from social.models import Base, SOCIAL_TABLES
    from social.connections.config import MetaConfig
    from social.connections.models import SocialCredential
    from social.connections.crypto import CredentialCipher
    from social.connections.contracts import AccountCommand
    from test_connections_support import svc, start, complete, select_asset, FakeGraph, REDIRECT, ACTOR, BINDING
    from uuid import uuid4

    engine = create_engine('sqlite:///' + str(tmp_path / 'owned-recovery.db'))
    Base.metadata.create_all(engine, tables=SOCIAL_TABLES)
    config = MetaConfig(enabled=True, app_configuration_validated=True, app_id='123', app_secret='fixture',
        redirect_uris=(REDIRECT,), access_mode='owned_standard', active_key_version='v1', encryption_keys={'v1': KEY1})
    graph = FakeGraph()
    try:
        with Session(engine) as db:
            service = svc(db, config, graph)
            flow, state = start(service); complete(service, state)
            accounts = select_asset(service, UUID(flow['flow_id']))['accounts']
            account_id = UUID(accounts[0]['id'])
            health = service.health(account_id); db.rollback()
            before = {r.id: (r.version, r.key_version, r.encrypted_bundle, r.credential_kind)
                      for r in db.scalars(select(SocialCredential))}
            db.rollback()
            service = svc(db, replace(config, active_key_version='v2', encryption_keys={'v1': KEY1, 'v2': KEY2}), graph)
            def refused(session): raise RuntimeError('fixture-failed-commit')
            if fail_commit: event.listen(db, 'before_commit', refused)
            try:
                call = lambda: service.account_command(account_id, ACTOR, BINDING, 'rotate/' + str(account_id), uuid4(),
                    AccountCommand(expected_credential_id=UUID(health['credential_id']),
                        expected_credential_version=health['credential_version'], reason='Fixture rotation'), uuid4(), rotate=True)
                if fail_commit:
                    with pytest.raises(RuntimeError, match='fixture-failed-commit'): call()
                else: call()
            finally:
                if fail_commit: event.remove(db, 'before_commit', refused)
        engine.dispose()
        # New engine/session/cipher: restart never trusts the old identity map.
        restarted_engine = create_engine('sqlite:///' + str(tmp_path / 'owned-recovery.db'))
        try:
            with Session(restarted_engine) as restarted:
                after = list(restarted.scalars(select(SocialCredential)))
                assert len(after) == len(before) == 2
                for row in after:
                    version, key_version, data, purpose = before[row.id]
                    expected = CredentialCipher('v1', {'v1': KEY1}).decrypt(row.id, purpose, key_version, data)
                    if fail_commit:
                        assert (row.version, row.key_version, row.encrypted_bundle) == (version, key_version, data)
                        reader = CredentialCipher('v1', {'v1': KEY1})
                    else:
                        assert row.version == version + 1 and row.key_version == 'v2' and row.encrypted_bundle != data
                        reader = CredentialCipher('v2', {'v2': KEY2})
                    assert reader.decrypt(row.id, purpose, row.key_version, row.encrypted_bundle) == expected
        finally: restarted_engine.dispose()
    finally: engine.dispose()


def test_recovery_direct_keyring_cannot_bypass_version_inventory_limit(ring):
    oversized = RecoveryKeyring('v1', {'v1': KEY1, **{str(i): KEY1 for i in range(65)}})
    with pytest.raises(RecoveryError):
        verify_restoration(oversized, oversized, [probe(ring)])

@pytest.mark.parametrize('operation', ['encode', 'write'])
def test_recovery_direct_key_container_shape_cannot_be_coerced(tmp_path, operation):
    invalid = RecoveryKeyring('v1', [('v1', KEY1)])
    with pytest.raises(RecoveryError):
        if operation == 'encode': encode_keyring(invalid)
        else: write_keyring_backup(tmp_path / 'backup', invalid)

@pytest.mark.parametrize('operation', ['read', 'write'])
def test_recovery_cleanup_failure_keeps_sanitized_error_and_removes_candidate(tmp_path, ring, monkeypatch, operation):
    prior = tmp_path / 'prior'; write_keyring_backup(prior, ring)
    candidate = tmp_path / 'candidate'
    real_close = os.close
    def failed_close(fd):
        real_close(fd)
        raise OSError('fixture-private-close-marker')
    def failed_operation(*args, **kwargs): raise OSError('fixture-private-operation-marker')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'close', failed_close)
        if operation == 'read': patch.setattr(os, 'fstat', failed_operation)
        else: patch.setattr(os, 'fdopen', failed_operation)
        with pytest.raises(RecoveryError) as error:
            if operation == 'read': read_keyring_backup(prior)
            else: write_keyring_backup(candidate, ring)
        assert error.value.__context__ is None
    assert not candidate.exists()
    assert read_keyring_backup(prior).active_version == 'v1'

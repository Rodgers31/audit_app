"""Synthetic inventory acceptance, independent commitments and restored backups."""
import base64
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

import pytest

from social.connections.crypto import CredentialCipher
from social.connections.recovery import RecoveryKeyring, encode_keyring
from social.privacy.subjects import SubjectDigester
from social.recovery_inventory import InventoryRecoveryError, verify_inventory_continuity


def uid(number):
    return str(UUID(int=number))


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest_backup(active='current', keys=None):
    return raw({'schema_version': 1, 'purpose': 'meta_subject_digests',
                'active_version': active, 'keys': keys or {'old': '61' * 32, 'current': '62' * 32}})


def commitment(row):
    # Independently authored witness algorithm, no production manifest builder.
    return hashlib.sha256(raw(row)).hexdigest()


@dataclass
class Fixture:
    source: dict
    restored: dict
    manifest: dict
    subjects: dict
    envelopes: bytes
    digests: bytes
    candidate_envelopes: bytes
    candidate_digests: bytes

    def verify(self):
        return verify_inventory_continuity(
            raw(self.source), raw(self.restored), raw(self.manifest), raw(self.subjects),
            self.envelopes, bytes(bytearray(self.envelopes)), self.digests,
            bytes(bytearray(self.digests)), self.candidate_envelopes, self.candidate_digests)


@pytest.fixture
def inventory():
    keys = {k: base64.urlsafe_b64encode(bytes([n]) * 32).decode() for n, k in enumerate(('old', 'current', 'next'), 1)}
    ring = RecoveryKeyring('current', {k: keys[k] for k in ('old', 'current')})
    digester = SubjectDigester('current', {'old': b'a' * 32, 'current': b'b' * 32})

    def encrypted(owner, purpose, version='old', bundle=None):
        c = CredentialCipher(version, keys)
        return base64.b64encode(c.encrypt(UUID(owner), purpose, bundle or {'inert': 'fixture'})[1]).decode()

    credentials = [dict(id=uid(1), credential_kind='facebook_user', parent_credential_id=None,
                        version=1, key_version='old', encrypted_bundle=encrypted(uid(1), 'facebook_user')),
                   # Retained orphan/revoked rows must still be decrypted.
                   dict(id=uid(2), credential_kind='facebook_page', parent_credential_id=uid(1),
                        version=2, key_version='current', encrypted_bundle=encrypted(uid(2), 'facebook_page', 'current'))]
    flows = [dict(id=uid(3), status='awaiting_selection', key_version='old', encrypted_verifier=None,
                  encrypted_pending_grant=encrypted(uid(3), 'oauth_pending')),
             dict(id=uid(4), status='initiated', key_version='current', encrypted_verifier=encrypted(uid(4), 'oauth_start', 'current'), encrypted_pending_grant=None),
             dict(id=uid(5), status='expired', key_version='old', encrypted_verifier=None, encrypted_pending_grant=None)]
    owner = dict(id=uid(6), app_id='100', digest_version='old', subject_digest=digester.digest('100', '200', 'old'),
                 reference_key='credential:' + uid(1) + ':1', flow_id=uid(3), credential_id=uid(1),
                 credential_version=1, account_id=None, page_id=None, generation_at='2026-10-01T00:00:00Z')
    affected = [{k: owner[k] for k in ('flow_id', 'credential_id', 'credential_version', 'account_id', 'page_id')} | {'ownership_id': owner['id']}]
    code = 'f' * 64
    receipt = dict(id=uid(7), app_id='100', kind='data_deletion', digest_version='current',
                   subject_digest=digester.digest('100', '200'), event_key='a' * 64,
                   request_fingerprint='b' * 64, affected=affected, state='pending_retention_review',
                   resolution='indexed_partial', audit_id=uid(8), confirmation_hash=hashlib.sha256(code.encode()).hexdigest(),
                   confirmation_key_version='old', encrypted_confirmation=encrypted(uid(7), 'privacy_confirmation', bundle={'code': code}))
    tables = dict(credentials=credentials, flows=flows, ownership=[owner], receipts=[receipt],
                  variants=[dict(id=uid(9), app_id='100', kind='data_deletion', fingerprint='b' * 64, receipt_id=uid(7))], accounts=[], audits=[{'id': uid(8)}])
    source = dict(schema_version=1, snapshot_id=uid(100), tables=tables)
    manifest = dict(schema_version=1, snapshot_id=uid(100), active_envelope_version='current', active_digest_version='current',
                    records={table: {r['id']: commitment(r) for r in rows} for table, rows in tables.items()})
    subjects = dict(schema_version=1, snapshot_id=uid(100), records=[dict(table=t, id=uid(i), subject='200') for t, i in [('ownership', 6), ('receipts', 7)]])
    return Fixture(source, deepcopy(source), manifest, subjects, encode_keyring(ring), digest_backup(),
                   encode_keyring(RecoveryKeyring('next', dict(keys))),
                   digest_backup('next', {'old': '61' * 32, 'current': '62' * 32, 'next': '63' * 32}))


def test_complete_supplied_snapshot_and_candidate_rotation(inventory):
    result = inventory.verify()
    assert result['status'] == 'VERIFIED_BY_EXECUTION'
    assert result['records_verified'] == 9
    assert result['envelopes_verified'] == 5
    assert result['subject_records_verified'] == 2
    assert result['snapshot_coverage_verified'] is True
    for flag in ('database_coverage_verified', 'backup_custody_verified', 'production_authorized',
                 'retirement_authorized', 'deletion_authorized', 'deletion_completed'):
        assert result[flag] is False
    assert result['candidate_envelope_version'] == result['candidate_digest_version'] == 'next'
    assert '200' not in repr(result)


@pytest.mark.parametrize('credential_id', [None, uid(1), uid(2)])
def test_inventory_includes_accounts_with_optional_credential(inventory, credential_id):
    row = {'id': uid(10), 'credential_id': credential_id}
    inventory.source['tables']['accounts'].append(row)
    inventory.restored = deepcopy(inventory.source)
    inventory.manifest['records']['accounts'][row['id']] = commitment(row)
    result = inventory.verify()
    assert result['records_verified'] == 10
    assert result['snapshot_coverage_verified'] is True
    assert result['production_authorized'] is False


@pytest.mark.parametrize('credential_id', [uid(999), '', False, 0, 'not-a-uuid'])
def test_optional_account_credential_still_refuses_dangling_or_malformed_values(inventory, credential_id):
    row = {'id': uid(10), 'credential_id': credential_id}
    inventory.source['tables']['accounts'].append(row)
    inventory.restored = deepcopy(inventory.source)
    inventory.manifest['records']['accounts'][row['id']] = commitment(row)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('table', ['credentials', 'flows', 'ownership', 'receipts', 'variants', 'audits'])
@pytest.mark.parametrize('side', ['source', 'restored', 'both'])
def test_omitted_rows_cannot_certify_coverage(inventory, table, side):
    for name in ('source', 'restored') if side == 'both' else (side,):
        getattr(inventory, name)['tables'][table].pop()
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('table', ['credentials', 'flows', 'ownership', 'receipts', 'variants', 'audits'])
def test_duplicate_ids_rejected_even_with_matching_counts(inventory, table):
    inventory.restored['tables'][table].append(inventory.restored['tables'][table][0])
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('part', ['restored', 'manifest', 'subjects'])
def test_cross_snapshot_input_refused(inventory, part):
    getattr(inventory, part)['snapshot_id'] = uid(999)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


def test_unreferenced_envelope_is_not_silently_ignored(inventory):
    row = inventory.restored['tables']['credentials'][1]
    row['encrypted_bundle'] = base64.b64encode(b'tampered').decode()
    # Independently trusted witness can describe a corrupt source; decrypt still must fail.
    inventory.source = deepcopy(inventory.restored)
    inventory.manifest['records']['credentials'][row['id']] = commitment(row)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


def test_alias_key_bytes_do_not_authenticate_version_labels(inventory):
    # HMAC remains valid when labels alias, but independent row commitment binds the label.
    keys = {'old': '61' * 32, 'current': '61' * 32}
    inventory.digests = digest_backup(keys=keys)
    r = inventory.source['tables']['receipts'][0]
    r['subject_digest'] = inventory.source['tables']['ownership'][0]['subject_digest']
    inventory.manifest['records']['receipts'][r['id']] = commitment(r)
    inventory.restored = deepcopy(inventory.source)
    inventory.restored['tables']['ownership'][0]['digest_version'] = 'current'
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('attribute,purpose', [('candidate_envelopes', 'envelope'), ('candidate_digests', 'digest')])
def test_retirement_missing_referenced_keys_refuses(inventory, attribute, purpose):
    if purpose == 'envelope':
        ring = json.loads(inventory.candidate_envelopes)
    else:
        ring = json.loads(inventory.candidate_digests)
    del ring['keys']['old']
    setattr(inventory, attribute, raw(ring))
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('change', ['missing_owner', 'wrong_flow', 'wrong_generation', 'wrong_app', 'empty_ledger', 'variant_missing_receipt'])
def test_privacy_ledger_reference_failures_even_when_witness_matches(inventory, change):
    tables = inventory.source['tables']
    if change == 'missing_owner': tables['receipts'][0]['affected'][0]['ownership_id'] = uid(500)
    if change == 'wrong_flow': tables['receipts'][0]['affected'][0]['flow_id'] = uid(4)
    if change == 'wrong_generation': tables['receipts'][0]['affected'][0]['credential_version'] = 7
    if change == 'wrong_app': tables['ownership'][0]['app_id'] = '101'
    if change == 'empty_ledger': tables['receipts'] = []
    if change == 'variant_missing_receipt': tables['variants'][0]['receipt_id'] = uid(500)
    inventory.restored = deepcopy(inventory.source)
    inventory.manifest['records'] = {t: {r['id']: commitment(r) for r in rows} for t, rows in tables.items()}
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('value', [None, True, b'', b'{}', b'[]', b'{"schema_version":1,"schema_version":1}', b'NaN'])
def test_malformed_input_has_fixed_private_failure(inventory, value):
    with pytest.raises(InventoryRecoveryError) as caught:
        verify_inventory_continuity(value, raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
                                    inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
                                    inventory.candidate_envelopes, inventory.candidate_digests)
    assert str(caught.value) == 'RECOVERY_INVENTORY_REFUSED'
    assert caught.value.__context__ is None


def recatalog(inventory):
    inventory.restored = deepcopy(inventory.source)
    inventory.manifest['records'] = {t: {r['id']: commitment(r) for r in rows}
                                     for t, rows in inventory.source['tables'].items()}


@pytest.mark.parametrize('attribute', ['source_snapshot', 'restored_snapshot', 'independent_manifest', 'subject_proofs',
                                     'primary_envelopes', 'restored_envelopes', 'primary_digests', 'restored_digests',
                                     'candidate_envelopes', 'candidate_digests'])
def test_all_input_boundaries_reject_objects_without_callbacks(inventory, attribute):
    class Hostile:
        def __bytes__(self):
            pytest.fail('supplied conversion callback ran')
        def __iter__(self):
            pytest.fail('supplied iteration callback ran')
    args = dict(source_snapshot=raw(inventory.source), restored_snapshot=raw(inventory.restored),
                independent_manifest=raw(inventory.manifest), subject_proofs=raw(inventory.subjects),
                primary_envelopes=inventory.envelopes, restored_envelopes=inventory.envelopes,
                primary_digests=inventory.digests, restored_digests=inventory.digests,
                candidate_envelopes=inventory.candidate_envelopes, candidate_digests=inventory.candidate_digests)
    args[attribute] = Hostile()
    with pytest.raises(InventoryRecoveryError):
        verify_inventory_continuity(**args)


@pytest.mark.parametrize('attribute', ['envelopes', 'digests', 'candidate_envelopes', 'candidate_digests'])
@pytest.mark.parametrize('bad', [b'', b'{}', b'[]', b'null', b'NaN', b'x' * 65537])
def test_absent_wrong_and_oversized_backup_material(inventory, attribute, bad):
    setattr(inventory, attribute, bad)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('table,field,bad', [
    ('credentials', 'version', True), ('credentials', 'version', 0), ('credentials', 'version', 2**63),
    ('flows', 'status', None), ('flows', 'status', 'unknown'), ('flows', 'key_version', ''),
    ('ownership', 'credential_version', True), ('ownership', 'credential_version', 2),
    ('ownership', 'flow_id', uid(999)), ('ownership', 'reference_key', 'wrong'),
    ('ownership', 'generation_at', None), ('ownership', 'page_id', 10),
    ('receipts', 'affected', {}), ('receipts', 'state', 'deleted'),
    ('receipts', 'confirmation_hash', '0' * 64), ('receipts', 'digest_version', 'absent'),
    ('receipts', 'audit_id', uid(999)), ('receipts', 'encrypted_confirmation', 'aA=='),
    ('variants', 'fingerprint', ''), ('variants', 'app_id', '101'),
])
def test_semantic_shapes_refused_with_coherent_witness(inventory, table, field, bad):
    inventory.source['tables'][table][0][field] = bad
    recatalog(inventory)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


def test_pending_grant_missing_with_coherent_witness(inventory):
    inventory.source['tables']['flows'][0]['encrypted_pending_grant'] = None
    recatalog(inventory)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('field', ['app_id', 'subject'])
def test_independent_subject_mismatch_refused(inventory, field):
    if field == 'subject':
        inventory.subjects['records'][0]['subject'] = '201'
    else:
        inventory.source['tables']['ownership'][0]['app_id'] = '101'
        recatalog(inventory)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('change', ['missing', 'extra', 'duplicate'])
def test_subject_proofs_must_exactly_cover_privacy_records(inventory, change):
    rows = inventory.subjects['records']
    if change == 'missing': rows.pop()
    if change == 'extra': rows.append({'table': 'ownership', 'id': uid(999), 'subject': '200'})
    if change == 'duplicate': rows[1] = deepcopy(rows[0])
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('error', [RuntimeError, ValueError, KeyboardInterrupt, SystemExit])
def test_sanitized_ordinary_crypto_failures_and_interrupts(inventory, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error('PRIVATE_TEST_MARKER')
    monkeypatch.setattr(CredentialCipher, 'decrypt', fail)
    expected = error if issubclass(error, BaseException) and not issubclass(error, Exception) else InventoryRecoveryError
    with pytest.raises(expected) as caught:
        inventory.verify()
    if expected is InventoryRecoveryError:
        assert str(caught.value) == 'RECOVERY_INVENTORY_REFUSED'
        assert caught.value.__context__ is None
        assert 'PRIVATE_TEST_MARKER' not in repr(caught.value)


@pytest.mark.parametrize('count', [1000, 1001])
def test_total_record_ceiling(inventory, count):
    rows = inventory.source['tables']['audits']
    rows.extend({'id': uid(i + 1000)} for i in range(count - 9))
    recatalog(inventory)
    if count == 1000:
        assert inventory.verify()['records_verified'] == 1000
    else:
        with pytest.raises(InventoryRecoveryError):
            inventory.verify()


def test_snapshot_bytes_ceiling_before_json_decode(inventory, monkeypatch):
    import social.recovery_inventory as module
    def fail(*args, **kwargs):
        pytest.fail('oversized JSON was decoded')
    monkeypatch.setattr(module.json, 'loads', fail)
    with pytest.raises(InventoryRecoveryError):
        module.verify_inventory_continuity(b' ' * 2_000_001, b'{}', b'{}', b'{}', b'{}', b'{}', b'{}', b'{}', b'{}', b'{}')


def test_input_bytes_and_result_are_not_shared_mutable_state(inventory):
    before = deepcopy(inventory)
    result = inventory.verify()
    assert inventory == before
    result['snapshot_coverage_verified'] = False
    assert inventory.verify()['snapshot_coverage_verified'] is True


def test_row_order_does_not_define_identity(inventory):
    inventory.restored['tables']['credentials'].reverse()
    inventory.restored['tables']['flows'].reverse()
    assert inventory.verify()['records_verified'] == 9


def test_old_immutable_ownership_generation_survives_current_credential_rotation(inventory):
    inventory.source['tables']['credentials'][0]['version'] = 2
    recatalog(inventory)
    assert inventory.verify()['subject_records_verified'] == 2


@pytest.mark.parametrize('purpose', ['envelope', 'digest'])
def test_restored_active_key_must_match_primary_even_before_first_new_write(inventory, purpose):
    # A normal post-rotation state may have no retained rows at the active label.
    if purpose == 'envelope':
        from social.connections.recovery import parse_keyring
        source_cipher = parse_keyring(inventory.envelopes).cipher()
        for row in inventory.source['tables']['credentials']:
            bundle = source_cipher.decrypt(UUID(row['id']), row['credential_kind'], row['key_version'], base64.b64decode(row['encrypted_bundle']))
            source_cipher.active_version = 'old'
            _, encrypted = source_cipher.encrypt(UUID(row['id']), row['credential_kind'], bundle)
            row.update(key_version='old', encrypted_bundle=base64.b64encode(encrypted).decode())
        for row in inventory.source['tables']['flows']:
            for field, label in [('encrypted_verifier', 'oauth_start'), ('encrypted_pending_grant', 'oauth_pending')]:
                if row[field] is not None:
                    bundle = source_cipher.decrypt(UUID(row['id']), label, row['key_version'], base64.b64decode(row[field]))
                    source_cipher.active_version = 'old'
                    _, encrypted = source_cipher.encrypt(UUID(row['id']), label, bundle)
                    row.update(key_version='old', **{field: base64.b64encode(encrypted).decode()})
        restored = json.loads(inventory.envelopes)
        restored['keys']['current'] = base64.urlsafe_b64encode(b'x' * 32).decode()
    else:
        row = inventory.source['tables']['receipts'][0]
        row.update(digest_version='old', subject_digest=inventory.source['tables']['ownership'][0]['subject_digest'])
        restored = json.loads(inventory.digests)
        restored['keys']['current'] = '78' * 32
    recatalog(inventory)
    args = [raw(inventory.source), raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
            inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
            inventory.candidate_envelopes, inventory.candidate_digests]
    args[5 if purpose == 'envelope' else 7] = raw(restored)
    with pytest.raises(InventoryRecoveryError):
        verify_inventory_continuity(*args)


@pytest.mark.parametrize('value', ['2026-99-99T99:99:99Z', '0000-01-01T00:00:00Z', '2026-02-30T00:00:00Z'])
def test_impossible_ownership_timestamp_refused_with_matching_manifest(inventory, value):
    inventory.source['tables']['ownership'][0]['generation_at'] = value
    recatalog(inventory)
    with pytest.raises(InventoryRecoveryError):
        inventory.verify()


@pytest.mark.parametrize('purpose', ['envelope', 'digest'])
@pytest.mark.parametrize('change', ['extra_restored', 'missing_unreferenced', 'candidate_reassigns_label'])
def test_backup_key_inventory_and_candidate_label_identity(inventory, purpose, change):
    args = [raw(inventory.source), raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
            inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
            inventory.candidate_envelopes, inventory.candidate_digests]
    primary_index, restored_index, candidate_index = (4, 5, 8) if purpose == 'envelope' else (6, 7, 9)
    primary = json.loads(args[primary_index])
    if change == 'missing_unreferenced':
        primary['keys']['unused'] = base64.urlsafe_b64encode(b'u' * 32).decode() if purpose == 'envelope' else '75' * 32
        args[primary_index] = raw(primary)
    else:
        index = restored_index if change == 'extra_restored' else candidate_index
        other = json.loads(args[index])
        other['keys']['unused' if change == 'extra_restored' else 'current'] = base64.urlsafe_b64encode(b'u' * 32).decode() if purpose == 'envelope' else '75' * 32
        args[index] = raw(other)
    with pytest.raises(InventoryRecoveryError):
        verify_inventory_continuity(*args)


@pytest.mark.parametrize('purpose,limit', [('envelope', 64), ('digest', 16)])
def test_key_count_ceiling(inventory, purpose, limit):
    args = [raw(inventory.source), raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
            inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
            inventory.candidate_envelopes, inventory.candidate_digests]
    index = 8 if purpose == 'envelope' else 9
    ring = json.loads(args[index])
    original_count = len(ring['keys'])
    for n in range(limit - original_count):
        ring['keys']['unused' + str(n)] = next(iter(ring['keys'].values()))
    args[index] = raw(ring)
    assert verify_inventory_continuity(*args)['status'] == 'VERIFIED_BY_EXECUTION'
    ring['keys']['overflow'] = next(iter(ring['keys'].values()))
    args[index] = raw(ring)
    with pytest.raises(InventoryRecoveryError):
        verify_inventory_continuity(*args)


def test_real_fresh_process_replays_same_synthetic_snapshot_and_backup_bytes(inventory):
    import os
    from pathlib import Path
    import subprocess
    import sys
    payload = [raw(inventory.source), raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
               inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
               inventory.candidate_envelopes, inventory.candidate_digests]
    script = ('import base64,json,sys; from social.recovery_inventory import verify_inventory_continuity; '
              'args=[base64.b64decode(v) for v in json.load(sys.stdin)]; '
              'print(json.dumps(verify_inventory_continuity(*args),sort_keys=True))')
    backend = str(Path(__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, '-B', '-c', script],
                            input=raw([base64.b64encode(v).decode() for v in payload]),
                            capture_output=True, cwd=backend, timeout=15,
                            env={'PATH': os.defpath, 'PYTHONPATH': backend, 'PYTHONDONTWRITEBYTECODE': '1',
                                 'PYTHON_DOTENV_DISABLED': '1'})
    assert result.returncode == 0, result.stderr.decode()
    expected = inventory.verify()
    expected['missing_prerequisites'] = list(expected['missing_prerequisites'])
    assert json.loads(result.stdout) == expected


def test_complete_account_flow_and_deauthorization_projection(inventory):
    tables = inventory.source['tables']
    owner = tables['ownership'][0]
    account_owner = deepcopy(owner)
    account_owner.update(id=uid(11), credential_id=uid(2), credential_version=2, account_id=uid(10), page_id='300',
                         reference_key='credential:' + uid(2) + ':2:' + uid(10))
    flow_owner = deepcopy(owner)
    flow_owner.update(id=uid(12), credential_id=None, credential_version=None, reference_key='flow:' + uid(3))
    tables['accounts'] = [{'id': uid(10), 'credential_id': uid(2)}]
    tables['ownership'].extend([account_owner, flow_owner])
    receipt = tables['receipts'][0]
    receipt.update(kind='deauthorization', state='blocked_future_mutations', confirmation_hash=None,
                   confirmation_key_version=None, encrypted_confirmation=None)
    for o in (account_owner, flow_owner):
        receipt['affected'].append({k: o[k] for k in ('flow_id', 'credential_id', 'credential_version', 'account_id', 'page_id')} | {'ownership_id': o['id']})
        inventory.subjects['records'].append(dict(table='ownership', id=o['id'], subject='200'))
    tables['variants'][0]['kind'] = 'deauthorization'
    recatalog(inventory)
    result = inventory.verify()
    assert result['records_verified'] == 12
    assert result['envelopes_verified'] == 4
    assert result['subject_records_verified'] == 4


@pytest.mark.parametrize('count', [500, 501])
def test_frozen_affected_reference_ceiling(inventory, count):
    tables = inventory.source['tables']
    template = tables['ownership'][0]
    tables['ownership'] = []
    tables['receipts'][0]['affected'] = []
    inventory.subjects['records'] = [r for r in inventory.subjects['records'] if r['table'] == 'receipts']
    tables['credentials'][0]['version'] = count
    for n in range(1, count + 1):
        owner = deepcopy(template)
        owner.update(id=uid(1000 + n), credential_version=n, reference_key='credential:' + uid(1) + ':' + str(n))
        tables['ownership'].append(owner)
        tables['receipts'][0]['affected'].append({k: owner[k] for k in ('flow_id', 'credential_id', 'credential_version', 'account_id', 'page_id')} | {'ownership_id': owner['id']})
        inventory.subjects['records'].append(dict(table='ownership', id=owner['id'], subject='200'))
    recatalog(inventory)
    if count == 500:
        assert inventory.verify()['subject_records_verified'] == 501
    else:
        with pytest.raises(InventoryRecoveryError):
            inventory.verify()


@pytest.mark.parametrize('size', [128_000, 128_001])
def test_decoded_envelope_allocation_ceiling(size):
    from social.recovery_inventory import _ciphertext
    encoded = base64.b64encode(b'x' * size).decode()
    if size == 128_000:
        assert _ciphertext(encoded) == b'x' * size
    else:
        with pytest.raises(InventoryRecoveryError):
            _ciphertext(encoded)


def test_same_backup_bytes_never_upgrade_custody_or_database_authority(inventory):
    # The verifier cannot authenticate who supplied any bytes; identity is a separate gate.
    result = inventory.verify()
    assert result['snapshot_coverage_verified'] is True
    assert result['database_coverage_verified'] is result['backup_custody_verified'] is False
    assert result['production_authorized'] is result['retirement_authorized'] is False


def test_utf16_snapshot_cannot_bypass_utf8_contract(inventory):
    args = [raw(inventory.source).decode().encode('utf-16'), raw(inventory.restored), raw(inventory.manifest), raw(inventory.subjects),
            inventory.envelopes, inventory.envelopes, inventory.digests, inventory.digests,
            inventory.candidate_envelopes, inventory.candidate_digests]
    with pytest.raises(InventoryRecoveryError):
        verify_inventory_continuity(*args)

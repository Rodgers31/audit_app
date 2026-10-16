"""Explicit operator-only recovery projection; no IO, environment or registration.

The manifest is an independently reconciled trust input, not an authentication
mechanism. Matching snapshots never establish DB coverage or backup custody.
Only exact bytes cross this boundary, excluding caller mappings and callbacks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime
from uuid import UUID

from .connections.recovery import parse_keyring
from .privacy.subjects import SubjectDigester

MAX_SNAPSHOT_BYTES = 2_000_000
MAX_RECORDS = 1000
MAX_ENVELOPE_BYTES = 128_000
MAX_AFFECTED = 500
HEX = r'[a-f0-9]{64}'
LABEL = r'[A-Za-z0-9_.-]{1,64}'
DIGEST_LABEL = r'[A-Za-z0-9_-]{1,32}'
DECIMAL = r'[1-9][0-9]{0,63}'
REF_FIELDS = frozenset(('ownership_id', 'flow_id', 'credential_id', 'credential_version', 'account_id', 'page_id'))
FIELDS = {
    'credentials': frozenset(('id', 'credential_kind', 'parent_credential_id', 'version', 'key_version', 'encrypted_bundle')),
    'flows': frozenset(('id', 'status', 'key_version', 'encrypted_verifier', 'encrypted_pending_grant')),
    'ownership': frozenset(('id', 'app_id', 'digest_version', 'subject_digest', 'reference_key', 'flow_id',
                           'credential_id', 'credential_version', 'account_id', 'page_id', 'generation_at')),
    'receipts': frozenset(('id', 'app_id', 'kind', 'digest_version', 'subject_digest', 'event_key',
                          'request_fingerprint', 'affected', 'state', 'resolution', 'audit_id',
                          'confirmation_hash', 'confirmation_key_version', 'encrypted_confirmation')),
    'variants': frozenset(('id', 'app_id', 'kind', 'fingerprint', 'receipt_id')),
    'accounts': frozenset(('id', 'credential_id')),
    'audits': frozenset(('id',)),
}
TABLES = frozenset(FIELDS)
MISSING_PREREQUISITES = (
    'authenticated_snapshot_extraction_and_complete_database_inventory',
    'independent_off_host_backup_custody_and_loss_of_primary_store_drill',
    'all_retained_backups_wal_and_external_deletion_ledger_reconciliation',
    'approved_retention_policy_and_separate_deletion_or_key_retirement_authority',
    'actual_store_failed_persist_restart_and_deployed_runtime_acceptance',
)


class InventoryRecoveryError(ValueError):
    def __init__(self):
        super().__init__('RECOVERY_INVENTORY_REFUSED')


def _require(condition):
    if not condition:
        raise InventoryRecoveryError()


def _matches(value, pattern):
    return type(value) is str and re.fullmatch(pattern, value) is not None


def _uuid(value):
    _require(type(value) is str and len(value) == 36)
    parsed = UUID(value)
    _require(parsed.int != 0 and str(parsed) == value)
    return value


def _optional_uuid(value):
    return None if value is None else _uuid(value)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _constant(value):
    raise InventoryRecoveryError()


def _json(raw, limit):
    _require(type(raw) is bytes and 1 <= len(raw) <= limit)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)


def _shape(value, fields):
    _require(type(value) is dict and set(value) == fields)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def _digest_backup(raw):
    value = _json(raw, 65536)
    _shape(value, {'schema_version', 'purpose', 'active_version', 'keys'})
    _require(type(value['schema_version']) is int and value['schema_version'] == 1
             and value['purpose'] == 'meta_subject_digests' and _matches(value['active_version'], DIGEST_LABEL))
    keys = value['keys']
    _require(type(keys) is dict and 1 <= len(keys) <= 16)
    _require(all(_matches(k, DIGEST_LABEL) and _matches(v, HEX) for k, v in keys.items()))
    return SubjectDigester(value['active_version'], {k: bytes.fromhex(v) for k, v in keys.items()})


def _snapshot(raw):
    value = _json(raw, MAX_SNAPSHOT_BYTES)
    _shape(value, {'schema_version', 'snapshot_id', 'tables'})
    _require(type(value['schema_version']) is int and value['schema_version'] == 1)
    _uuid(value['snapshot_id'])
    _shape(value['tables'], TABLES)
    result, count = {}, 0
    for table in sorted(TABLES):
        rows = value['tables'][table]
        _require(type(rows) is list and len(rows) <= MAX_RECORDS)
        count += len(rows)
        _require(count <= MAX_RECORDS)
        indexed = {}
        for row in rows:
            _shape(row, FIELDS[table])
            record_id = _uuid(row['id'])
            _require(record_id not in indexed)
            indexed[record_id] = row
        result[table] = indexed
    _require(count > 0)
    return value['snapshot_id'], result


def _manifest(raw, snapshot_id, tables):
    value = _json(raw, 256_000)
    _shape(value, {'schema_version', 'snapshot_id', 'active_envelope_version', 'active_digest_version', 'records'})
    _require(type(value['schema_version']) is int and value['schema_version'] == 1
             and value['snapshot_id'] == snapshot_id and _matches(value['active_envelope_version'], LABEL)
             and _matches(value['active_digest_version'], DIGEST_LABEL))
    _shape(value['records'], TABLES)
    total = 0
    for table, rows in tables.items():
        records = value['records'][table]
        _require(type(records) is dict and set(records) == set(rows))
        total += len(records)
        _require(total <= MAX_RECORDS)
        for record_id, row in rows.items():
            expected = records[record_id]
            _require(_matches(expected, HEX))
            _require(hmac.compare_digest(hashlib.sha256(_canonical(row)).hexdigest(), expected))
    return value['active_envelope_version'], value['active_digest_version']


def _ciphertext(value):
    _require(type(value) is str and 1 <= len(value) <= 4 * ((MAX_ENVELOPE_BYTES + 2) // 3))
    data = base64.b64decode(value, validate=True)
    _require(1 <= len(data) <= MAX_ENVELOPE_BYTES and base64.b64encode(data).decode('ascii') == value)
    return data


def _references(row):
    for name in ('flow_id', 'credential_id', 'account_id'):
        _optional_uuid(row[name])
    _require(row['flow_id'] is not None)
    version = row['credential_version']
    _require((row['credential_id'] is None and version is None and row['account_id'] is None and row['page_id'] is None)
             or (row['credential_id'] is not None and type(version) is int and 0 < version < 2**63))
    _require(row['page_id'] is None or _matches(row['page_id'], DECIMAL))


def _inventory(tables):
    """Validate projection and freeze crypto operations to private primitives."""
    envelopes, subjects = [], {}
    credentials, flows, owners, receipts = (tables[t] for t in ('credentials', 'flows', 'ownership', 'receipts'))

    def envelope(row, purpose, version_field, data_field):
        version = row[version_field]
        _require(_matches(version, LABEL))
        envelopes.append((row['id'], purpose, version, _ciphertext(row[data_field])))

    for row in credentials.values():
        kind = row['credential_kind']
        _require(type(kind) is str and kind in ('facebook_user', 'facebook_page'))
        _require(type(row['version']) is int and 0 < row['version'] < 2**63)
        parent = _optional_uuid(row['parent_credential_id'])
        _require((kind == 'facebook_user' and parent is None) or
                 (kind == 'facebook_page' and parent in credentials and credentials[parent]['credential_kind'] == 'facebook_user'))
        envelope(row, kind, 'key_version', 'encrypted_bundle')
    for row in flows.values():
        status = row['status']
        _require(type(status) is str and status in ('initiated', 'exchanging', 'awaiting_selection', 'completed', 'failed', 'expired'))
        _require(_matches(row['key_version'], LABEL))
        verifier, pending = row['encrypted_verifier'], row['encrypted_pending_grant']
        if status == 'initiated':
            _require(verifier is not None and pending is None)
            envelope(row, 'oauth_start', 'key_version', 'encrypted_verifier')
        elif status == 'awaiting_selection':
            _require(verifier is None and pending is not None)
            envelope(row, 'oauth_pending', 'key_version', 'encrypted_pending_grant')
        else:
            _require(verifier is None and pending is None)
    reference_keys = set()
    for row in owners.values():
        _references(row)
        _require(row['flow_id'] in flows)
        if row['credential_id'] is not None:
            _require(row['credential_id'] in credentials)
            # Immutable historical generations can precede the current grant.
            _require(row['credential_version'] <= credentials[row['credential_id']]['version'])
        if row['account_id'] is not None:
            _require(row['account_id'] in tables['accounts'] and tables['accounts'][row['account_id']]['credential_id'] == row['credential_id'])
        expected = ('flow:' + row['flow_id'] if row['credential_id'] is None else
                    'credential:' + row['credential_id'] + ':' + str(row['credential_version'])
                    + (':' + row['account_id'] if row['account_id'] else ''))
        reference = row['reference_key']
        _require(type(reference) is str and reference == expected and reference not in reference_keys)
        reference_keys.add(reference)
        _require(_matches(row['generation_at'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z'))
        datetime.fromisoformat(row['generation_at'].replace('Z', '+00:00'))
    for table in ('ownership', 'receipts'):
        for row in tables[table].values():
            _require(_matches(row['app_id'], DECIMAL) and _matches(row['digest_version'], DIGEST_LABEL) and _matches(row['subject_digest'], HEX))
            subjects[(table, row['id'])] = (row['app_id'], row['digest_version'], row['subject_digest'])
    event_keys, confirmation_hashes = set(), set()
    for row in receipts.values():
        kind = row['kind']
        _require(type(kind) is str and kind in ('data_deletion', 'deauthorization'))
        _require(type(row['state']) is str and row['state'] in ('pending_retention_review', 'blocked_future_mutations', 'ownership_unresolved'))
        _require(_matches(row['event_key'], HEX) and _matches(row['request_fingerprint'], HEX) and _matches(row['resolution'], r'[a-z_]{1,64}'))
        event = (row['app_id'], kind, row['digest_version'], row['event_key'])
        _require(event not in event_keys)
        event_keys.add(event)
        _require(_uuid(row['audit_id']) in tables['audits'])
        affected = row['affected']
        _require(type(affected) is list and len(affected) <= MAX_AFFECTED)
        seen = set()
        for reference in affected:
            _shape(reference, REF_FIELDS)
            owner_id = _uuid(reference['ownership_id'])
            _references(reference)
            _require(owner_id in owners and owner_id not in seen)
            seen.add(owner_id)
            owner = owners[owner_id]
            _require(all(reference[k] == owner[k] for k in REF_FIELDS - {'ownership_id'}))
            _require(owner['app_id'] == row['app_id'])
        if kind == 'data_deletion':
            _require(row['state'] == 'pending_retention_review' and _matches(row['confirmation_hash'], HEX) and row['confirmation_hash'] not in confirmation_hashes)
            confirmation_hashes.add(row['confirmation_hash'])
            envelope(row, 'privacy_confirmation', 'confirmation_key_version', 'encrypted_confirmation')
        else:
            _require(all(row[k] is None for k in ('confirmation_hash', 'confirmation_key_version', 'encrypted_confirmation')))
    variants = set()
    for row in tables['variants'].values():
        receipt_id = _uuid(row['receipt_id'])
        _require(receipt_id in receipts and _matches(row['fingerprint'], HEX))
        receipt = receipts[receipt_id]
        _require(row['app_id'] == receipt['app_id'] and row['kind'] == receipt['kind'])
        identity = (row['app_id'], row['kind'], row['fingerprint'])
        _require(identity not in variants)
        variants.add(identity)
    for row in receipts.values():
        _require(any(v['receipt_id'] == row['id'] and v['fingerprint'] == row['request_fingerprint'] for v in tables['variants'].values()))
    for row in tables['accounts'].values():
        _require(_uuid(row['credential_id']) in credentials)
    _require(envelopes and subjects)
    return tuple(envelopes), subjects


def _subject_proofs(raw, snapshot_id, expected, tables):
    value = _json(raw, 256_000)
    _shape(value, {'schema_version', 'snapshot_id', 'records'})
    _require(type(value['schema_version']) is int and value['schema_version'] == 1 and value['snapshot_id'] == snapshot_id)
    records = value['records']
    _require(type(records) is list and len(records) == len(expected) <= MAX_RECORDS)
    result = {}
    for row in records:
        _shape(row, {'table', 'id', 'subject'})
        _require(type(row['table']) is str and row['table'] in ('ownership', 'receipts'))
        key = (row['table'], _uuid(row['id']))
        _require(key in expected and key not in result and _matches(row['subject'], DECIMAL))
        result[key] = row['subject']
    _require(set(result) == set(expected))
    for receipt in tables['receipts'].values():
        _require(all(result[('ownership', r['ownership_id'])] == result[('receipts', receipt['id'])] for r in receipt['affected']))
    return tuple((*expected[key], result[key]) for key in sorted(result))


def _key_continuity(primary_envelopes, restored_envelopes, candidate_envelopes,
                    primary_digests, restored_digests, candidate_digests):
    # Self-canaries miss corrupt active keys with no stored rows yet. Reconcile
    # every label/material pair, including unreferenced keys, across backups.
    envelope_sets = tuple({k: base64.urlsafe_b64decode(v) for k, v in parse_keyring(raw).keys.items()}
                          for raw in (primary_envelopes, restored_envelopes, candidate_envelopes))
    digest_sets = tuple(dict(_digest_backup(raw).keys)
                       for raw in (primary_digests, restored_digests, candidate_digests))
    for primary, restored, candidate in (envelope_sets, digest_sets):
        _require(set(primary) == set(restored))
        _require(all(hmac.compare_digest(primary[k], restored[k]) for k in primary))
        # A new active label is allowed; relabeling old material is not rotation.
        _require(all(hmac.compare_digest(primary[k], candidate[k]) for k in primary.keys() & candidate.keys()))


def _execute(envelopes, subjects, envelope_raw, digest_raw, tables):
    ring, digester = parse_keyring(envelope_raw), _digest_backup(digest_raw)
    cipher = ring.cipher()
    for owner, purpose, version, ciphertext in envelopes:
        bundle = cipher.decrypt(UUID(owner), purpose, version, ciphertext)
        if purpose == 'privacy_confirmation':
            _shape(bundle, {'code'})
            _require(_matches(bundle['code'], HEX))
            _require(hmac.compare_digest(hashlib.sha256(bundle['code'].encode('ascii')).hexdigest(), tables['receipts'][owner]['confirmation_hash']))
    for app, version, stored, subject in subjects:
        _require(hmac.compare_digest(digester.digest(app, subject, version), stored))
    # This proves fresh deserialization only, never actual store durability.
    restarted_cipher = parse_keyring(envelope_raw).cipher()
    owner = UUID(int=1)
    version, canary = cipher.encrypt(owner, 'recovery_canary', {'inert': 'recovery-continuity-v1'})
    _require(restarted_cipher.decrypt(owner, 'recovery_canary', version, canary) == {'inert': 'recovery-continuity-v1'})
    restarted_digester = _digest_backup(digest_raw)
    _require(hmac.compare_digest(digester.digest('1', '1'), restarted_digester.digest('1', '1')))
    return ring.active_version, digester.active_version


def verify_inventory_continuity(source_snapshot: bytes, restored_snapshot: bytes, independent_manifest: bytes,
                                subject_proofs: bytes, primary_envelopes: bytes, restored_envelopes: bytes,
                                primary_digests: bytes, restored_digests: bytes,
                                candidate_envelopes: bytes, candidate_digests: bytes) -> dict:
    """Reconcile exact row commitments then execute historical and active reads.

    Restore inputs must retain the manifest's active labels. Candidate inputs may
    change active labels but must read every retained envelope/digest. The caller
    must obtain the manifest, subjects and restored keys independently. This seam
    cannot authenticate those origins. It executes no retirement or deletion.
    """
    try:
        inputs = (source_snapshot, restored_snapshot, independent_manifest, subject_proofs,
                  primary_envelopes, restored_envelopes, primary_digests, restored_digests,
                  candidate_envelopes, candidate_digests)
        _require(all(type(value) is bytes for value in inputs))
        snapshot_id, source = _snapshot(source_snapshot)
        restored_id, restored = _snapshot(restored_snapshot)
        _require(restored_id == snapshot_id)
        active = _manifest(independent_manifest, snapshot_id, source)
        _require(_manifest(independent_manifest, snapshot_id, restored) == active)
        envelopes, expected_subjects = _inventory(source)
        subjects = _subject_proofs(subject_proofs, snapshot_id, expected_subjects, source)
        _key_continuity(primary_envelopes, restored_envelopes, candidate_envelopes,
                        primary_digests, restored_digests, candidate_digests)
        _require(_execute(envelopes, subjects, primary_envelopes, primary_digests, source) == active)
        _require(_execute(envelopes, subjects, restored_envelopes, restored_digests, source) == active)
        candidate = _execute(envelopes, subjects, candidate_envelopes, candidate_digests, source)
        return {'status': 'VERIFIED_BY_EXECUTION', 'scope': 'independently_manifested_recovery_projection',
                'records_verified': sum(len(rows) for rows in source.values()),
                'envelopes_verified': len(envelopes), 'subject_records_verified': len(subjects),
                'snapshot_coverage_verified': True, 'database_coverage_verified': False,
                'backup_custody_verified': False, 'production_authorized': False,
                'retirement_authorized': False, 'deletion_authorized': False, 'deletion_completed': False,
                'restart_scope': 'fresh_instances_from_supplied_backup_bytes',
                'candidate_envelope_version': candidate[0], 'candidate_digest_version': candidate[1],
                'missing_prerequisites': MISSING_PREREQUISITES}
    except Exception:
        # Ordinary parser/crypto errors are private; operator interrupts propagate.
        pass
    raise InventoryRecoveryError()

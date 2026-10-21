"""Owned PostgreSQL projection reads reach the shared historical-binding guard.

This is a crypto-bridge test, not full schema/ACL, dump or off-host acceptance.
"""
import base64
from copy import deepcopy
from datetime import datetime
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from social.recovery_database import _verify_crypto, recovery_snapshot_id
from social.recovery_inventory import FIELDS, InventoryRecoveryError
from test_recovery_inventory import historical_account_inventory, inventory

TABLES = {
    'credentials': 'social_credentials', 'flows': 'social_oauth_flows',
    'ownership': 'social_privacy_ownership', 'receipts': 'social_privacy_receipts',
    'variants': 'social_privacy_request_variants', 'accounts': 'social_accounts',
    'audits': 'social_audit_events',
}


@pytest.fixture
def projection_store(historical_account_inventory):
    if os.environ.get('B36_RECOVERY_POSTGRES') != '1':
        pytest.skip('Explicit owned loopback55392 PostgreSQL opt-in required')
    port = os.environ.get('B36_RECOVERY_POSTGRES_PORT', '55392')
    if port not in ('5432', '55392'):
        raise ValueError('Only the owned loopback PostgreSQL ports are supported')
    engine = create_engine('postgresql+psycopg2://postgres@127.0.0.1:' + port + '/postgres',
                           pool_size=1, max_overflow=0,
                           connect_args={'connect_timeout': 3})
    schema = 'b36_recovery_' + uuid4().hex
    snapshot = historical_account_inventory
    manifest = b'inert-crypto-bridge-manifest'
    subjects = deepcopy(snapshot.subjects)
    subjects['snapshot_id'] = recovery_snapshot_id(manifest)
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE SCHEMA ' + schema))
            for logical, physical in TABLES.items():
                fields = sorted(FIELDS[logical])
                def column_type(field):
                    if field == 'affected': return 'jsonb'
                    if field.startswith('encrypted_'): return 'bytea'
                    if field == 'generation_at': return 'timestamptz'
                    if field in ('version', 'credential_version'): return 'bigint'
                    if field == 'id' or field.endswith('_id') and field not in ('app_id', 'page_id'):
                        return 'uuid'
                    return 'text'
                columns = ','.join('"' + f + '" ' + column_type(f) for f in fields)
                conn.execute(text('CREATE TABLE ' + schema + '.' + physical + '(' + columns + ')'))
                values = ','.join('CAST(:' + f + ' AS jsonb)' if f == 'affected' else ':' + f for f in fields)
                statement = text('INSERT INTO ' + schema + '.' + physical + ' (' + ','.join('"' + f + '"' for f in fields) + ') VALUES (' + values + ')')
                for row in snapshot.source['tables'][logical]:
                    data = dict(row)
                    for field in fields:
                        if data[field] is not None and field.startswith('encrypted_'):
                            data[field] = base64.b64decode(data[field], validate=True)
                        elif field == 'affected':
                            data[field] = json.dumps(data[field])
                        elif field == 'generation_at':
                            data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                    conn.execute(statement, data)
        yield engine, schema, manifest, json.dumps(subjects).encode(), snapshot
    finally:
        try:
            with engine.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
        finally:
            engine.dispose()


def verify_store(store):
    engine, schema, manifest, subjects, snapshot = store
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        conn.execute(text("SET LOCAL statement_timeout='3s'"))
        conn.execute(text("SET LOCAL timezone='UTC'"))
        return _verify_crypto(conn, schema, manifest, snapshot.envelopes,
                              snapshot.digests, subjects)


@pytest.mark.parametrize('detached', [False, True])
def test_pg_crypto_bridge_reads_historical_binding_after_reconnect(projection_store, detached):
    if detached:
        engine, schema, *_ = projection_store
        with engine.begin() as conn:
            conn.execute(text('UPDATE ' + schema + '.social_accounts SET credential_id=NULL'))
    result = verify_store(projection_store)
    assert result == {'envelopes_verified': 6, 'subject_records_verified': 2,
                      'active_envelope_version': 'current', 'active_digest_version': 'current'}


@pytest.mark.parametrize('damage', ['frozen_binding', 'subject_digest', 'missing_account'])
def test_pg_crypto_bridge_refuses_corrupt_historical_binding(projection_store, damage):
    engine, schema, *_ = projection_store
    statements = {
        'frozen_binding': "UPDATE {s}.social_privacy_receipts SET affected=jsonb_set(affected,'{{0,credential_version}}','1')",
        'subject_digest': "UPDATE {s}.social_privacy_ownership SET subject_digest=repeat('0',64)",
        'missing_account': 'DELETE FROM {s}.social_accounts',
    }
    with engine.begin() as conn:
        conn.execute(text(statements[damage].format(s=schema)))
    with pytest.raises(InventoryRecoveryError):
        verify_store(projection_store)

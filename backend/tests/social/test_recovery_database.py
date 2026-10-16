"""Owned real PostgreSQL complete-schema witness and loss-of-primary restore drill."""
import hashlib
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from social.recovery_database import capture_database, verify_database_restore, DatabaseRecoveryError

DSN = 'postgresql+psycopg2://postgres@127.0.0.1:55392/'
CONTAINER = 'b15-recovery-privacy-pg'

@pytest.fixture
def stores(tmp_path):
    if os.getenv('B15_RECOVERY_POSTGRES') != '1':
        pytest.skip('Explicit owned local PostgreSQL opt-in required')
    suffix = uuid4().hex
    source_name, restore_name = 'b15_source_' + suffix, 'b15_restore_' + suffix
    admin = create_engine(DSN+'postgres', isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE '+source_name))
        conn.execute(text('CREATE DATABASE '+restore_name))
    source, restored = create_engine(DSN+source_name), create_engine(DSN+restore_name)
    try:
        with source.begin() as conn:
            conn.execute(text('CREATE TABLE crypto_inventory(id int primary key, bundle bytea, state jsonb)'))
            conn.exec_driver_sql("INSERT INTO crypto_inventory VALUES (1, decode('abcd','hex'), '{\"pending_flow\":true}'),(2,decode('00','hex'), '{\"ownership\":\"retained\"}')")
            conn.execute(text('CREATE TABLE empty_inventory(id int primary key)'))
        backup = subprocess.run(['docker','exec',CONTAINER,'pg_dump','-U','postgres','-Fc',source_name], check=True, capture_output=True).stdout
        subprocess.run(['docker','exec','-i',CONTAINER,'pg_restore','-U','postgres','-d',restore_name], input=backup, check=True, capture_output=True)
        key = Ed25519PrivateKey.from_private_bytes(b'w'*32)
        pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        digest = hashlib.sha256(backup).hexdigest()
        manifest = capture_database(source, schema='public', signing_key=b'w'*32, backup_sha256=digest)
        yield source, restored, manifest, pub, digest, admin, source_name
    finally:
        source.dispose(); restored.dispose()
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE IF EXISTS '+source_name+' WITH (FORCE)'))
            conn.execute(text('DROP DATABASE IF EXISTS '+restore_name+' WITH (FORCE)'))
        admin.dispose()


def test_actual_dump_restore_without_primary_and_signed_complete_inventory(stores):
    source, restored, packet, key, digest, admin, source_name = stores
    source.dispose()
    with admin.connect() as conn:
        conn.execute(text('DROP DATABASE '+source_name+' WITH (FORCE)'))
    result = verify_database_restore(restored, packet, schema='public', public_key=key, backup_sha256=digest)
    assert result['database_coverage_verified'] is True
    assert result['records_verified'] == 2 and result['tables_verified'] == 2
    assert result['source_database_required'] is False
    assert result['off_host_verified'] is False and result['retirement_authorized'] is False

@pytest.mark.parametrize('mutation', ['DELETE FROM crypto_inventory WHERE id=2', 'DROP TABLE empty_inventory', 'ALTER TABLE crypto_inventory ADD COLUMN ignored text', "UPDATE crypto_inventory SET state='{}'"])
def test_missing_rows_empty_tables_schema_and_crypto_mutations_refused(stores, mutation):
    _, restored, packet, key, digest, *_ = stores
    with restored.begin() as conn:
        conn.execute(text(mutation))
    with pytest.raises(DatabaseRecoveryError):
        verify_database_restore(restored, packet, schema='public', public_key=key, backup_sha256=digest)

def test_wrong_witness_dump_and_same_store_refused(stores):
    source, restored, packet, key, digest, *_ = stores
    for engine, witness, backup in [(source,key,digest),(restored,b'x'*32,digest),(restored,key,'0'*64)]:
        with pytest.raises(DatabaseRecoveryError):
            verify_database_restore(engine, packet, schema='public', public_key=witness, backup_sha256=backup)

@pytest.mark.parametrize('value', [None, b'', b'{}', b'[]', True, b'NaN'])
def test_malformed_restore_packet_is_private(stores, value):
    _, restored, _, key, digest, *_ = stores
    with pytest.raises(DatabaseRecoveryError) as error:
        verify_database_restore(restored, value, schema='public', public_key=key, backup_sha256=digest)
    assert str(error.value) == 'DATABASE_RECOVERY_REFUSED'


def test_zero_column_relation_cannot_disappear_from_complete_inventory(stores):
    source, restored, _, key, digest, *_ = stores
    with source.begin() as conn:
        conn.execute(text('CREATE TABLE zero_columns()'))
        conn.execute(text('INSERT INTO zero_columns DEFAULT VALUES'))
    packet = capture_database(source,schema='public',signing_key=b'w'*32,backup_sha256=digest)
    with pytest.raises(DatabaseRecoveryError):
        verify_database_restore(restored,packet,schema='public',public_key=key,backup_sha256=digest)


def test_cross_schema_partition_rows_are_inventoried(stores):
    source, restored, _, key, digest, *_ = stores
    for engine in (source,restored):
        with engine.begin() as conn:
            conn.execute(text('CREATE SCHEMA other'))
            conn.execute(text('CREATE TABLE other.root(id int) PARTITION BY RANGE(id)'))
            conn.execute(text('CREATE TABLE public.leaf PARTITION OF other.root FOR VALUES FROM (0) TO (100)'))
    with source.begin() as conn:
        conn.execute(text('INSERT INTO public.leaf VALUES(7)'))
    packet = capture_database(source,schema='public',signing_key=b'w'*32,backup_sha256=digest)
    with pytest.raises(DatabaseRecoveryError):
        verify_database_restore(restored,packet,schema='public',public_key=key,backup_sha256=digest)


def test_runtime_export_binds_actual_dump_to_exported_snapshot(stores,tmp_path):
    from pathlib import Path
    from social.recovery_database import export_database_backup
    source,restored,_,key,_,*_=stores
    backup=tmp_path/'real-backup.dump'
    manifest=export_database_backup(source,schema='public',destination=backup,signing_key=b'w'*32,pg_dump=Path('/opt/homebrew/bin/pg_dump'))
    digest=hashlib.sha256(backup.read_bytes()).hexdigest()
    assert backup.stat().st_mode & 0o077==0
    result=verify_database_restore(restored,manifest,schema='public',public_key=key,backup_sha256=digest)
    assert result['records_verified']==2
    with pytest.raises(DatabaseRecoveryError):
        export_database_backup(source,schema='public',destination=backup,signing_key=b'w'*32,pg_dump=Path('/opt/homebrew/bin/pg_dump'))


@pytest.mark.parametrize('identity',[None,[],{},'source',True,[None]*4])
def test_signed_but_malformed_identity_cannot_bypass_same_store_guard(stores,identity):
    import json
    from social.privacy.deletion_ledger import canonical
    source,_,packet,key,digest,*_=stores
    value=json.loads(packet)
    value['payload']['source_identity']=identity
    value['signature']=Ed25519PrivateKey.from_private_bytes(b'w'*32).sign(canonical(value['payload'])).hex()
    with pytest.raises(DatabaseRecoveryError):
        verify_database_restore(source,canonical(value),schema='public',public_key=key,backup_sha256=digest)


def test_address_alias_cannot_turn_source_into_a_restore(stores):
    import json
    from social.privacy.deletion_ledger import canonical
    source,_,packet,key,digest,*_=stores
    value=json.loads(packet)
    address=value['payload']['source_identity'][2]
    value['payload']['source_identity'][2]=address.split('/')[0] if '/' in address else address+'/32'
    value['signature']=Ed25519PrivateKey.from_private_bytes(b'w'*32).sign(canonical(value['payload'])).hex()
    with pytest.raises(DatabaseRecoveryError):
        verify_database_restore(source,canonical(value),schema='public',public_key=key,backup_sha256=digest)

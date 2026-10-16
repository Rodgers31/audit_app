"""Execute the privacy workflow through the complete reserved Alembic chain."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from test_privacy_workflow import (setup, config, graph,
    test_independent_approval_execution_restart_and_no_false_request_completion,
    test_failed_custody_keeps_credentials_and_requires_reconciliation,
    test_failed_db_completion_reconciles_external_intent_without_repeat,
    test_approval_scope_change_and_foreign_credential_are_blocked,
    test_erasure_intent_reapplies_to_predelete_database_and_refuses_newer_generation)

@pytest.fixture
def db():
    if os.getenv('B15_RECOVERY_POSTGRES') != '1':
        pytest.skip('Explicit owned local PostgreSQL required')
    name = 'b15_privacy_' + uuid4().hex
    admin = create_engine('postgresql+psycopg2://postgres@127.0.0.1:55392/postgres', isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE '+name))
    engine = create_engine('postgresql+psycopg2://postgres@127.0.0.1:55392/'+name)
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / 'alembic'))
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            for revision in reversed(list(scripts.walk_revisions(base='base', head='a700b15a0001'))):
                revision.module.upgrade()
        with Session(engine, expire_on_commit=False) as db:
            yield db
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE IF EXISTS '+name+' WITH (FORCE)'))
        admin.dispose()


def test_rls_immutable_authority_and_no_browser_or_delivery_worker_grant(db, setup):
    from test_privacy_workflow import approve
    svc, command, ledger = setup
    approve(svc, command)
    for table in ('social_privacy_plans','social_privacy_decisions','social_privacy_executions','social_privacy_execution_events'):
        with db.begin():
            assert db.execute(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'), {'name':table}).scalar() is True
            assert db.execute(text("SELECT has_table_privilege('public',CAST(:name AS regclass),'SELECT')"), {'name':table}).scalar() is False
    from sqlalchemy.exc import DBAPIError
    for statement in ('DELETE FROM social_privacy_plans', "UPDATE social_privacy_decisions SET reason='rewrite'"):
        with pytest.raises(DBAPIError), db.begin():
            db.execute(text(statement))


def test_trigger_retaining_old_ciphertext_cannot_certify_erasure(db, setup):
    from test_privacy_workflow import approve, APPROVER
    from uuid import UUID
    from social.service import SocialError
    svc, command, ledger = setup
    plan = approve(svc, command)
    with db.begin():
        db.execute(text("""CREATE FUNCTION b15_retain_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.encrypted_bundle=OLD.encrypted_bundle; RETURN NEW; END $$"""))
        db.execute(text('CREATE TRIGGER b15_retain_envelope BEFORE UPDATE ON social_credentials FOR EACH ROW EXECUTE FUNCTION b15_retain_envelope()'))
    with pytest.raises(SocialError):
        svc.execute(APPROVER, UUID(plan['id']), 1)
    assert svc.get(UUID(plan['id']))['execution']['state'] != 'completed'


def test_rotation_cannot_certify_trigger_preserved_envelopes(db, config, graph):
    from cryptography.fernet import Fernet
    from social.connections.rotation import rotate_retained_envelopes
    from social.connections.crypto import CredentialCipher
    from test_privacy_support import connected
    from social.service import SocialError
    connected(db,config,graph)
    old=CredentialCipher(config.active_key_version,config.encryption_keys)
    candidate=CredentialCipher('next',dict(config.encryption_keys,next=Fernet.generate_key().decode()))
    with db.begin():
        db.execute(text('CREATE FUNCTION b15_retain_rotation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.key_version=OLD.key_version; NEW.encrypted_bundle=OLD.encrypted_bundle; RETURN NEW; END $$'))
        db.execute(text('CREATE TRIGGER b15_retain_rotation BEFORE UPDATE ON social_credentials FOR EACH ROW EXECUTE FUNCTION b15_retain_rotation()'))
    with pytest.raises(SocialError):
        rotate_retained_envelopes(db,old_cipher=old,candidate_cipher=candidate)


def test_stale_session_cannot_erase_a_newer_credential_generation(db, setup):
    from social.connections.models import SocialCredential
    from test_privacy_workflow import approve, APPROVER
    from social.service import SocialError
    from uuid import UUID
    svc, command, _ = setup
    plan=approve(svc,command)
    with db.begin():
        retained=list(db.scalars(select(SocialCredential)))
        before={r.id:r.version for r in retained}
    with Session(db.bind) as writer, writer.begin():
        for row in writer.scalars(select(SocialCredential)):
            row.version+=10
    with pytest.raises(SocialError):
        svc.execute(APPROVER,UUID(plan['id']),1)
    with Session(db.bind) as fresh:
        assert {r.id:r.version for r in fresh.scalars(select(SocialCredential))}=={i:v+10 for i,v in before.items()}


def test_actual_off_primary_dump_restore_reapplies_external_ledger(db,setup,tmp_path,config):
    import hashlib
    import subprocess
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from social.recovery_database import export_database_backup,verify_database_restore,recovery_snapshot_id
    from social.privacy.restoration import reapply_deletion_ledger
    from social.connections.models import SocialCredential
    from social.connections.crypto import CredentialCipher
    from test_privacy_workflow import approve,APPROVER
    from uuid import UUID
    svc,command,ledger=setup
    plan=approve(svc,command)
    from social.connections.recovery import RecoveryKeyring,write_keyring_backup,read_keyring_backup
    key_backup=tmp_path/'independent-keyring.json'
    write_keyring_backup(key_backup,RecoveryKeyring(config.active_key_version,dict(config.encryption_keys)))
    backup=tmp_path/'before-deletion.dump'
    import json
    envelope_backup=key_backup.read_bytes()
    digest_backup=json.dumps({'schema_version':1,'purpose':'meta_subject_digests','active_version':'d1','keys':{'d1':(b'x'*32).hex()}}).encode()
    packet=export_database_backup(db.bind,schema='public',destination=backup,signing_key=b'w'*32,pg_dump=Path('/opt/homebrew/bin/pg_dump'),keyring_backup=envelope_backup,digest_backup=digest_backup)
    from social.privacy.models import SocialPrivacyOwnership,SocialPrivacyReceipt
    with db.begin():
        proof_records=[{'table':table,'id':str(row.id),'subject':'701'} for table,model in [('ownership',SocialPrivacyOwnership),('receipts',SocialPrivacyReceipt)] for row in db.scalars(select(model))]
    proofs=json.dumps({'schema_version':1,'snapshot_id':recovery_snapshot_id(packet),'records':proof_records}).encode()
    witness=Ed25519PrivateKey.from_private_bytes(b'w'*32).public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    result=svc.execute(APPROVER,UUID(plan['id']),1)
    entry=(ledger.directory/(result['execution']['id']+'.json')).read_bytes()
    restored_name='b15_reapply_'+uuid4().hex
    admin=create_engine('postgresql+psycopg2://postgres@127.0.0.1:55392/postgres',isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:conn.execute(text('CREATE DATABASE '+restored_name))
    restored=create_engine('postgresql+psycopg2://postgres@127.0.0.1:55392/'+restored_name)
    try:
        with restored.begin() as conn:conn.execute(text('DROP SCHEMA public'))
        restored_process=subprocess.run(['/opt/homebrew/bin/pg_restore','--no-owner','--no-privileges','--dbname',restored.url.set(drivername='postgresql').render_as_string(hide_password=False),str(backup)],check=False,capture_output=True)
        assert restored_process.returncode == 0, restored_process.stderr.decode()[:6000]
        source_name=db.bind.url.database
        db.close();db.bind.dispose()
        with admin.connect() as conn:conn.execute(text('DROP DATABASE '+source_name+' WITH (FORCE)'))
        recovered_cipher=read_keyring_backup(key_backup).cipher()
        from social.recovery_database import _setup,_inventory
        import json
        with restored.connect().execution_options(isolation_level='REPEATABLE READ') as check,check.begin():
            _setup(check,'public')
            actual=_inventory(check,'public')
        expected=json.loads(packet)['payload']['inventory']
        def differences(left,right,path=''):
            if type(left) is dict and type(right) is dict:
                return [item for key in set(left)|set(right) for item in differences(left.get(key),right.get(key),path+'/'+key)]
            if left!=right:return [(path,str(left)[:6000],str(right)[:6000])]
            return []
        if actual!=expected:print('INVENTORY_DIFFERENCES='+json.dumps(differences(actual,expected)[:10]))
        assert actual==expected,differences(actual,expected)[:10]
        report=verify_database_restore(restored,packet,schema='public',public_key=witness,backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),keyring_backup=envelope_backup,digest_backup=digest_backup,subject_proofs=proofs)
        assert report['database_coverage_verified'] is True and report['cryptographic_continuity_verified'] is True
        with Session(restored) as restored_db:
            # Reconstruct key material from the separately preserved synthetic ring.
            replay=reapply_deletion_ledger(restored_db,[entry],public_key=ledger.public_key,cipher=recovered_cipher,apply=True)
            assert replay['state']=='LOCAL_SUPPRESSION_REAPPLIED' and replay['publishing_authorized'] is False
            with restored_db.begin():
                for row in restored_db.scalars(select(SocialCredential)):
                    assert recovered_cipher.decrypt(row.id,row.credential_kind,row.key_version,row.encrypted_bundle)['privacy_erased'] is True
    finally:
        restored.dispose()
        with admin.connect() as conn:conn.execute(text('DROP DATABASE '+restored_name+' WITH (FORCE)'))
        admin.dispose()

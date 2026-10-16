"""Real ORM transactions, frozen receipts and external durable ledger failure paths."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from social.connections.crypto import CredentialCipher
from social.connections.models import SocialCredential
from social.privacy.workflow import PrivacyWorkflow
from social.privacy.workflow_contracts import PrivacyProposal, PrivacyApproval, PrivacyWorkflowConfig
from social.privacy.workflow_models import PrivacyExecution
from social.privacy.models import SocialPrivacyReceipt, SocialPrivacyOwnership
from social.privacy.deletion_ledger import FileDeletionLedger, verify_entry
from social.models import SocialAccount
from social.service import SocialError
from test_privacy_support import config, db, graph, connected, privacy, signed, ACTOR

APPROVER = UUID(int=1234)
POLICY = ('fixture-policy', 'a' * 64)

@pytest.fixture
def setup(db, config, graph, tmp_path):
    connected(db, config, graph)
    privacy(db, config).receive(signed(config), kind='data_deletion')
    with db.begin():
        receipt = db.scalar(select(SocialPrivacyReceipt))
        identities = [c.id for c in db.scalars(select(SocialCredential))]
        receipt_id = receipt.id
    ledger_dir = tmp_path / 'custody'
    ledger_dir.mkdir(mode=0o700)
    ledger = FileDeletionLedger(ledger_dir, b'k' * 32)
    cfg = PrivacyWorkflowConfig(True, True, (POLICY,), (APPROVER, ACTOR))
    cipher = CredentialCipher(config.active_key_version, config.encryption_keys)
    svc = PrivacyWorkflow(db, cfg, cipher=cipher, ledger=ledger)
    command = PrivacyProposal(receipt_id=receipt_id, policy_key=POLICY[0], policy_hash=POLICY[1],
        evidence='Synthetic operator reviewed ownership and policy evidence.', erase_credentials=identities)
    return svc, command, ledger


def approve(svc, command):
    plan = svc.propose(ACTOR, uuid4(), command)
    return svc.decide(APPROVER, UUID(plan['id']), PrivacyApproval(plan_hash=plan['plan_hash'], decision='approved', reason='Independent synthetic policy and scope review.'))


def test_no_default_authority_or_self_approval(setup, db):
    svc, command, ledger = setup
    with pytest.raises(SocialError, match='PRIVACY_WORKFLOW_DISABLED'):
        PrivacyWorkflow(db, PrivacyWorkflowConfig()).propose(ACTOR, uuid4(), command)
    plan = svc.propose(ACTOR, uuid4(), command)
    with pytest.raises(SocialError) as e:
        svc.decide(ACTOR, UUID(plan['id']), PrivacyApproval(plan_hash=plan['plan_hash'], decision='approved', reason='Self approval must fail closed.'))
    assert e.value.code == 'PRIVACY_INDEPENDENT_APPROVAL_REQUIRED'
    assert not list(ledger.directory.iterdir())


def test_independent_approval_execution_restart_and_no_false_request_completion(setup, db):
    svc, command, ledger = setup
    plan = approve(svc, command)
    result = svc.execute(APPROVER, UUID(plan['id']), 1)
    assert result['execution']['state'] == 'completed'
    assert result['execution']['result']['request_completed'] is False
    with db.begin():
        assert len(db.scalars(select(SocialPrivacyReceipt)).all()) == 1
        assert len(db.scalars(select(SocialPrivacyOwnership)).all()) > 0
        for row in db.scalars(select(SocialCredential)):
            assert svc.cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle) == {'privacy_erased': True, 'authority_id': plan['id']}
            assert row.revoked_at
        assert all(not a.publishing_enabled for a in db.scalars(select(SocialAccount)))
    with Session(db.bind) as restarted:
        again = PrivacyWorkflow(restarted, svc.config, cipher=svc.cipher, ledger=FileDeletionLedger(ledger.directory, b'k'*32))
        assert again.get(UUID(plan['id']))['execution']['state'] == 'completed'
    entry = next(ledger.directory.iterdir()).read_bytes()
    assert verify_entry(entry, ledger.public_key)['plan_id'] == plan['id']
    with pytest.raises(ValueError):
        verify_entry(entry, b'z'*32)


def test_failed_custody_keeps_credentials_and_requires_reconciliation(setup, db, monkeypatch):
    svc, command, ledger = setup
    plan = approve(svc, command)
    with db.begin():
        before = {c.id: bytes(c.encrypted_bundle) for c in db.scalars(select(SocialCredential))}
    def fail(*args):
        raise OSError('owned fixture disk full')
    monkeypatch.setattr(ledger, 'persist', fail)
    with pytest.raises(SocialError) as caught:
        svc.execute(APPROVER, UUID(plan['id']), 1)
    assert caught.value.code == 'PRIVACY_RECONCILIATION_REQUIRED'
    with db.begin():
        assert {c.id: bytes(c.encrypted_bundle) for c in db.scalars(select(SocialCredential))} == before
        assert db.scalar(select(PrivacyExecution)).state == 'outcome_unknown'
    with pytest.raises(SocialError):
        svc.execute(APPROVER, UUID(plan['id']), 3)


def test_failed_db_completion_reconciles_external_intent_without_repeat(setup, db):
    svc, command, ledger = setup
    plan = approve(svc, command)
    failed = False
    def fail(session, context, instances):
        nonlocal failed
        if not failed and any(isinstance(r, PrivacyExecution) and r.state == 'completed' for r in session.dirty):
            failed = True
            raise OSError('synthetic completion write failed')
    event.listen(db, 'before_flush', fail)
    try:
        with pytest.raises(SocialError):
            svc.execute(APPROVER, UUID(plan['id']), 1)
    finally:
        event.remove(db, 'before_flush', fail)
    result = svc.get(UUID(plan['id']))
    assert result['execution']['state'] == 'outcome_unknown'
    result = svc.reconcile(APPROVER, UUID(plan['id']), result['execution']['version'])
    assert result['execution']['state'] == 'completed'
    assert len(list(ledger.directory.iterdir())) == 1


def test_approval_scope_change_and_foreign_credential_are_blocked(setup):
    svc, command, _ = setup
    with pytest.raises(SocialError):
        svc.propose(ACTOR, uuid4(), command.model_copy(update={'erase_credentials': (uuid4(),)}))
    bad = command.model_copy(update={'policy_hash': 'b'*64})
    with pytest.raises(SocialError):
        svc.propose(ACTOR, uuid4(), bad)
    plan = approve(svc, command)
    with pytest.raises(SocialError):
        svc.execute(APPROVER, UUID(plan['id']), True)


def test_erasure_intent_reapplies_to_predelete_database_and_refuses_newer_generation(setup, db):
    svc, command, ledger = setup
    plan = approve(svc, command)
    with db.begin():
        before = {r.id: (r.version, r.key_version, bytes(r.encrypted_bundle)) for r in db.scalars(select(SocialCredential))}
    result = svc.execute(APPROVER, UUID(plan['id']), 1)
    intent = ledger.read(UUID(result['execution']['id']))
    with db.begin():
        for row in db.scalars(select(SocialCredential)):
            row.version, row.key_version, row.encrypted_bundle = before[row.id]
    with db.begin():
        svc.apply_intent(intent)
    with db.begin():
        for row in db.scalars(select(SocialCredential)):
            assert svc.cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle)['privacy_erased'] is True
            row.version, row.key_version, row.encrypted_bundle = before[row.id]
            row.version += 100
    with pytest.raises(SocialError), db.begin():
        svc.apply_intent(intent)


def test_pending_flow_rotation_and_older_backup_reapply_keep_identity_bound(setup,db,config,graph):
    from datetime import datetime,timezone
    from test_privacy_support import connection,start,complete,signed,privacy
    from social.connections.models import SocialOAuthFlow
    from social.privacy.workflow import flow_hash
    from cryptography.fernet import Fernet
    svc,_,ledger=setup
    conn=connection(db,config,graph)
    flow,state=start(conn)
    complete(conn,state)
    identity=UUID(flow['flow_id'])
    issued=int(datetime.now(timezone.utc).timestamp())+10
    privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':issued}),kind='data_deletion')
    with db.begin():
        receipt=db.scalar(select(SocialPrivacyReceipt).where(SocialPrivacyReceipt.issued_at==issued))
        row=db.get(SocialOAuthFlow,identity)
        old=(row.key_version,bytes(row.encrypted_pending_grant))
        # A legitimate rotation changes ciphertext, not the immutable flow identity.
        version,encrypted=svc.cipher.encrypt(row.id,'oauth_pending',svc.cipher.decrypt(row.id,'oauth_pending',row.key_version,row.encrypted_pending_grant))
        row.key_version,row.encrypted_pending_grant=version,encrypted
        receipt_id=receipt.id
    command=PrivacyProposal(receipt_id=receipt_id,policy_key=POLICY[0],policy_hash=POLICY[1],evidence='Synthetic pending flow and immutable identity reviewed.',erase_flows=(identity,))
    plan=approve(svc,command)
    result=svc.execute(APPROVER,UUID(plan['id']),1)
    intent=ledger.read(UUID(result['execution']['id']))
    with db.begin():
        row=db.get(SocialOAuthFlow,identity)
        assert row.encrypted_pending_grant is None and row.status=='failed'
        row.status,row.encrypted_pending_grant,row.key_version='awaiting_selection',old[1],old[0]
    with db.begin():svc.apply_intent(intent)
    with db.begin():
        row=db.get(SocialOAuthFlow,identity)
        assert row.encrypted_pending_grant is None and row.status=='failed'

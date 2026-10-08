from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from social.models import SocialAccount, SocialAuditEvent
from social.connections.models import SocialCredential, SocialOAuthFlow
from social.privacy.models import SocialPrivacyOwnership, SocialPrivacyReceipt, SocialPrivacyRequestVariant
from social.privacy.subjects import SubjectKeyError, SubjectDigester
from social.service import SocialError
from test_privacy_support import *


def test_provider_inspected_index_and_pending_flow_survive_restart(db, config, graph):
    _, flow_id, _ = connected(db, config, graph)
    owners = list(db.scalars(select(SocialPrivacyOwnership)))
    assert len(owners) == 4
    assert all(o.app_id == config.app_id and o.flow_id == flow_id for o in owners)
    assert len({o.credential_id for o in owners if o.credential_id}) == 2
    assert len({o.account_id for o in owners if o.account_id}) == 2
    assert all(o.credential_version == 1 for o in owners if o.credential_id)
    assert all(o.subject_digest == digester().digest(config.app_id, '701') for o in owners)
    assert {'debug_token', 'me'} <= {r.url.path.split('/')[-1] for r in graph.calls}
    db.rollback()
    with Session(db.bind) as restarted:
        assert restarted.scalar(select(func.count()).select_from(SocialPrivacyOwnership)) == 4


def test_receipt_exact_variant_and_restart_freeze_refs(db, config, graph):
    connected(db, config, graph)
    svc = privacy(db, config)
    result = svc.receive(signed(config), kind='data_deletion')
    assert svc.receive(signed(config), kind='data_deletion') == result
    assert svc.receive(signed(config, raw='{ "user_id":"701", "app_id":"123", "algorithm":"HMAC-SHA256" }', padded=True), kind='data_deletion') == result
    assert svc.status(result['confirmation_code'])['deletion_completed'] is False
    with Session(db.bind) as restarted:
        assert privacy(restarted, config).receive(signed(config), kind='data_deletion') == result
        rows = list(restarted.scalars(select(SocialPrivacyReceipt)))
        assert len(rows) == 1 and len(rows[0].affected) == 4
        assert rows[0].received_at is not None and rows[0].state == 'pending_retention_review'
        assert rows[0].confirmation_hash != result['confirmation_code']
        assert restarted.get(SocialAuditEvent, rows[0].audit_id).details['affected_count'] == 4
        assert restarted.scalar(select(func.count()).select_from(SocialPrivacyRequestVariant)) == 2


def test_deauthorization_preserves_active_lease(db, config, graph):
    _, _, selected = connected(db, config, graph)
    token = uuid4()
    account = db.get(SocialAccount, UUID(selected['accounts'][0]['id']))
    account.publish_lease_token = token
    account.publish_lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    db.commit()
    out = privacy(db, config).receive(signed(config), kind='deauthorization')
    assert out['state'] == 'blocked_future_mutations'
    account = db.get(SocialAccount, UUID(selected['accounts'][0]['id']))
    assert account.publish_lease_token == token and account.connection_state == 'revoked'
    assert account.publishing_enabled is False
    assert all(c.revoked_at is not None for c in db.scalars(select(SocialCredential)))


def test_reconnect_replay_never_revokes_new_generation(db, config, graph):
    svc, _, selected = connected(db, config, graph)
    first = privacy(db, config).receive(signed(config), kind='deauthorization')
    flow, state = start(svc, reconnect=UUID(selected['accounts'][0]['id']))
    complete(svc, state)
    select_asset(svc, UUID(flow['flow_id']))
    assert privacy(db, config).receive(signed(config), kind='deauthorization') == first
    assert privacy(db, config).receive(signed(config, padded=True), kind='deauthorization') == first
    assert all(a.connection_state == 'connected' for a in db.scalars(select(SocialAccount)))
    assert len(list(db.scalars(select(SocialPrivacyOwnership)))) == 8
    active = {a.credential_id for a in db.scalars(select(SocialAccount))}
    assert all(db.get(SocialCredential, cid).revoked_at is None for cid in active)


@pytest.mark.parametrize('subject', ['702', '999'])
def test_unknown_subject_does_not_claim_no_data_or_scan_grants(db, config, graph, subject):
    connected(db, config, graph)
    queries = []
    def capture(conn, cursor, statement, params, context, many):
        queries.append(statement)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        out = privacy(db, config).receive(signed(config, subject), kind='deauthorization')
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert out['state'] == 'ownership_unresolved' and out['resolution'] == 'unknown_or_legacy'
    assert not any('encrypted_bundle' in q for q in queries)
    assert all(a.connection_state == 'connected' for a in db.scalars(select(SocialAccount)))


def test_legacy_provider_does_not_become_indexed_by_declaration(db, config, graph):
    from test_connections_support import svc
    old = svc(db, config, graph)
    flow, state = start(old)
    complete(old, state)
    select_asset(old, UUID(flow['flow_id']))
    result = privacy(db, config).receive(signed(config), kind='deauthorization')
    assert result['resolution'] == 'unknown_or_legacy'
    assert list(db.scalars(select(SocialPrivacyOwnership))) == []
    assert all(a.connection_state == 'connected' for a in db.scalars(select(SocialAccount)))


@pytest.mark.parametrize('raw', ['null', '[]', '{}', '{"algorithm":"HMAC-SHA256","user_id":"701","user_id":"701"}', '{"algorithm":"HMAC-SHA256","user_id":true}', '{"algorithm":"HMAC-SHA256","user_id":"701","unknown":1}', '{"algorithm":"HMAC-SHA256","user_id":"701","issued_at":true}', '{"algorithm":"HMAC-SHA256","user_id":"701","app_id":"456"}', '{"algorithm":"HMAC-SHA256","user_id":"701","expires":null}'])
def test_mac_valid_malformed_input_never_inserts(db, config, raw):
    with pytest.raises(SocialError) as caught:
        privacy(db, config).receive(signed(config, raw=raw), kind='data_deletion')
    assert caught.value.code == 'PRIVACY_REQUEST_INVALID' and raw not in str(caught.value)
    assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 0


def test_unknown_key_and_rotation_replay(db, config, graph):
    connected(db, config, graph)
    first = privacy(db, config).receive(signed(config), kind='data_deletion')
    rotated = digester('d2', {'d1': b'x' * 32, 'd2': b'y' * 32})
    assert privacy(db, config, rotated).receive(signed(config, padded=True), kind='data_deletion') == first
    missing = digester('d2', {'d2': b'y' * 32})
    result = privacy(db, config, missing).receive(signed(config, payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':1}), kind='deauthorization')
    assert result['resolution'] == 'digest_key_unavailable' and result['state'] == 'ownership_unresolved'


def test_pending_flow_blocked_without_purging_grant(db, config, graph):
    svc = connection(db, config, graph)
    flow, state = start(svc)
    complete(svc, state)
    privacy(db, config).receive(signed(config), kind='deauthorization')
    with pytest.raises(SocialError) as caught:
        select_asset(svc, UUID(flow['flow_id']))
    assert caught.value.code == 'PRIVACY_FLOW_BLOCKED'
    assert db.get(SocialOAuthFlow, UUID(flow['flow_id'])).encrypted_pending_grant is not None


def test_failed_commit_no_ack_or_partial_revocation_restart_retries(db, config, graph):
    connected(db, config, graph)
    def fail(session):
        raise RuntimeError('simulated persist failure')
    event.listen(db, 'before_commit', fail)
    try:
        with pytest.raises(RuntimeError):
            privacy(db, config).receive(signed(config), kind='deauthorization')
    finally:
        event.remove(db, 'before_commit', fail)
    with Session(db.bind) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 0
        assert all(a.connection_state == 'connected' for a in fresh.scalars(select(SocialAccount)))
        fresh.rollback()
        assert privacy(fresh, config).receive(signed(config), kind='deauthorization')['state'] == 'blocked_future_mutations'


@pytest.mark.parametrize('value', [None, '', True, {}, 'v' * 33])
def test_key_versions_explicit_strict(value):
    with pytest.raises(SubjectKeyError):
        SubjectDigester(value, {'d1': b'x'*32})


def test_conflicting_ownership_is_unresolved_without_revocation(db,config,graph):
    connected(db,config,graph)
    owner = db.scalar(select(SocialPrivacyOwnership).where(SocialPrivacyOwnership.credential_id.is_not(None)))
    db.add(SocialPrivacyOwnership(id=uuid4(), app_id='123', digest_version='d1',
        subject_digest=digester().digest('123','702'), reference_key='conflicting:'+str(uuid4()),
        flow_id=owner.flow_id, credential_id=owner.credential_id, credential_version=owner.credential_version,
        generation_at=owner.generation_at))
    db.commit()
    out=privacy(db,config).receive(signed(config),kind='deauthorization')
    assert out['state']=='ownership_unresolved' and out['resolution']=='conflicting_ownership'
    assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))


def test_wrong_credential_version_does_not_revoke_replaced_version(db,config,graph):
    connected(db,config,graph)
    for c in db.scalars(select(SocialCredential)):
        c.version += 1
    db.commit()
    out=privacy(db,config).receive(signed(config),kind='deauthorization')
    assert out['resolution']=='indexed_partial_version_changed'
    assert out['state']=='ownership_unresolved'
    assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))
    assert all(a.connection_state=='connected' for a in db.scalars(select(SocialAccount)))


def test_inventory_seam_keeps_retention_and_unattributed_categories_pending(db,config,graph):
    from social.privacy.policy import inventory_for_review
    connected(db,config,graph)
    privacy(db,config).receive(signed(config),kind='data_deletion')
    receipt=db.scalar(select(SocialPrivacyReceipt))
    inventory=inventory_for_review(db,receipt.id)
    assert inventory['decision'].deletion_completed is False
    assert inventory['decision'].deletion_authorized is False
    assert inventory['credential_envelopes']==2 and inventory['account_metadata']==2
    assert 'legal_retention_basis' in inventory['unknown_categories']


def test_rotation_does_not_relabel_retained_app_namespace(db,config,graph):
    from dataclasses import replace
    from social.connections.contracts import AccountCommand
    from social.connections.service import ConnectionService
    from social.privacy.ownership import OwnershipRecorder
    _, _, selected=connected(db,config,graph)
    changed=replace(config,app_id='456')
    svc=ConnectionService(db,changed,ownership_recorder=OwnershipRecorder('456',digester()))
    aid=UUID(selected['accounts'][0]['id'])
    row=db.get(SocialAccount,aid)
    body=AccountCommand(expected_credential_id=row.credential_id,expected_credential_version=1,reason='Rotate retained credential')
    db.rollback()
    with pytest.raises(SocialError):
        svc.account_command(aid,ACTOR,BINDING,'POST rotate',uuid4(),body,uuid4(),rotate=True)
    assert not list(db.scalars(select(SocialPrivacyOwnership).where(SocialPrivacyOwnership.app_id=='456')))


def test_variant_limit_never_acknowledges_unpersisted_exact_identity(db,config):
    for n in range(64):
        privacy(db,config).receive(signed(config,raw=' '*n+'{"algorithm":"HMAC-SHA256","user_id":"701"}'),kind='data_deletion')
    with pytest.raises(SocialError) as caught:
        privacy(db,config).receive(signed(config,raw=' '*64+'{"algorithm":"HMAC-SHA256","user_id":"701"}'),kind='data_deletion')
    assert caught.value.code=='PRIVACY_VARIANT_LIMIT'


def test_issued_cutoff_precedes_bounded_lookup_so_history_is_not_hidden(db,config,graph):
    connected(db,config,graph)
    owners=list(db.scalars(select(SocialPrivacyOwnership)))
    db.rollback()
    # Synthetic indexed historical/nonhistorical rows exercise SQL query bound.
    # All share an inspected flow; none of the synthetic later refs authorizes
    # a different credential. The one eligible record has a maximal UUID.
    from social.privacy.models import immutable_privacy_history
    event.remove(SocialPrivacyOwnership,'before_update',immutable_privacy_history)
    try:
        for owner in owners:
            owner.generation_at=datetime(2030,1,1,tzinfo=timezone.utc)
        chosen=owners[0]
        db.add(SocialPrivacyOwnership(id=UUID(int=2**128-1),app_id='123',digest_version='d1',subject_digest=chosen.subject_digest,
            reference_key='eligible-history',flow_id=chosen.flow_id,generation_at=datetime(2000,1,1,tzinfo=timezone.utc)))
        for n in range(1,502):
            db.add(SocialPrivacyOwnership(id=UUID(int=n),app_id='123',digest_version='d1',subject_digest=chosen.subject_digest,
                reference_key='later:'+str(n),flow_id=chosen.flow_id,generation_at=datetime(2030,1,1,tzinfo=timezone.utc)))
        db.commit()
    finally:
        event.listen(SocialPrivacyOwnership,'before_update',immutable_privacy_history)
    out=privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':1600000000}),kind='deauthorization')
    assert out['resolution']=='indexed_partial'
    receipt=db.scalar(select(SocialPrivacyReceipt))
    assert len(receipt.affected)==1 and receipt.affected[0]['ownership_id']==str(UUID(int=2**128-1))


def test_long_running_reconnect_flow_does_not_age_new_credential_generation(db,config,graph):
    svc=connection(db,config,graph)
    flow,state=start(svc)
    row=db.get(SocialOAuthFlow,UUID(flow['flow_id']))
    row.created_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    db.commit()
    complete(svc,state)
    select_asset(svc,UUID(flow['flow_id']))
    payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':int((datetime.now(timezone.utc)-timedelta(seconds=5)).timestamp())}
    out=privacy(db,config).receive(signed(config,payload=payload),kind='deauthorization')
    assert out['state']=='ownership_unresolved'
    assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))


def test_same_second_issuance_is_explicitly_ambiguous(db,config,graph):
    connected(db,config,graph)
    owner=db.scalar(select(SocialPrivacyOwnership))
    from social.service import utc
    issued=int(utc(owner.generation_at).timestamp())
    db.rollback()
    out=privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':issued}),kind='deauthorization')
    assert out['resolution']=='indexed_partial_timestamp_ambiguous'
    assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))


def test_expiry_only_delayed_callback_cannot_revoke_later_generation(db,config,graph):
    connected(db,config,graph)
    payload={'algorithm':'HMAC-SHA256','user_id':'701','expires':int((datetime.now(timezone.utc)-timedelta(seconds=5)).timestamp())}
    out=privacy(db,config).receive(signed(config,payload=payload),kind='deauthorization')
    assert out['state']=='ownership_unresolved'
    assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))

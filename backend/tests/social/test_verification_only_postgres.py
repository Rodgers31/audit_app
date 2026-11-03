"""Paused saved-grant commits on an explicitly assigned local PostgreSQL schema."""
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from social.connections.service import ConnectionService
from social.connections.verification import SavedGrantVerificationAuthority
from social.models import SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls
from social.service import SocialError
from test_connections_postgres import connection_pg_engine
from test_connections_support import config, graph, svc, start, complete, select_asset
from test_existing_grant_verification import body_for, verify


def connected(db, config, graph, platform):
    bootstrap = svc(db, config, graph)
    flow, state = start(bootstrap)
    complete(bootstrap, state)
    select_asset(bootstrap, UUID(flow['flow_id']))
    service = ConnectionService(db, config, verification_authority=SavedGrantVerificationAuthority(
        config, transport=httpx.MockTransport(graph)))
    row = db.scalar(select(SocialAccount).where(SocialAccount.platform == platform))
    db.rollback()
    graph.calls.clear()
    return service, row


@pytest.mark.parametrize('platform', ['facebook', 'instagram'])
def test_pg_verification_only_commit_is_paused_and_replay_needs_no_provider(connection_pg_engine, config, graph, platform):
    from uuid import uuid4
    with Session(connection_pg_engine, expire_on_commit=False) as db:
        service, row = connected(db, config, graph, platform)
        original = graph.__call__
        def read(request):
            assert not db.in_transaction()
            return original(request)
        service.verification_authority = SavedGrantVerificationAuthority(config, transport=httpx.MockTransport(read))
        body, key = body_for(service, row), uuid4()
        result = verify(service, row, body, key)
        calls = len(graph.calls)
        assert calls and all(r.method == 'GET' for r in graph.calls)
        assert result['enable_available'] is False and result['publishing_enabled'] is False
        assert verify(service, row, body, key) == result and len(graph.calls) == calls
        db.expire_all()
        assert db.get(SocialAccount, row.id).capability_snapshot['adapter_available'] is False
        assert db.get(SocialControls, 1).publishing_enabled is False
        assert db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'connection.publishing_access_verified'))


@pytest.mark.parametrize('platform', ['facebook', 'instagram'])
@pytest.mark.parametrize('corruption', ['proof', 'audit'])
def test_pg_receipt_time_corruption_rolls_back_paused_proof_and_receipt(connection_pg_engine, config, graph, platform, corruption):
    with Session(connection_pg_engine, expire_on_commit=False) as db:
        service, row = connected(db, config, graph, platform)
        account_id = row.id
        body = body_for(service, row)
        if corruption == 'proof':
            statement = "UPDATE social_accounts SET capability_snapshot = '{}'::json WHERE id = '" + str(account_id) + "';"
        else:
            statement = "DELETE FROM social_audit_events WHERE action = 'connection.publishing_access_verified';"
        db.execute(text("CREATE FUNCTION corrupt_verification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF NEW.route_key LIKE 'POST verify/%' THEN " + statement + " END IF; RETURN NEW; END $$"))
        db.execute(text('CREATE TRIGGER receipt_corruption AFTER INSERT ON social_command_receipts '
            'FOR EACH ROW EXECUTE FUNCTION corrupt_verification()'))
        db.commit()
        with pytest.raises(SocialError, match='ACCOUNT_CONTROL_FAILED'):
            verify(service, row, body)
        db.expire_all()
        assert db.get(SocialControls, 1).version == body['expected_controls_version']
        assert db.get(SocialAccount, account_id).capability_snapshot['adapter_available'] is False
        assert not db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'connection.publishing_access_verified'))
        assert not db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.route_key.like('POST verify/%')))


@pytest.mark.parametrize('change', ['controls', 'sibling'])
def test_pg_concurrent_commit_during_reads_refuses_stale_verification(connection_pg_engine, config, graph, change):
    with Session(connection_pg_engine, expire_on_commit=False) as db:
        service, row = connected(db, config, graph, 'facebook')
        body = body_for(service, row)
        original, changed = graph.__call__, False
        def read(request):
            nonlocal changed
            assert not db.in_transaction()
            if not changed:
                changed = True
                with Session(connection_pg_engine) as other:
                    if change == 'controls':
                        other.get(SocialControls, 1).version += 1
                    else:
                        other.scalar(select(SocialAccount).where(SocialAccount.platform == 'instagram')).publishing_enabled = True
                    other.commit()
            return original(request)
        service.verification_authority = SavedGrantVerificationAuthority(config, transport=httpx.MockTransport(read))
        with pytest.raises(SocialError):
            verify(service, row, body)
        assert not db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'connection.publishing_access_verified'))

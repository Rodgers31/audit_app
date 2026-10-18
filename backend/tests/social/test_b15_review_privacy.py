"""Application-scoped privacy authority and custody startup regressions."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4
import base64
import json
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from social.service import SocialError
from social.privacy.models import SocialPrivacyReceipt, SocialPrivacyOwnership
from social.privacy.workflow_contracts import PrivacyWorkflowConfig
from social.privacy.workflow_startup import configure_privacy_workflow
from test_privacy_workflow import setup, approve, APPROVER, ACTOR
from test_privacy_support import db, config, graph


def foreign_receipt(svc):
    svc.config = replace(svc.config, app_id='999999')


def test_foreign_application_receipt_cannot_authorize_proposal(setup):
    svc, command, _ = setup
    foreign_receipt(svc)
    with pytest.raises(SocialError):
        svc.propose(ACTOR, uuid4(), command)


def test_plan_lookup_and_execution_are_bound_to_registration(setup):
    svc, command, _ = setup
    plan = approve(svc, command)
    foreign_receipt(svc)
    with pytest.raises(SocialError): svc.get(UUID(plan['id']))
    with pytest.raises(SocialError): svc.execute(APPROVER, UUID(plan['id']), 1)


@pytest.mark.parametrize('bad', ['missing', 'file', 'shared', 'symlink'])
def test_execution_startup_refuses_invalid_ledger_custody(tmp_path, bad):
    path = tmp_path/'ledger'
    if bad == 'file': path.write_text('inert')
    if bad == 'shared': path.mkdir(mode=0o755)
    if bad == 'symlink':
        target = tmp_path/'target'; target.mkdir(mode=0o700); path.symlink_to(target)
    app = FastAPI()
    app.state.social_privacy_registration = SimpleNamespace(config=SimpleNamespace(app_id='123'))
    env = {'SOCIAL_PRIVACY_WORKFLOW_ENABLED':'true', 'SOCIAL_PRIVACY_EXECUTION_ENABLED':'true',
        'SOCIAL_PRIVACY_POLICIES':json.dumps({'fixture':'a'*64}),
        'SOCIAL_PRIVACY_APPROVERS':json.dumps([str(APPROVER)]),
        'SOCIAL_PRIVACY_LEDGER_DIRECTORY':str(path),
        'SOCIAL_PRIVACY_LEDGER_SIGNING_KEY':base64.urlsafe_b64encode(b'x'*32).decode()}
    with pytest.raises(SocialError): configure_privacy_workflow(app, env)
    assert not hasattr(app.state, 'social_privacy_workflow_config')


def test_queue_and_detail_are_application_scoped_even_with_workflow_disabled(setup):
    from social.privacy.workflow_api import requests, request_detail
    svc, command, _ = setup
    svc.config = replace(svc.config, enabled=False, execution_enabled=False, app_id='999999')
    result = requests(SimpleNamespace(), page=1, page_size=20, svc=svc)
    assert result['total'] == 0 and result['requests'] == []
    with pytest.raises(SocialError) as caught:
        request_detail(command.receipt_id, svc=svc)
    assert caught.value.status == 404


def test_valid_private_ledger_custody_accepts_startup(tmp_path):
    path = tmp_path/'ledger'; path.mkdir(mode=0o700)
    app = FastAPI()
    app.state.social_privacy_registration = SimpleNamespace(config=SimpleNamespace(app_id='123'))
    cfg = configure_privacy_workflow(app, {'SOCIAL_PRIVACY_WORKFLOW_ENABLED':'true',
        'SOCIAL_PRIVACY_EXECUTION_ENABLED':'true', 'SOCIAL_PRIVACY_POLICIES':json.dumps({'fixture':'a'*64}),
        'SOCIAL_PRIVACY_APPROVERS':json.dumps([str(APPROVER)]),
        'SOCIAL_PRIVACY_LEDGER_DIRECTORY':str(path),
        'SOCIAL_PRIVACY_LEDGER_SIGNING_KEY':base64.urlsafe_b64encode(b'x'*32).decode()})
    assert cfg.execution_enabled is True and cfg.app_id == '123'
    assert list(path.iterdir()) == []

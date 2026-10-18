"""Generation HTTP commands use the existing auth, receipts and review surface."""
import sys
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from social.models import SocialPost, SocialPublication, SocialPostTarget
from test_domain_support import db, account
from test_api_admin import make_client, key
from test_generation import observation


def adapter(monkeypatch, value):
    module = ModuleType('seeding.source_observations')
    class SourceObservationUnavailable(Exception):
        pass
    module.SourceObservationUnavailable = SourceObservationUnavailable
    module.read_county_budget_observation = lambda factory, **kwargs: value.model_dump(mode='json')
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_http_off_controls_auth_and_private_failures(db):
    client = make_client(db.bind)
    path = '/api/v1/admin/social/generation/controls'
    result = client.get(path)
    assert result.status_code == 200 and result.json()['drafts_enabled'] is False
    assert result.headers['cache-control'] == 'private, no-store'
    body = dict(expected_version=1, drafts_enabled=True, shadow_enabled=True, source_allowlist=['cob'], targets=[], reason='Owned fixture')
    forbidden = make_client(db.bind, authenticated=False).patch(path, json=body, headers=key())
    assert forbidden.status_code in {401, 403}
    headers = key()
    first = client.patch(path, json=body, headers=headers)
    assert first.status_code == 200 and first.json()['version'] == 2
    assert client.patch(path, json=body, headers=headers).json() == first.json()
    assert client.patch(path, json=body, headers=key()).status_code == 409
    unsupported = client.patch(path, json={**body, 'auto_publish_enabled': True}, headers=key())
    assert unsupported.status_code == 422
    for path in ('/automation/rules', '/automation/decisions'):
        response = client.get('/api/v1/admin/social' + path)
        assert response.status_code == 200 and response.json()['total'] == 0
        assert response.headers['cache-control'] == 'private, no-store'


def test_http_generated_evidence_filters_and_shadow(monkeypatch, db):
    a = account(db)
    adapter(monkeypatch, observation())
    client = make_client(db.bind, adapters=('facebook',))
    cfg = dict(expected_version=1, drafts_enabled=True, shadow_enabled=True, source_allowlist=['cob'], targets=[dict(account_id=str(a.id), format='text', overrides={})], reason='Owned fixture')
    assert client.patch('/api/v1/admin/social/generation/controls', json=cfg, headers=key()).status_code == 200
    body = dict(record_ids=[1], ingestion_id=42, backfill=True, reason='Explicit first observation fixture')
    response = client.post('/api/v1/admin/social/generation/detect', json=body, headers=key())
    assert response.status_code == 200, response.text
    post_id = response.json()['results'][0]['post_id']
    post = client.get('/api/v1/admin/social/posts/' + post_id).json()
    evidence = client.get('/api/v1/admin/social/posts/' + post_id + '/evidence')
    assert evidence.status_code == 200
    assert evidence.json()['evidence']['source']['facts'][0]['value'] == '123.45'
    assert evidence.json()['revision_id'] == post['revision_id']
    assert client.get('/api/v1/admin/social/posts?origin_type=manual').json()['total'] == 0
    assert client.get('/api/v1/admin/social/posts?origin_type=generated&content_type=dataset_availability').json()['total'] == 1
    rule_id = str(uuid4())
    definition = dict(expected_version=0, name='Dataset suggestions', mode='shadow', categories=['dataset_availability'], source_allowlist=['cob'], account_allowlist=[str(a.id)], reason='Owned fixture')
    created = client.post(f'/api/v1/admin/social/automation/rules/{rule_id}/versions', json=definition, headers=key())
    assert created.status_code == 201, created.text
    evaluate = dict(expected_version=post['version'], revision_id=post['revision_id'], rule_id=rule_id, rule_version=1)
    decision = client.post('/api/v1/admin/social/posts/' + post_id + '/shadow', json=evaluate, headers=key())
    assert decision.status_code == 200 and decision.json()['outcome'] == 'would_allow', decision.text
    history = client.get('/api/v1/admin/social/automation/decisions?post_id=' + post_id).json()
    assert history['total'] == 1 and history['decisions'][0]['id'] == decision.json()['id']
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0
    assert db.get(SocialPost, UUID(post_id)).editorial_state == 'pending_review'
    invalid = client.post('/api/v1/admin/social/generation/detect', json={**body, 'facts': observation().model_dump(mode='json')['facts']}, headers=key())
    assert invalid.status_code == 422


def test_detect_replay_preserves_receipt_when_source_later_unavailable(monkeypatch, db):
    adapter(monkeypatch, observation())
    client = make_client(db.bind)
    cfg = dict(expected_version=1, drafts_enabled=True, shadow_enabled=False, source_allowlist=['cob'], targets=[], reason='Owned fixture')
    client.patch('/api/v1/admin/social/generation/controls', json=cfg, headers=key())
    headers = key()
    body = dict(record_ids=[1], ingestion_id=42, backfill=True, reason='Explicit first observation')
    first = client.post('/api/v1/admin/social/generation/detect', json=body, headers=headers)
    assert first.status_code == 200, first.text
    def unavailable(*args, **kwargs):
        raise AssertionError('A stored receipt must not re-read the source')
    monkeypatch.setattr(sys.modules['seeding.source_observations'], 'read_county_budget_observation', unavailable)
    replay = client.post('/api/v1/admin/social/generation/detect', json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    conflict = client.post('/api/v1/admin/social/generation/detect', json={**body, 'backfill': False}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()['detail']['code'] == 'IDEMPOTENCY_CONFLICT'

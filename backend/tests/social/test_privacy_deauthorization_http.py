"""Explicit app-removal ingress: durable revocation, opaque acknowledgement."""
import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from social.models import SocialAccount
from social.privacy.api import DATA_PATH, STATUS_PATH
from social.privacy.models import SocialPrivacyReceipt
from social.privacy.startup import configure_meta_privacy
from test_privacy_support import config, connected, db, graph, signed

DEAUTH = '/api/v1/social/privacy/meta/deauthorization'


def configured_client(db, config, deauthorization=True):
    app = FastAPI()
    configure_meta_privacy(app, sessionmaker(db.bind), {
        'META_PRIVACY_ENABLED': 'true', 'META_CONNECTIONS_ENABLED': 'false',
        'META_DEAUTHORIZATION_ENABLED': str(deauthorization).lower(),
        'META_APP_ID': config.app_id, 'META_APP_SECRET': config.app_secret,
        'META_PRIVACY_STATUS_URL': 'https://privacy.example.test' + STATUS_PATH,
        'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION': config.active_key_version,
        'SOCIAL_CREDENTIAL_KEYS': json.dumps(config.encryption_keys),
        'META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION': 'd1',
        'META_PRIVACY_SUBJECT_KEYS': json.dumps({'d1': base64.urlsafe_b64encode(b'x' * 32).decode()}),
    })
    return TestClient(app, raise_server_exceptions=False)


def test_signed_app_removal_blocks_indexed_accounts_and_acknowledges_only_after_persist(db, config, graph):
    connected(db, config, graph)
    client = configured_client(db, config)
    response = client.post(DEAUTH, data={'signed_request': signed(config)})
    assert response.status_code == 200
    assert response.content == b''
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    with Session(db.bind) as fresh:
        accounts = list(fresh.scalars(select(SocialAccount)))
        assert accounts and all(a.connection_state == 'revoked' and not a.publishing_enabled for a in accounts)
        receipt = fresh.scalar(select(SocialPrivacyReceipt))
        assert receipt.kind == 'deauthorization'
        assert receipt.state == 'blocked_future_mutations'
        assert receipt.confirmation_hash is None
    assert client.post(DEAUTH, data={'signed_request': signed(config)}).content == b''
    with Session(db.bind) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 1
    assert client.get(DEAUTH).status_code == 405


def test_disabled_app_removal_keeps_existing_deletion_ingress(db, config):
    client = configured_client(db, config, deauthorization=False)
    assert client.post(DEAUTH, data={'signed_request': signed(config)}).status_code == 404
    assert client.post(DATA_PATH, data={'signed_request': signed(config)}).status_code == 200


def test_unknown_subject_receives_no_ownership_or_deletion_status_details(db, config):
    response = configured_client(db, config).post(DEAUTH, data={'signed_request': signed(config)})
    assert response.status_code == 200 and response.content == b''
    with Session(db.bind) as fresh:
        receipt = fresh.scalar(select(SocialPrivacyReceipt))
        assert receipt.state == 'ownership_unresolved'
        assert receipt.affected == []


def test_failed_commit_is_not_acknowledged_or_echoed(db, config):
    client = configured_client(db, config)

    def reject_commit(session):
        raise RuntimeError('INERT_PRIVATE_COMMIT_FAILURE')

    event.listen(Session, 'before_commit', reject_commit)
    try:
        response = client.post(DEAUTH, data={'signed_request': signed(config)})
    finally:
        event.remove(Session, 'before_commit', reject_commit)
    assert response.status_code == 500
    assert 'INERT_PRIVATE_COMMIT_FAILURE' not in response.text
    with Session(db.bind) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 0


@pytest.mark.parametrize('body', ['', 'signed_request=', 'signed_request=x',
    'signed_request=x&signed_request=y', 'signed_request=x&unknown=y',
    'signed_request=%ZZ', 'signed_request=%FF', 'signed_request=' + 'x' * 25001])
def test_deauthorization_rejects_unsigned_malformed_and_oversized_input(db, config, body):
    response = configured_client(db, config).post(DEAUTH, content=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'PRIVACY_REQUEST_INVALID'

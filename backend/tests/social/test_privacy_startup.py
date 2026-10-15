"""Configured assembly executes durable receipts; only inert keys and SQLite."""
import base64
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from social.privacy.api import DATA_PATH, STATUS_PATH
from social.privacy.models import SocialPrivacyReceipt
from social.privacy.startup import configure_meta_privacy
from test_privacy_support import config, db, signed


def test_configured_runtime_persists_before_ack_and_survives_connection_disable(db, config):
    values = {
        'META_PRIVACY_ENABLED': 'true', 'META_CONNECTIONS_ENABLED': 'false',
        'META_APP_ID': config.app_id, 'META_APP_SECRET': config.app_secret,
        'META_PRIVACY_STATUS_URL': 'https://privacy.example.test' + STATUS_PATH,
        'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION': config.active_key_version,
        'SOCIAL_CREDENTIAL_KEYS': json.dumps(config.encryption_keys),
        'META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION': 'd1',
        'META_PRIVACY_SUBJECT_KEYS': json.dumps({'d1': base64.urlsafe_b64encode(b'd' * 32).decode()}),
    }
    app = FastAPI()
    configure_meta_privacy(app, sessionmaker(db.bind), values)
    response = TestClient(app).post(DATA_PATH, data={'signed_request': signed(config)})
    assert response.status_code == 200
    assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt)) == 1
    assert set(response.json()) == {'url', 'confirmation_code'}
    # Reconstruct the actual runtime dependencies, like a process restart.
    again = FastAPI()
    configure_meta_privacy(again, sessionmaker(db.bind), values)
    client = TestClient(again)
    retry = client.post(DATA_PATH, data={'signed_request': signed(config)})
    assert retry.json() == response.json()
    status = client.get(STATUS_PATH, params={'code': response.json()['confirmation_code']})
    assert status.status_code == 200
    assert status.json()['status'] == 'pending_review'
    assert status.json()['deletion_completed'] is False
    assert client.post(DATA_PATH.replace('data-deletion', 'deauthorization')).status_code == 404

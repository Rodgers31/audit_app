from dataclasses import replace
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from social.privacy.api import DATA_PATH, STATUS_PATH, create_privacy_router, MAX_BODY_BYTES
from social.privacy.runtime import PrivacyRegistration, install_privacy
from social.privacy.service import PrivacyConfig
from social.connections.crypto import CredentialCipher
from test_privacy_support import *


def client(db, config, enabled=True):
    app = FastAPI()
    registration = PrivacyRegistration(PrivacyConfig(config.app_id, config.app_secret,
        'https://privacy.example.test' + STATUS_PATH, enabled), digester(),
        CredentialCipher(config.active_key_version, config.encryption_keys), sessionmaker(db.bind))
    install_privacy(app, registration)
    return TestClient(app, raise_server_exceptions=False)


def test_http_positive_status_and_oauth_disabled_are_independent(db, config):
    c = client(db, replace(config, enabled=False))
    result = c.post(DATA_PATH, data={'signed_request':signed(config)})
    assert result.status_code == 200
    assert set(result.json()) == {'url','confirmation_code'}
    status = c.get(STATUS_PATH, params={'code':result.json()['confirmation_code']})
    assert status.status_code == 200
    assert status.json()['deletion_completed'] is False
    assert 'has not been completed' in status.json()['message']
    assert '701' not in status.text and config.app_secret not in result.text
    for response in (result,status):
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
    assert c.post(DATA_PATH.replace('data-deletion','deauthorization'),data={'signed_request':signed(config)}).status_code == 404
    assert c.get(DATA_PATH).status_code == 405


def test_default_runtime_has_no_ingress_and_no_implicit_install(db, config):
    assert TestClient(FastAPI()).post(DATA_PATH).status_code == 404
    c = client(db, config, enabled=False)
    assert c.post(DATA_PATH).status_code == 404
    assert c.get(STATUS_PATH).status_code == 404


@pytest.mark.parametrize('body', ['', 'signed_request=', 'signed_request=x&signed_request=x', 'signed_request=x&unknown=y', 'unknown=x', 'signed_request=%ZZ', 'signed_request=%FF', 'signed_request='+'x'*(MAX_BODY_BYTES+1)])
def test_hostile_form_bounded_no_echo(db, config, body):
    response = client(db,config).post(DATA_PATH,content=body,headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'PRIVACY_REQUEST_INVALID'
    assert 'signed_request=' not in response.text


@pytest.mark.parametrize('code', ['', '0'*64, 'a'*63, 'A'*64, str(uuid4()), '701', '../etc/passwd', "' OR 1=1--"])
def test_hostile_status_lookup_opaque_miss(db, config, code):
    response = client(db,config).get(STATUS_PATH,params={'code':code})
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'NOT_FOUND'
    assert 'Request status was not found' in response.text
    assert code not in response.text if code else True


@pytest.mark.parametrize('query', ['','code=x&code=y','id=701','code=x&subject=701'])
def test_status_duplicate_unknown_or_missing_query(db, config, query):
    assert client(db,config).get(STATUS_PATH+'?'+query).status_code == 404


@pytest.mark.parametrize('headers', [{'Content-Type':'application/json'}, {'Content-Type':'application/x-www-form-urlencoded','Content-Encoding':'gzip'}, {'Content-Type':'application/x-www-form-urlencoded','Content-Length':'NaN'}])
def test_ingress_header_shape(db, config, headers):
    assert client(db,config).post(DATA_PATH,content='signed_request=x',headers=headers).status_code == 400


def test_streamed_oversize_without_content_length_is_rejected(db,config):
    def chunks():
        yield b'signed_request='
        yield b'x' * (MAX_BODY_BYTES+1)
    assert client(db,config).post(DATA_PATH,content=chunks(),headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code == 400

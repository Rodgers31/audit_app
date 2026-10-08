"""Execute review findings with forced worker changes and hostile provider ports."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from social.connections.crypto import CredentialCipher
from social.connections.provider import InspectedDiscovery
from social.privacy.api import DATA_PATH, STATUS_PATH
from social.privacy.api import create_privacy_router
from social.privacy.runtime import PrivacyRegistration, install_privacy
from social.privacy.ownership import OwnershipRecorder
from social.privacy.service import PrivacyConfig
from social.service import SocialError
from test_privacy_support import db, config, graph, connected, privacy, digester, signed


def test_installed_privacy_session_creation_work_and_close_share_worker(db, config, monkeypatch):
    instances = []

    class ThreadConfinedSession(Session):
        def __init__(self, *args, **kwargs):
            self.owner_thread = get_ident()
            instances.append(self)
            super().__init__(*args, **kwargs)

        def begin(self, *args, **kwargs):
            assert get_ident() == self.owner_thread, 'Session crossed a worker boundary'
            return super().begin(*args, **kwargs)

        def close(self):
            assert get_ident() == self.owner_thread, 'Session closed on another worker'
            return super().close()

    async def separate_worker(function, *args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as worker:
            return worker.submit(function, *args, **kwargs).result(timeout=5)

    monkeypatch.setattr('social.privacy.api.run_in_threadpool', separate_worker)
    app = FastAPI()
    registration = PrivacyRegistration(
        PrivacyConfig(config.app_id, config.app_secret, 'https://privacy.example.test' + STATUS_PATH, True),
        digester(), CredentialCipher(config.active_key_version, config.encryption_keys),
        sessionmaker(db.bind, class_=ThreadConfinedSession))
    install_privacy(app, registration)
    with TestClient(app) as browser:
        response = browser.post(DATA_PATH, data={'signed_request': signed(config)})
        assert response.status_code == 200
        code = response.json()['confirmation_code']
        assert browser.get(STATUS_PATH, params={'code': code}).status_code == 200
        before = len(instances)
        assert browser.post(DATA_PATH, content='invalid', headers={'Content-Type': 'application/json'}).status_code == 400
        assert len(instances) == before
    assert len(instances) == 2


@pytest.mark.parametrize('page_id', [[], {}, True, 901, '0', 'bad', '9' * 65])
def test_inspected_page_ids_are_sanitized_before_set_or_database(db, page_id):
    inspected = InspectedDiscovery('123', '701', (page_id,), {})
    with pytest.raises(SocialError) as caught:
        OwnershipRecorder('123', digester()).record_discovery(db, None, inspected)
    assert caught.value.code == 'PRIVACY_OWNERSHIP_UNRESOLVED'


def test_ingress_parse_refusal_discards_secret_bearing_decoder_context():
    import asyncio
    from starlette.requests import Request

    body = b'signed_request=fixture-secret\xff'
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}
    request = Request({'type': 'http', 'method': 'POST', 'path': DATA_PATH,
                       'query_string': b'', 'headers': [(b'content-type', b'application/x-www-form-urlencoded')]}, receive)
    endpoint = create_privacy_router(lambda: None).routes[0].endpoint
    with pytest.raises(SocialError) as caught:
        asyncio.run(endpoint(request, None))
    assert caught.value.code == 'PRIVACY_REQUEST_INVALID'
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize('version_count', [16, 17, 20])
def test_distinct_history_sample_cannot_hide_unavailable_digest_versions(db, config, graph, version_count):
    from datetime import datetime, timezone
    from uuid import uuid4
    from sqlalchemy import select
    from social.models import SocialAccount
    from social.privacy.models import SocialPrivacyOwnership
    from social.privacy.subjects import SubjectDigester

    keys = SubjectDigester('d1', {f'd{i}': bytes([i]) * 32 for i in range(1, 17)})
    _, flow, _ = connected(db, config, graph, keys)
    with db.begin():
        for index in range(1, version_count + 1):
            version = f'd{index}'
            digest = keys.digest(config.app_id, '701', version) if index <= 16 else 'a' * 64
            db.add(SocialPrivacyOwnership(id=uuid4(), app_id=config.app_id,
                digest_version=version, subject_digest=digest, reference_key='review:' + str(uuid4()),
                flow_id=flow, generation_at=datetime.now(timezone.utc)))
    result = privacy(db, config, keys).receive(signed(config), kind='deauthorization')
    if version_count > 16:
        assert result['resolution'] == 'digest_key_unavailable'
        assert result['state'] == 'ownership_unresolved'
        assert all(account.connection_state == 'connected' for account in db.scalars(select(SocialAccount)))
    else:
        assert result['resolution'] == 'indexed_partial'
        assert result['state'] == 'blocked_future_mutations'

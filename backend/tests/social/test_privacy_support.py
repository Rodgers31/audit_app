"""Private fixtures execute actual MetaProvider through MockTransport."""
import base64
import hashlib
import hmac
import json
from uuid import UUID
import httpx
from social.connections.crypto import CredentialCipher
from social.connections.service import ConnectionService
from social.connections.provider import MetaProvider
from social.privacy.ownership import OwnershipRecorder
from social.privacy.service import PrivacyConfig, PrivacyService
from social.privacy.subjects import SubjectDigester
from test_connections_support import config, db, graph, start, complete, select_asset, ACTOR, BINDING


def digester(active='d1', keys=None):
    return SubjectDigester(active, keys or {'d1': b'x' * 32})


def connection(db, config, graph, keys=None):
    return ConnectionService(db, config, provider_factory=lambda c: MetaProvider(c, transport=httpx.MockTransport(graph)),
        ownership_recorder=OwnershipRecorder(config.app_id, keys or digester()))


def privacy(db, config, keys=None, enabled=True):
    return PrivacyService(db, PrivacyConfig(config.app_id, config.app_secret,
        'https://privacy.example.test/api/v1/social/privacy/meta/data-deletion/status', enabled),
        digester=keys or digester(), cipher=CredentialCipher(config.active_key_version, config.encryption_keys))


def signed(config, subject='701', *, payload=None, raw=None, padded=False):
    value = raw or json.dumps(payload or {'algorithm': 'HMAC-SHA256', 'user_id': subject}, separators=(',', ':'))
    encoded = base64.urlsafe_b64encode(value.encode()).decode()
    if not padded:
        encoded = encoded.rstrip('=')
    mac = base64.urlsafe_b64encode(hmac.new(config.app_secret.encode(), encoded.encode(), hashlib.sha256).digest()).decode().rstrip('=')
    return mac + '.' + encoded


def connected(db, config, graph, keys=None):
    svc = connection(db, config, graph, keys)
    flow, state = start(svc)
    complete(svc, state)
    selected = select_asset(svc, UUID(flow['flow_id']))
    return svc, UUID(flow['flow_id']), selected

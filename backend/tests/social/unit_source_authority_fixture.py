"""Explicit authority port for the historical SQLite policy unit fixtures.

This is not source qualification. Only observations deliberately registered by
the declared synthetic test producer can receive a marker. Real guards remain
the default, and the production verifier rejects these markers unconditionally.
Current-source admission is exercised separately with owned PostgreSQL writers.
"""
from uuid import uuid4

import social.generation.worker_authority as authority
from social.contracts import canonical_hash
from social.generation.contracts import SourceObservation

_REAL_CAPTURE = authority.capture_worker_authority
_REAL_VERIFY = authority.verify_worker_authority
_SESSION_KEY = 'historical_sqlite_unit_source_authority'


def _engine(db):
    binding = db.get_bind() if hasattr(db, 'get_bind') else db
    # Worker authority wraps an already-owned Connection in a Session. That
    # preserves its Engine identity; it must not mint a new unit scope.
    return binding.engine


def _raw(value):
    return SourceObservation.model_validate(
        value.model_dump(mode='python') if isinstance(value, SourceObservation) else value
    ).model_dump(mode='json')


def _declared_fixture(source):
    facts = source['facts']
    return (source['source_type'] == 'cob'
        and source['source_key'] == 'county:1:budget:2025'
        and source['ingestion_id'] in {'job:42', 'job:43'}
        and source.get('report') is None and source.get('financial') is None
        and source['committed'] is True and source['fixture'] is False
        and source['quarantined'] is False and source['publishable'] is True
        and len(facts) == 1 and facts[0]['fact_id'] == 'county:1:budget'
        and facts[0]['source_document_id'] == 1
        and facts[0]['document_url'] == 'https://example.gov/report.pdf'
        and facts[0]['document_checksum'] == 'a' * 64)


class UnitSourceAuthority:
    def __init__(self, engine):
        if engine.dialect.name != 'sqlite':
            raise ValueError('The unit authority port is SQLite-only')
        self.engine = engine
        self.owner = str(uuid4())
        self.source_hashes = set()

    def register(self, value):
        source = _raw(value)
        if not _declared_fixture(source):
            raise ValueError('Only the declared synthetic unit source may be registered')
        self.source_hashes.add(canonical_hash(source))

    def _marker(self, digest):
        return {'UNIT_AUTHORITY_ONLY': True, 'version': 'test-only-v1',
            'owner': self.owner, 'source_hash': digest}

    def capture(self, db, source):
        digest = canonical_hash(source)
        if _engine(db) is self.engine and digest in self.source_hashes:
            return self._marker(digest)
        return _REAL_CAPTURE(db, source)

    def verify(self, db, source, witness):
        digest = canonical_hash(source)
        if (_engine(db) is self.engine and digest in self.source_hashes
                and type(witness) is dict
                and set(witness) == {'UNIT_AUTHORITY_ONLY', 'version', 'owner', 'source_hash'}
                and witness['UNIT_AUTHORITY_ONLY'] is True
                and type(witness['version']) is str and witness['version'] == 'test-only-v1'
                and type(witness['owner']) is str and witness['owner'] == self.owner
                and type(witness['source_hash']) is str and witness['source_hash'] == digest):
            return
        return _REAL_VERIFY(db, source, witness)


def install_unit_source_authority(monkeypatch, db):
    """Opt in at a named unit setup, never via a session-wide/autouse fixture."""
    current = db.info.get(_SESSION_KEY)
    if current is not None:
        if current.engine is not _engine(db):
            raise ValueError('Unit authority cannot move between engines')
        port = current
    else:
        port = UnitSourceAuthority(_engine(db))
        db.info[_SESSION_KEY] = port
    monkeypatch.setattr(authority, 'capture_worker_authority', port.capture)
    monkeypatch.setattr(authority, 'verify_worker_authority', port.verify)
    return port


def register_unit_observation(db, value):
    """Called only by test producers; no opt-in means no change in authority."""
    port = db.info.get(_SESSION_KEY)
    if port is not None:
        port.register(value)
    return value


def unit_observation_payload(db, value):
    register_unit_observation(db, value)
    return value.model_dump(mode='json')

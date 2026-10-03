"""Explicit isolated fake object store; never imported by runtime code."""
from dataclasses import replace
import hashlib
import shutil
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.media.storage import ObjectSnapshot, SignedAccess, StorageFailure
from social.models import Base

ACTOR = uuid4()
ENDPOINT = 'https://' + 'a' * 32 + '.r2.cloudflarestorage.com'


def png():
    output = BytesIO(); Image.new('RGB', (64, 32), 'green').save(output, format='PNG'); return output.getvalue()


class FakeStorage:
    provider, bucket = 'r2', 'media-test'
    def __init__(self):
        self.objects = {}; self.fail = None; self.operations = []; self.hook = None
    def check(self, operation):
        self.operations.append(operation)
        if self.hook: self.hook(operation)
        if self.fail == operation: raise StorageFailure('safe fake failure')
    def authorize_upload(self, key, size, mime, ttl):
        self.check('authorize'); self.last_key = key
        return SignedAccess(ENDPOINT + '/media-test/' + key + '?fixture=secret', {'Content-Type': mime, 'If-None-Match': '*'})
    def head(self, key):
        self.check('head')
        if key not in self.objects: raise StorageFailure('missing fake object')
        data, mime, sha = self.objects[key]
        return ObjectSnapshot(len(data), hashlib.md5(data).hexdigest(), None, sha, mime)
    def download(self, key, snapshot, path, maximum):
        self.check('download'); data = self.objects[key][0]
        if len(data) > maximum or self.head(key) != snapshot: raise StorageFailure('fake changed')
        path.write_bytes(data)
    def finalize(self, path, key, size, mime, sha256):
        self.check('finalize'); data = path.read_bytes()
        self.objects.setdefault(key, (data, mime, sha256))
        return self.head(key)
    def preview(self, key, snapshot, ttl):
        self.check('preview'); return SignedAccess(ENDPOINT + '/media-test/' + key + '?fixture=preview-secret')
    def delete(self, key):
        self.check('delete'); self.objects.pop(key, None)


@pytest.fixture
def media_db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def fk(conn, record): conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    with Session(engine, expire_on_commit=False) as session: yield session
    engine.dispose()


@pytest.fixture
def media(media_db):
    config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='test', secret_key='test', ffprobe_path=shutil.which('ffprobe'))
    storage = FakeStorage()
    runtime = MediaRuntime(config, storage, LocalInspector(config))
    return MediaService(media_db, runtime), storage


def intent(data=None, **updates):
    return {'filename': 'actual.png', 'declared_mime_type': 'image/png', 'declared_size': len(png() if data is None else data), **updates}


def upload_ready(media, actor=ACTOR, **updates):
    svc, storage = media; data = png()
    grant = svc.initiate(actor, uuid4(), intent(data, **updates), uuid4())
    storage.objects[storage.last_key] = (data, 'image/png', None)
    result = svc.complete(actor, grant.asset.id, uuid4(), 1, uuid4())
    return result

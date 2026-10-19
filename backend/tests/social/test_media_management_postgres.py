"""Actual migrated local PostgreSQL checks; never uses a cloud database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialMediaAsset, SocialPost, SocialRevisionAsset
from social.service import SocialError, SocialService
from test_domain_postgres import pg_engine
from test_domain_support import draft_body, call
from test_media_migration_postgres import upgrade
from test_media_support import ENDPOINT, FakeStorage
from test_media_management import archive, settled


@pytest.fixture
def pg_media(pg_engine):
    upgrade(pg_engine)
    cfg = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture', secret_key='fixture')
    storage = FakeStorage(); runtime = MediaRuntime(cfg, storage, LocalInspector(cfg))
    with Session(pg_engine, expire_on_commit=False) as db:
        yield MediaService(db, runtime), storage


def test_pg_metadata_archive_keeps_bytes_quota_and_same_key(pg_media):
    from test_media_management import test_unused_archive_retains_bytes_quota_audit_and_replays
    test_unused_archive_retains_bytes_quota_audit_and_replays(pg_media)


@pytest.mark.parametrize('target', ['audit', 'state', 'version', 'receipt'])
def test_pg_suppressed_persistence_never_reports_success(pg_media, target):
    svc, _ = pg_media; asset = settled(pg_media)
    tables = {'audit': ('social_audit_events', 'INSERT', "IF NEW.action='media.asset_archived' THEN RETURN NULL; END IF;"),
              'state': ('social_media_assets', 'UPDATE', "IF NEW.state='archived' THEN NEW.state := OLD.state; END IF;"),
              'version': ('social_media_uploads', 'UPDATE', 'NEW.version := OLD.version;'),
              'receipt': ('social_command_receipts', 'INSERT', 'RETURN NULL;')}
    table, operation, action = tables[target]
    with svc.db.begin():
        svc.db.execute(text('CREATE FUNCTION suppress754() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+action+' RETURN NEW; END $$'))
        svc.db.execute(text('CREATE TRIGGER suppress754 BEFORE '+operation+' ON '+table+' FOR EACH ROW EXECUTE FUNCTION suppress754()'))
    with pytest.raises(SocialError): archive(svc, asset)
    with svc.db.begin(): assert svc.db.get(SocialMediaAsset, asset.id, populate_existing=True).state == 'ready'


def test_pg_reference_creation_and_archive_serialize_on_asset(pg_media):
    svc, _ = pg_media; asset = settled(pg_media); start = Barrier(2)
    body = draft_body(document={'schema_version': 1, 'master': {'text': 'Evidence', 'link': None, 'hashtags': [], 'media': [{'asset_id': str(asset.id), 'alt_text': None, 'caption_asset_id': None}]}, 'targets': []})
    def action(which):
        with Session(svc.db.bind, expire_on_commit=False) as db:
            start.wait(5)
            try:
                if which == 'archive': archive(MediaService(db, svc.runtime), asset)
                else:
                    # Exercise the real shared reference/asset-lock boundary;
                    # this media migration fixture omits later policy tables.
                    with db.begin():
                        from test_media_support import ACTOR
                        p = SocialPost(id=uuid4(), title='Reference race', content_type='announcement', origin_type='manual', creation_method='admin', editorial_state='draft', created_by=ACTOR)
                        db.add(p); db.flush()
                        social = SocialService(db); social.actor = ACTOR
                        social._new_revision(p, body.document, [], 1)
                return which
            except SocialError: return 'refused'
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(action, ['archive', 'reference']))
    assert results.count('refused') == 1
    with svc.db.begin():
        state = svc.db.get(SocialMediaAsset, asset.id, populate_existing=True).state
        reference = svc.db.scalar(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == asset.id))
        assert (state == 'archived') != (reference is not None)

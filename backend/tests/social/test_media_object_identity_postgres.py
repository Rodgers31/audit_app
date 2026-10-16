"""Execute deterministic identity filtering and stale candidates on real PG."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.service import MediaService
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_cleanup import media_pg
from test_media_object_identity import (
    test_cleanup_cannot_delete_another_ready_original_via_quarantine_key as protect_ready,
    test_malformed_oldest_candidate_does_not_starve_valid_cleanup as bounded_cleanup,
)
from test_media_support import ACTOR, intent, media, media_db, png, settle_writes


@pytest.mark.parametrize('scenario', [protect_ready, bounded_cleanup])
def test_pg_exact_key_filter_preserves_ready_original_and_progress(media_pg, scenario):
    engine, runtime = media_pg
    with Session(engine, expire_on_commit=False) as db:
        scenario((MediaService(db, runtime), runtime.storage))


def test_pg_candidate_identity_change_is_rechecked_after_lock_wait(media_pg):
    engine, runtime = media_pg
    with Session(engine, expire_on_commit=False) as db:
        svc = MediaService(db, runtime)
        target = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
        settle_writes(svc, target.id)
        with db.begin():
            db.get(SocialMediaUpload, target.id).expires_at = svc.now() - timedelta(days=1)
    selected, release = threading.Event(), threading.Event()

    class Paused(MediaService):
        def _budgets(self, actor):
            selected.set()
            assert release.wait(5)
            return super()._budgets(actor)

    def cleanup():
        with Session(engine, expire_on_commit=False) as db:
            return Paused(db, runtime).cleanup()

    calls = list(runtime.storage.operations)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cleanup)
        assert selected.wait(5)
        try:
            with Session(engine) as db, db.begin():
                db.get(SocialMediaUpload, target.id).quarantine_key = 'ready/private-victim/original'
        finally:
            release.set()
        with pytest.raises(SocialError, match='MEDIA_OBJECT_IDENTITY_MISMATCH'):
            future.result(timeout=5)
    assert runtime.storage.operations == calls
    # A fresh process/session must observe no state or capacity release.
    with Session(engine) as db, db.begin():
        upload = db.get(SocialMediaUpload, target.id)
        asset = db.get(SocialMediaAsset, target.id)
        assert not upload.reservation_released and not upload.quarantine_cleaned
        assert upload.reserved_bytes == 2 * len(png())
        assert asset.state == 'archived' and asset.lease_token is None
        assert db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())

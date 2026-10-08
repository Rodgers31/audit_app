"""Draft history must never race maintenance into retaining unusable originals."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from social.models import SocialMediaAsset, SocialRevisionAsset
from social.service import SocialError
from test_domain_support import ACTOR, db, call, draft_body


@pytest.mark.parametrize('state,deleted',[('pending',False),('inspecting',False),('failed',False),('archived',False),('ready',True)])
def test_revision_rejects_nonready_or_deleted_originals(db,state,deleted):
    identity=uuid4()
    db.add(SocialMediaAsset(id=identity,storage_provider='fixture',bucket='fixture',storage_key=str(identity),original_filename='fixture.png',
        mime_type='image/png',byte_size=100,sha256='a'*64,state=state,created_by=ACTOR,deleted_at=datetime.now(timezone.utc) if deleted else None))
    db.commit()
    body=draft_body(document={'master':{'text':'Draft','media':[{'asset_id':str(identity)}]},'targets':[]})
    with pytest.raises(SocialError,match='TARGET_VALIDATION_FAILED'):
        call(db,body,lambda svc:svc.create(body))
    assert db.scalar(select(func.count()).select_from(SocialRevisionAsset)) == 0


def test_ready_caption_and_master_assets_are_retained_in_same_revision(db):
    ids=[uuid4(),uuid4()]
    for identity in ids:
        db.add(SocialMediaAsset(id=identity,storage_provider='fixture',bucket='fixture',storage_key=str(identity),original_filename='fixture.png',
            mime_type='image/png',byte_size=100,sha256='a'*64,state='ready',created_by=ACTOR))
    db.commit()
    body=draft_body(document={'master':{'text':'Draft','media':[{'asset_id':str(ids[0]),'caption_asset_id':str(ids[1])}]},'targets':[]})
    call(db,body,lambda svc:svc.create(body))
    assert set(db.scalars(select(SocialRevisionAsset.asset_id)))==set(ids)

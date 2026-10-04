"""Cancelled unsent authorization resumes explicitly without recreating targets."""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from social.models import SocialAuditEvent, SocialPostTarget, SocialPublication
from social.service import SocialService
from test_api_admin import key, make_client
from test_domain_commands import enable
from test_domain_support import account, db, draft_body


def cancelled_fixture(db):
    row=account(db)
    enable(db)
    client=make_client(db.bind,adapters=('facebook',))
    created=client.post('/api/v1/admin/social/posts',json=draft_body((row,)).model_dump(mode='json'),headers=key()).json()
    base='/api/v1/admin/social/posts/'+created['id']
    accepted=client.post(base+'/publish',json={'expected_version':1,'revision_id':created['revision_id']},headers=key()).json()
    response=client.post(base+'/cancel',json={'expected_version':2},headers=key())
    assert response.status_code==200
    return client,base,created,accepted,{'expected_version':3,'revision_id':created['revision_id'],'reason':'Resume the unchanged reviewed post'}


def test_resume_reuses_authorization_and_targets_with_atomic_receipt(db):
    client,base,created,accepted,body=cancelled_fixture(db)
    headers=key()
    response=client.post(base+'/resume',json=body,headers=headers)
    assert response.status_code==202, response.text
    resumed=response.json()
    assert resumed['publication_id']==accepted['publication_id']
    assert {t['id'] for t in resumed['targets']}=={t['id'] for t in accepted['targets']}
    assert client.post(base+'/resume',json=body,headers=headers).json()==resumed
    assert db.scalar(select(func.count()).select_from(SocialPublication))==1
    assert db.scalar(select(func.count()).select_from(SocialPostTarget))==1
    event=db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action=='post.resumed'))
    assert event.reason==body['reason']
    assert client.get(base).json()['version']==4


def test_resume_cannot_extend_expired_authorization(db):
    client,base,created,accepted,body=cancelled_fixture(db)
    publication=db.get(SocialPublication,UUID(accepted['publication_id']))
    publication.start_deadline=SocialService(db).now()-timedelta(seconds=1)
    db.commit()
    response=client.post(base+'/resume',json=body,headers=key())
    assert response.status_code==409, response.text
    assert response.json()['detail']['code']=='AUTHORIZATION_EXPIRED'
    assert client.get(base).json()['targets'][0]['state']=='cancelled'


def test_resume_refuses_prior_dispatch_and_retains_cancellation(db):
    client,base,created,accepted,body=cancelled_fixture(db)
    target=db.get(SocialPostTarget,UUID(accepted['targets'][0]['id']))
    target.submit_count=1
    db.commit()
    response=client.post(base+'/resume',json=body,headers=key())
    assert response.status_code==409, response.text
    assert response.json()['detail']['code']=='CONTENT_LOCKED'
    assert client.get(base).json()['targets'][0]['state']=='cancelled'


def test_resume_obeys_current_pause_without_changing_targets(db):
    from social.models import SocialControls
    client,base,created,accepted,body=cancelled_fixture(db)
    controls=db.get(SocialControls,1)
    controls.publishing_enabled=False
    db.commit()
    response=client.post(base+'/resume',json=body,headers=key())
    assert response.status_code==409, response.text
    assert response.json()['detail']['code']=='PUBLISHING_PAUSED'
    assert client.get(base).json()['targets'][0]['state']=='cancelled'


def test_resume_preserves_original_future_schedule_and_deadlines(db):
    client,base,created,accepted,body=cancelled_fixture(db)
    publication=db.get(SocialPublication,UUID(accepted['publication_id']))
    due=SocialService(db).now()+timedelta(hours=2)
    publication.scheduled_for=due
    publication.start_deadline=due+timedelta(hours=1)
    publication.retry_deadline=due+timedelta(hours=24)
    original_start,original_retry=publication.start_deadline,publication.retry_deadline
    db.commit()
    response=client.post(base+'/resume',json=body,headers=key())
    assert response.status_code==202, response.text
    db.expire_all()
    from social.service import utc
    publication=db.get(SocialPublication,UUID(accepted['publication_id']))
    target=db.get(SocialPostTarget,UUID(accepted['targets'][0]['id']))
    assert utc(publication.start_deadline)==utc(original_start)
    assert utc(publication.retry_deadline)==utc(original_retry)
    assert utc(target.next_action_at)==utc(due)

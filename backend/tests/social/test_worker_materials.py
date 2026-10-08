"""Execute the real material boundary with explicit fake grants and objects."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from social.connections.crypto import CredentialCipher
from social.connections.models import SocialCredential
from social.contracts import InspectedAsset, ResolvedPostPayload, canonical_hash
from social.models import SocialAccount, SocialControls, SocialMediaAsset, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget, SocialPublishAttempt
from social.worker.materials import CredentialLoadRequest, CredentialMaterialLoader, MaterialUnavailable, VerifiedMediaAccess
from social.worker.repository import Claim
from test_connections_support import config, db, graph, svc, start, complete, select_asset, PAGE
from test_media_support import FakeStorage, ENDPOINT, png


@pytest.fixture
def admitted(db, config, graph):
    service = svc(db, config, graph)
    _, state = start(service)
    completed = complete(service, state)
    select_asset(service, UUID(completed['flow_id']))
    account = db.scalar(select(SocialAccount).where(SocialAccount.platform == 'facebook'))
    credential = db.get(SocialCredential, account.credential_id)
    now = datetime.now(timezone.utc)
    token, post_id, revision_id, pub_id, target_id, operation_id = [uuid4() for _ in range(6)]
    db.get(SocialControls, 1).publishing_enabled = True
    db.add(SocialPost(id=post_id, title='Fake', content_type='announcement', editorial_state='approved'))
    db.flush()
    db.add(SocialPostRevision(id=revision_id, post_id=post_id, revision_no=1, document={}, evidence_snapshot={}, content_hash='a'*64))
    db.flush()
    db.add(SocialPublication(id=pub_id, post_id=post_id, revision_id=revision_id, approved_by=uuid4(), approved_at=now, approved_hash='a'*64))
    payload = ResolvedPostPayload(account_id=account.id, platform=account.platform, api_product=account.api_product,
        external_account_id=account.external_account_id, format='text', text='Fake', evidence_hash='b'*64, content_hash='c'*64)
    payload = payload.model_copy(update={'content_hash':canonical_hash(payload.model_dump(mode='json',exclude={'content_hash'}))})
    db.flush()
    target = SocialPostTarget(id=target_id, publication_id=pub_id, account_id=account.id, resolved_payload=payload.model_dump(mode='json'),
        payload_hash=payload.content_hash, capability_version='social-v1', state='dispatching', lease_epoch=1,
        lease_token=token, lease_expires_at=now+timedelta(minutes=2))
    db.add(target); db.flush()
    account.publishing_enabled=True
    account.publish_lease_target_id=target_id; account.publish_lease_token=token; account.publish_lease_expires_at=now+timedelta(minutes=2)
    db.add(SocialPublishAttempt(id=uuid4(), target_id=target_id, sequence=1, operation_id=operation_id, operation='publish',
        request_fingerprint='d'*64, lease_epoch=1, outcome='intent', receipt={'intent': {'mutating': True}}))
    db.commit()
    request=CredentialLoadRequest(Claim(str(target_id),str(account.id),str(pub_id),str(token),1,'queued'), payload,
        operation_id, credential.id, credential.version, True)
    loader=CredentialMaterialLoader(db.bind, CredentialCipher(config.active_key_version, config.encryption_keys))
    return loader, request, account.id, credential.id


def test_real_credential_loader_returns_ephemeral_bound_material(admitted):
    loader, request, _, _ = admitted
    material=asyncio.run(loader(request))
    assert material.page_access_token == PAGE and material.page_id == '901'
    assert material.credential_id == request.credential_id
    assert PAGE not in repr(material)


@pytest.mark.parametrize('change', ['token','epoch','target','publication','operation','identity','version','missing_id','boolean_version','payload'])
def test_loader_rejects_forged_or_stale_admission(admitted, change):
    loader, request, _, _ = admitted
    if change in {'token','epoch','target','publication'}:
        field={'token':'token','epoch':'epoch','target':'target_id','publication':'publication_id'}[change]
        value=2 if change=='epoch' else str(uuid4())
        request=replace(request,claim=replace(request.claim, **{field:value}))
    elif change=='operation': request=replace(request,operation_id=uuid4())
    elif change=='identity': request=replace(request,credential_id=uuid4())
    elif change=='missing_id': request=replace(request,credential_id=None)
    elif change=='boolean_version': request=replace(request,credential_version=True)
    elif change=='version': request=replace(request,credential_version=2)
    else: request=replace(request,payload=request.payload.model_copy(update={'text':'Tampered'}))
    with pytest.raises(MaterialUnavailable): asyncio.run(loader(request))


@pytest.mark.parametrize('change',['revoked','parent_revoked','expired','parent_expired','refresh','expired_refresh','ciphertext','scope','page_id','admission','lease','disconnected'])
def test_loader_rechecks_real_credential_and_claim_state(admitted, db, change):
    loader, request, account_id, credential_id=admitted
    credential=db.get(SocialCredential,credential_id); account=db.get(SocialAccount,account_id)
    parent=db.get(SocialCredential,credential.parent_credential_id); now=datetime.now(timezone.utc)
    if change=='revoked': credential.revoked_at=now
    elif change=='parent_revoked': parent.revoked_at=now
    elif change=='expired': credential.access_expires_at=now-timedelta(seconds=1)
    elif change=='parent_expired': parent.data_access_expires_at=now-timedelta(seconds=1)
    elif change in {'refresh','expired_refresh'}:
        parent.refresh_lease_token=uuid4(); parent.refresh_lease_expires_at=now+timedelta(seconds=-1 if change=='expired_refresh' else 60)
    elif change=='ciphertext': credential.encrypted_bundle=b'fake-unreadable'
    elif change=='scope': account.granted_scopes=[]
    elif change=='page_id':
        bundle=loader.cipher.decrypt(credential.id,'facebook_page',credential.key_version,credential.encrypted_bundle)
        bundle['page_id']='902'; credential.key_version,credential.encrypted_bundle=loader.cipher.encrypt(credential.id,'facebook_page',bundle)
    elif change=='admission': account.publish_lease_token=uuid4()
    elif change=='lease': db.get(SocialPostTarget, UUID(request.claim.target_id)).lease_expires_at=now-timedelta(seconds=1)
    elif change=='disconnected': account.connection_state='disconnected'
    db.commit()
    with pytest.raises(MaterialUnavailable) as error: asyncio.run(loader(request))
    assert PAGE not in str(error.value)


@pytest.fixture
def final_media(db):
    storage=FakeStorage(); content=png(); sha=hashlib.sha256(content).hexdigest(); identity=uuid4()
    storage.objects['final/private']=(content,'image/png',sha)
    snapshot=storage.head('final/private')
    db.add(SocialMediaAsset(id=identity,storage_provider='r2',bucket=storage.bucket,storage_key='final/private',original_filename='fixture.png',
        mime_type='image/png',byte_size=len(content),sha256=sha,width=64,height=32,state='ready',created_by=uuid4(),
        codec_metadata={'storage_etag':snapshot.etag,'storage_version':snapshot.version}))
    db.commit()
    asset=InspectedAsset(asset_id=identity,sha256=sha,mime_type='image/png',byte_size=len(content),width=64,height=32)
    access=VerifiedMediaAccess(db.bind,storage,allowed_origin=urlsplit(ENDPOINT).hostname,assets=(asset,))
    return access,storage,asset,content


def test_final_bytes_are_checksum_and_authorization_verified(final_media):
    access,_,asset,content=final_media
    assert asyncio.run(access.read_bytes(asset,8_000_000)) == content
    with pytest.raises(MaterialUnavailable): asyncio.run(access.read_bytes(asset.model_copy(update={'asset_id':uuid4()}),8_000_000))


@pytest.mark.parametrize('limit',[None,True,0,-1,float('nan'),float('inf'),8_000_001])
def test_direct_material_byte_limit_rejects_hostile_numbers(final_media,limit):
    access,_,asset,_=final_media
    with pytest.raises(MaterialUnavailable): asyncio.run(access.read_bytes(asset,limit))


def test_changed_final_bytes_cannot_be_used(final_media):
    access,storage,asset,_=final_media
    storage.objects['final/private']=(b'evil','image/png',asset.sha256)
    with pytest.raises(MaterialUnavailable): asyncio.run(access.read_bytes(asset,8_000_000))


@pytest.mark.parametrize('change',['expired','no_expiry','foreign_origin','wrong_version'])
def test_provider_fetch_never_accepts_unproven_or_foreign_access(final_media,change):
    access,storage,asset,_=final_media
    now=datetime.now(timezone.utc)
    expiry=now+timedelta(seconds=300)
    url=ENDPOINT+'/media-test/final/private?fake=sensitive'
    if change=='expired': expiry=now-timedelta(seconds=1)
    if change=='no_expiry': expiry=None
    if change=='foreign_origin': url='https://attacker.example/fake'
    def preview(*args):
        if change=='wrong_version': storage.objects['final/private']=(b'evil','image/png',asset.sha256)
        return SimpleNamespace(url=url,expires_at=expiry)
    storage.preview=preview
    with pytest.raises(MaterialUnavailable): asyncio.run(access.provider_fetch_url(asset,120))


def test_fresh_scoped_fetch_url_has_ephemeral_material(final_media):
    access,storage,asset,_=final_media
    storage.preview=lambda *args: SimpleNamespace(url=ENDPOINT+'/media-test/final/private?fake=sensitive',expires_at=datetime.now(timezone.utc)+timedelta(seconds=300))
    result=asyncio.run(access.provider_fetch_url(asset,120))
    assert result.asset_id==asset.asset_id and result.sha256==asset.sha256
    assert 'sensitive' not in repr(result)

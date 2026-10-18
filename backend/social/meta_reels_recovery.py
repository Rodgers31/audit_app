"""Audited two-admin authority for existing Meta Reels; never provider proof.

See META_REELS_PUBLIC_OUTCOME.md. This command checks binding, custody and
independent human authority; it never fetches URLs, observes pixels or sends.
"""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4
import re

from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import or_, select, text

from .adapters.common import caption
from .adapters.meta_http import remote_id
from .contracts import Hash, PositiveVersion, PostDocument, Reason, ResolvedPostPayload, StrictModel, canonical_hash
from .models import (SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls,
                     SocialMediaAsset, SocialPostRevision, SocialPostTarget, SocialPublication, SocialPublishAttempt)
from .service import SocialError, SocialService, iso, utc
from .validation import resolve_fields

CONTRACT = 'meta-reels-two-admin-public-v1'
PROPOSED = 'meta.reels_public_proof_proposed'
ADMITTED = 'meta.reels_public_proof_admitted'
PRODUCTS = {'facebook':'facebook_pages', 'instagram':'instagram_graph_facebook_login'}
Identity = Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9]{1,64}$')]
Narrative = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=30, max_length=1000)]


def raw_input(value):
    if isinstance(value, BaseModel):
        value = dict(value)
    if isinstance(value, dict):
        return {key: raw_input(item) for key, item in value.items()}
    if isinstance(value, (tuple,list)):
        return [raw_input(item) for item in value]
    return value


class ReelObservation(StrictModel):
    platform: Literal['facebook','instagram']
    api_product: Literal['facebook_pages','instagram_graph_facebook_login']
    method: Literal['anonymous_browser']
    visibility: Literal['public']
    observed_at: datetime
    capture_sha256: Hash
    custody_reference: UUID
    identity_capture_sha256: Hash
    identity_custody_reference: UUID
    external_account_id: Identity
    remote_id: Identity
    remote_url: Annotated[str, StringConstraints(strict=True, max_length=256)]
    text: Annotated[str, StringConstraints(strict=True, max_length=20000)]
    asset_sha256: Hash
    identity_basis: Narrative
    media_comparison: Narrative

    @model_validator(mode='after')
    def exact_product_url(self):
        if self.api_product!=PRODUCTS[self.platform]:
            raise ValueError('Observation identifies a different Meta product')
        if any(c.isspace() or ord(c)<32 or ord(c)==127 for c in self.remote_url):
            raise ValueError('Use the exact canonical Reel permalink')
        parsed = urlsplit(self.remote_url)
        if (parsed.scheme!='https' or parsed.netloc not in {self.platform+'.com','www.'+self.platform+'.com'}
                or parsed.query or parsed.fragment):
            raise ValueError('Use the exact canonical Reel permalink')
        pattern = r'/reel/'+re.escape(self.remote_id)+r'/?' if self.platform=='facebook' else r'/reel/[A-Za-z0-9_-]{1,64}/'
        if not re.fullmatch(pattern,parsed.path):
            raise ValueError('Permalink must identify the exact Reel product')
        if self.capture_sha256==self.identity_capture_sha256 or self.custody_reference==self.identity_custody_reference:
            raise ValueError('Public and owner identity captures need separate custody')
        return self


class ProposeReelProof(StrictModel):
    expected_publication_version: PositiveVersion
    binding_hash: Hash
    observation: ReelObservation
    reason: Reason


class RecordExistingReel(StrictModel):
    expected_publication_version: PositiveVersion
    proof_id: UUID
    observation: ReelObservation
    reason: Reason


class ReelProofContext(StrictModel):
    target_id: UUID
    publication_id: UUID
    publication_version: PositiveVersion
    revision_id: UUID
    approved_hash: Hash
    payload_hash: Hash
    account_id: UUID
    platform: Literal['facebook','instagram']
    api_product: str
    external_account_id: Identity
    binding_hash: Hash
    caption: str
    asset_sha256: Hash
    known_remote_id: Identity | None
    state: str


class ReelProofDTO(StrictModel):
    proof_id: UUID
    target_id: UUID
    expires_at: datetime
    binding_hash: Hash
    state: Literal['awaiting_independent_review']


class ReelSettlementDTO(StrictModel):
    target_id: UUID
    proof_id: UUID
    remote_id: Identity
    remote_url: str
    publication_version: PositiveVersion
    state: Literal['published']


class MetaReelsRecoveryService(SocialService):
    _operator_command = False

    def command(self, *, actor, route, key, body, request_id, action, status=200):
        if self.db.in_transaction() or any(type(v) is not UUID for v in (actor,key,request_id)):
            raise SocialError('OPERATOR_COMMAND_REQUIRED','Use the authenticated isolated operator command.',403)
        self.actor,self.request_id = actor,request_id
        fingerprint = canonical_hash(body)
        with self.db.begin():
            controls = self.db.scalar(select(SocialControls).where(SocialControls.id==1).with_for_update().execution_options(populate_existing=True))
            if controls is None:
                raise SocialError('SOCIAL_SCHEMA_UNAVAILABLE','Recovery controls are unavailable.',503)
            old = self.db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.actor_key==str(actor),
                SocialCommandReceipt.route_key==route, SocialCommandReceipt.idempotency_key==key))
            if old:
                if old.request_hash!=fingerprint:
                    raise SocialError('IDEMPOTENCY_CONFLICT','Command key was used with different input.')
                return old.http_status,old.response
            before = set(self.db.new)
            self._operator_command = True
            try:
                result = action()
            finally:
                self._operator_command = False
            receipt = SocialCommandReceipt(id=uuid4(),actor_key=str(actor),route_key=route,idempotency_key=key,
                request_hash=fingerprint,http_status=status,response=result,resource_id=UUID(result['target_id']),
                expires_at=self.now()+timedelta(days=30))
            self.db.add(receipt)
            new = [obj for obj in self.db.new if obj not in before and isinstance(obj,(SocialAuditEvent,SocialCommandReceipt))]
            expected = [(obj,{col.name:getattr(obj,col.name) for col in obj.__table__.columns if getattr(obj,col.name) is not None}) for obj in new]
            self.db.flush()
            if self.db.bind.dialect.name=='postgresql':
                self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            for obj,values in expected:
                saved = self.db.execute(select(obj.__table__).where(obj.__table__.c.id==obj.id)).mappings().one_or_none()
                def primitive(value):
                    return str(value) if isinstance(value,UUID) else iso(value) if isinstance(value,datetime) else value
                if saved is None or any(canonical_hash(primitive(saved[k]))!=canonical_hash(primitive(v)) for k,v in values.items()):
                    raise SocialError('RECOVERY_PERSISTENCE_FAILED','Recovery evidence was not stored as required.',503)
            if result['state']=='published':
                self._verify_settlement()
        return status,result

    def _load(self, target_id, version=None, *, locked=False):
        initial = self.db.get(SocialPostTarget,target_id)
        if initial is None:
            raise SocialError('NOT_FOUND','Destination was not found.',404)
        def read(model,identity):
            statement = select(model).where(model.id==identity).execution_options(populate_existing=True)
            return self.db.scalar(statement.with_for_update() if locked else statement)
        account = read(SocialAccount,initial.account_id)
        publication = read(SocialPublication,initial.publication_id)
        target = read(SocialPostTarget,target_id)
        revision = read(SocialPostRevision,publication.revision_id) if publication else None
        if version is not None and publication and publication.version!=version:
            raise SocialError('VERSION_CONFLICT','Publication changed. Collect fresh evidence.')
        try:
            payload = ResolvedPostPayload.model_validate(target.resolved_payload)
            document = PostDocument.model_validate(revision.document)
            selected = [item for item in document.targets if item.account_id==account.id]
            if (payload.platform not in PRODUCTS or account.platform!=payload.platform
                    or payload.api_product!=PRODUCTS[payload.platform] or account.api_product!=payload.api_product
                    or payload.external_account_id!=account.external_account_id or payload.account_id!=account.id
                    or payload.format!='reel' or len(payload.assets)!=1 or len(selected)!=1 or selected[0].format!='reel'
                    or payload.content_hash!=target.payload_hash
                    or canonical_hash(payload.model_dump(mode='json',exclude={'content_hash'}))!=target.payload_hash
                    or publication.post_id!=revision.post_id or publication.approved_hash!=revision.content_hash
                    or canonical_hash({'document':revision.document,'evidence_snapshot':revision.evidence_snapshot})!=publication.approved_hash
                    or payload.evidence_hash!=canonical_hash(revision.evidence_snapshot)):
                raise ValueError('Approved identity differs')
            remote_id(payload.external_account_id)
            fields = resolve_fields(document,selected[0])
            if (payload.text!=fields['text'] or payload.link!=fields['link'] or list(payload.hashtags)!=fields['hashtags']
                    or len(fields['media'])!=1 or fields['media'][0]['asset_id']!=str(payload.assets[0].asset_id)):
                raise ValueError('Approved content differs')
            from .adapters.facebook_reels import checkpoint as facebook_checkpoint
            from .adapters.common import Checkpoint
            from .adapters.meta_validation import reel_errors
            if reel_errors(payload) or any(a.caption_asset_id is not None or a.caption_sha256 is not None for a in payload.assets):
                raise ValueError('Unsupported Reel media')
            state = facebook_checkpoint(payload,target.checkpoint) if payload.platform=='facebook' else Checkpoint.model_validate(target.checkpoint)
            if payload.platform=='instagram' and (state.adapter!='instagram_facebook_login-v1'
                    or state.account_id!=account.id or state.external_account_id!=payload.external_account_id or state.content_hash!=payload.content_hash
                    or state.phase not in {'publication_uncertain','media_created'} or state.container_id is None
                    or (state.media_id is not None)!=(state.phase=='media_created')
                    or state.media_id==state.container_id or any(getattr(state,k) is not None for k in ('photo_id','photo_post_id','post_id'))):
                raise ValueError('Unknown Instagram publication checkpoint')
            if state is None or payload.platform=='facebook' and state.phase not in {'publication_uncertain','publication_accepted'}:
                raise ValueError('No recorded Reel publication')
            if not isinstance(target.remote_refs,dict):
                raise ValueError('Malformed remote references')
            key = 'video_id' if payload.platform=='facebook' else 'media_id'
            allowed_refs = {'video_id'} if payload.platform=='facebook' else {'container_id','media_id'}
            if set(target.remote_refs)-allowed_refs or any(remote_id(v)!=getattr(state,k,None) for k,v in target.remote_refs.items()):
                raise ValueError('Remote references differ from their checkpoint')
            identities = [target.primary_remote_id,target.remote_refs.get(key),getattr(state,key,None)]
            known = {remote_id(item) for item in identities if item is not None}
            if len(known)>1:
                raise ValueError('Contradictory retained remote identity')
            asset = read(SocialMediaAsset,payload.assets[0].asset_id)
            approved = payload.assets[0]
            if (asset is None or asset.state!='ready' or asset.deleted_at is not None
                    or (asset.sha256,asset.mime_type,asset.byte_size,asset.width,asset.height,asset.duration_ms)
                    != (approved.sha256,approved.mime_type,approved.byte_size,approved.width,approved.height,approved.duration_ms)
                    or asset.frame_rate is None or int(asset.frame_rate*1000)!=approved.frame_rate_milli_fps):
                raise ValueError('Approved video custody changed')
        except (ValueError,TypeError,AttributeError,KeyError):
            raise SocialError('PROOF_BINDING_INVALID','Approved Meta Reel, source custody or retained identities are inconsistent.') from None
        if target.state not in {'processing','reconciling','outcome_unknown'} or target.submit_count<1:
            raise SocialError('RECONCILIATION_REQUIRED','Only an attempted unresolved Reel can be recorded.')
        dispatch = self.db.scalar(select(SocialPublishAttempt).where(SocialPublishAttempt.target_id==target.id,
            SocialPublishAttempt.operation=='publish',SocialPublishAttempt.dispatch_started_at.is_not(None))
            .order_by(SocialPublishAttempt.sequence.desc()).limit(1))
        intent = dispatch.receipt.get('intent') if dispatch and isinstance(dispatch.receipt,dict) else None
        if (not isinstance(intent,dict) or intent.get('publication_capable') is not True or intent.get('mutating') is not True
                or intent.get('safe_replay_class')!='requires_reconciliation'):
            raise SocialError('RECONCILIATION_REQUIRED','A durable public dispatch permit is required.')
        if (any(getattr(target,key) is not None for key in ('lease_owner','lease_token','lease_expires_at'))
                or any(getattr(account,key) is not None for key in ('publish_lease_target_id','publish_lease_token','publish_lease_expires_at'))
                or self.db.scalar(select(SocialPublishAttempt.id).where(SocialPublishAttempt.target_id==target.id,SocialPublishAttempt.completed_at.is_(None)).limit(1))):
            raise SocialError('RECOVERY_BUSY','Drain worker ownership and complete retained intents before recovery.')
        binding = dict(target_id=str(target.id),account_id=str(account.id),publication_id=str(publication.id),revision_id=str(revision.id),
            platform=payload.platform,api_product=payload.api_product,external_account_id=payload.external_account_id,
            payload_hash=target.payload_hash,approved_hash=publication.approved_hash,publication_version=publication.version,
            state=target.state,lease_epoch=target.lease_epoch,checkpoint=target.checkpoint,remote_refs=target.remote_refs,
            remote_id=target.primary_remote_id,remote_url=target.remote_url,submit_count=target.submit_count,
            updated_at=iso(target.updated_at),dispatch_operation_id=str(dispatch.operation_id))
        return account,publication,target,payload,binding,next(iter(known),None)

    def context(self,target_id):
        account,pub,target,payload,binding,known = self._load(target_id)
        return dict(target_id=str(target.id),publication_id=str(pub.id),publication_version=pub.version,revision_id=str(pub.revision_id),
            approved_hash=pub.approved_hash,payload_hash=target.payload_hash,account_id=str(account.id),platform=payload.platform,
            api_product=payload.api_product,external_account_id=payload.external_account_id,binding_hash=canonical_hash(binding),
            caption=caption(payload),asset_sha256=payload.assets[0].sha256,known_remote_id=known,state=target.state)

    def _observation(self,observation,account,target,payload,known,*,new_packet=True):
        if not self.now()-timedelta(minutes=30)<=observation.observed_at<=self.now():
            raise SocialError('PROOF_EXPIRED','Observations must be fresh within thirty minutes of database time.')
        if (observation.platform!=payload.platform or observation.api_product!=payload.api_product or observation.external_account_id!=account.external_account_id
                or known is not None and observation.remote_id!=known or observation.text!=caption(payload)
                or observation.asset_sha256!=payload.assets[0].sha256
                or target.remote_url is not None and observation.remote_url!=target.remote_url
                or payload.platform=='instagram' and observation.remote_id==target.checkpoint.get('container_id')):
            raise SocialError('PROOF_MISMATCH','Compare exact approved video, caption, owner and retained publication identity.')
        key = 'video_id' if payload.platform=='facebook' else 'media_id'
        duplicate = self.db.scalar(select(SocialPostTarget.id).join(SocialAccount,SocialAccount.id==SocialPostTarget.account_id).where(
            SocialAccount.platform==payload.platform,SocialAccount.external_account_id==payload.external_account_id,SocialPostTarget.id!=target.id,
            or_(SocialPostTarget.primary_remote_id==observation.remote_id,SocialPostTarget.remote_refs[key].as_string()==observation.remote_id,
                SocialPostTarget.checkpoint[key].as_string()==observation.remote_id)).limit(1))
        if duplicate:
            raise SocialError('PROOF_REPLAY','This retained remote identity belongs to another target.')
        if not new_packet:
            return
        hashes = (observation.capture_sha256,observation.identity_capture_sha256)
        refs = tuple(str(value) for value in (observation.custody_reference,observation.identity_custody_reference))
        used = self.db.scalar(select(SocialAuditEvent.id).where(or_(
            SocialAuditEvent.details['observation']['capture_sha256'].as_string().in_(hashes),
            SocialAuditEvent.details['observation']['identity_capture_sha256'].as_string().in_(hashes),
            SocialAuditEvent.details['observation']['custody_reference'].as_string().in_(refs),
            SocialAuditEvent.details['observation']['identity_custody_reference'].as_string().in_(refs))).limit(1))
        if used:
            raise SocialError('PROOF_REPLAY','Capture packets and custody records cannot be reused.')

    def _require_command(self):
        if not self._operator_command or not self.db.in_transaction():
            raise SocialError('OPERATOR_COMMAND_REQUIRED','Use the authenticated idempotent operator command.',403)

    def propose(self,target_id,body):
        self._require_command()
        body = ProposeReelProof.model_validate(raw_input(body))
        account,pub,target,payload,binding,known = self._load(target_id,body.expected_publication_version,locked=True)
        if body.binding_hash!=canonical_hash(binding):
            raise SocialError('VERSION_CONFLICT','Target state changed. Collect a fresh binding.')
        self._observation(body.observation,account,target,payload,known)
        identity,expiry = uuid4(),body.observation.observed_at+timedelta(minutes=30)
        self.db.add(SocialAuditEvent(id=identity,post_id=pub.post_id,target_id=target.id,account_id=account.id,actor_kind='admin',
            actor_id=self.actor,request_id=str(self.request_id),action=PROPOSED,reason=body.reason,previous_state=target.state,new_state=target.state,
            details={'contract':CONTRACT,'binding':binding,'binding_hash':body.binding_hash,'expires_at':iso(expiry),'observation':body.observation.model_dump(mode='json')}))
        return dict(proof_id=str(identity),target_id=str(target.id),expires_at=iso(expiry),binding_hash=body.binding_hash,state='awaiting_independent_review')

    def record_existing(self,target_id,body):
        self._require_command()
        body = RecordExistingReel.model_validate(raw_input(body))
        account,pub,target,payload,binding,known = self._load(target_id,body.expected_publication_version,locked=True)
        proposal = self.db.get(SocialAuditEvent,body.proof_id)
        if (proposal is None or proposal.action!=PROPOSED or proposal.target_id!=target.id or proposal.account_id!=account.id or proposal.post_id!=pub.post_id):
            raise SocialError('PROOF_MISMATCH','Proposal does not belong to this exact Reel.')
        if proposal.actor_kind!='admin' or proposal.actor_id is None or proposal.actor_id==self.actor:
            raise SocialError('INDEPENDENT_REVIEW_REQUIRED','A different administrator must independently inspect and admit the Reel.',403)
        try:
            first = ReelObservation.model_validate(proposal.details['observation'])
            expiry = datetime.fromisoformat(proposal.details['expires_at'].replace('Z','+00:00'))
            if (proposal.details['contract']!=CONTRACT or expiry.tzinfo is None or self.now()>=expiry
                    or expiry!=first.observed_at+timedelta(minutes=30)
                    or proposal.details['binding_hash']!=canonical_hash(binding) or canonical_hash(proposal.details['binding'])!=canonical_hash(binding)):
                raise ValueError('Stale proposal')
        except (ValueError,TypeError,KeyError):
            raise SocialError('PROOF_EXPIRED','Proposal is invalid or stale. Collect fresh independent evidence.') from None
        self._observation(first,account,target,payload,known,new_packet=False)
        self._observation(body.observation,account,target,payload,known)
        if first.remote_id!=body.observation.remote_id or first.remote_url!=body.observation.remote_url:
            raise SocialError('PROOF_MISMATCH','Independent observations must identify the same exact Reel.')
        now,previous = self.now(),target.state
        target.state,target.visibility_state,target.confirmation_kind = 'published','public',CONTRACT
        target.primary_remote_id,target.remote_url,target.published_at = body.observation.remote_id,body.observation.remote_url,now
        target.error_code=target.safe_error_message=target.next_action=target.next_action_at=None
        target.updated_at=now
        if account.hold_reason=='RECONCILIATION_REQUIRED:'+str(target.id):
            account.hold_reason,account.updated_at=None,now
        pub.version,pub.updated_at=pub.version+1,now
        self.db.add(SocialAuditEvent(id=uuid4(),post_id=pub.post_id,target_id=target.id,account_id=account.id,actor_kind='admin',actor_id=self.actor,
            request_id=str(self.request_id),action=ADMITTED,reason=body.reason,previous_state=previous,new_state='published',
            details={'contract':CONTRACT,'proof_id':str(proposal.id),'binding':binding,'observation':body.observation.model_dump(mode='json')}))
        self._settlement = dict(target_id=target.id,remote_id=target.primary_remote_id,url=target.remote_url,when=iso(now),pub_id=pub.id,
            version=pub.version,account_id=account.id,hold=account.hold_reason,checkpoint=canonical_hash(target.checkpoint),refs=canonical_hash(target.remote_refs),
            count=target.submit_count)
        return dict(target_id=str(target.id),proof_id=str(proposal.id),remote_id=target.primary_remote_id,remote_url=target.remote_url,
            publication_version=pub.version,state='published')

    def _verify_settlement(self):
        expected=self._settlement
        self.db.expire_all()
        target=self.db.get(SocialPostTarget,expected['target_id']);pub=self.db.get(SocialPublication,expected['pub_id']);account=self.db.get(SocialAccount,expected['account_id'])
        if (target is None or pub is None or account is None or target.state!='published' or target.visibility_state!='public'
                or target.confirmation_kind!=CONTRACT or target.primary_remote_id!=expected['remote_id'] or target.remote_url!=expected['url']
                or iso(target.published_at)!=expected['when'] or target.error_code is not None or target.safe_error_message is not None
                or target.next_action is not None or target.next_action_at is not None or pub.version!=expected['version']
                or account.hold_reason!=expected['hold'] or canonical_hash(target.checkpoint)!=expected['checkpoint']
                or canonical_hash(target.remote_refs)!=expected['refs'] or target.submit_count!=expected['count']):
            raise SocialError('RECOVERY_PERSISTENCE_FAILED','Settlement values were not stored as required.',503)

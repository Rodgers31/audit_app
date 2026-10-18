"""Provider credentials loaded only against a committed, unexpired worker intent."""
from dataclasses import replace
from datetime import datetime, timezone
import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .contracts import ResolvedPostPayload, canonical_hash
from .models import SocialAccount, SocialControls, SocialPostTarget, SocialPublication, SocialPublishAttempt
from .native_admission import NativeCapabilityAdmission
from .service import utc
from .worker.materials import CredentialLoadRequest, MaterialUnavailable, WorkerCredentialMaterial
from .platform_connections.models import PlatformCredential
from .platform_budget import SocialPlatformBudget


class PlatformCredentialMaterialLoader:
    def __init__(self, engine, cipher, configurations, *, tiktok_verified_origins=()):
        self.engine, self.cipher, self.configurations = engine, cipher, configurations
        self.tiktok_verified_origins = tiktok_verified_origins

    async def __call__(self, request):
        import asyncio
        return await asyncio.to_thread(self._load, request)

    def _load(self, request):
        from .worker.repository import Claim
        if (not isinstance(request, CredentialLoadRequest) or not isinstance(request.claim, Claim)
                or not isinstance(request.payload, ResolvedPostPayload) or type(request.mutating) is not bool
                or not isinstance(request.credential_id, UUID) or not isinstance(request.operation_id, UUID)
                or type(request.credential_version) is not int or request.credential_version < 1):
            raise MaterialUnavailable('CREDENTIAL_REQUEST_INVALID')
        claim, payload = request.claim, request.payload
        try:
            ids = [UUID(value) for value in (claim.target_id,claim.account_id,claim.publication_id,claim.token)]
        except (ValueError, TypeError, AttributeError):
            raise MaterialUnavailable('CREDENTIAL_REQUEST_INVALID') from None
        with Session(self.engine) as db, db.begin():
            db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
            account = db.scalar(select(SocialAccount).where(SocialAccount.id == ids[1]).with_for_update())
            publication = db.scalar(select(SocialPublication).where(SocialPublication.id == ids[2]).with_for_update())
            target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.id == ids[0]).with_for_update())
            now = utc(db.scalar(select(func.clock_timestamp()))) if db.bind.dialect.name == 'postgresql' else datetime.now(timezone.utc)
            if (not account or not publication or not target or target.account_id != account.id
                    or target.publication_id != publication.id or str(target.lease_token) != claim.token
                    or target.lease_epoch != claim.epoch or not target.lease_expires_at or utc(target.lease_expires_at) <= now):
                raise MaterialUnavailable('CREDENTIAL_CLAIM_FENCED')
            if (payload.account_id != account.id or payload.platform != account.platform
                    or payload.api_product != account.api_product or payload.external_account_id != account.external_account_id
                    or account.connection_state != 'connected'
                    or (payload.platform,payload.api_product) not in {('threads','threads'),('x','x_api_v2'),('tiktok','tiktok_accounts_api')}):
                raise MaterialUnavailable('CREDENTIAL_ACCOUNT_CHANGED')
            if (ResolvedPostPayload.model_validate(target.resolved_payload) != payload or target.payload_hash != payload.content_hash
                    or canonical_hash(payload.model_dump(mode='json',exclude={'content_hash'})) != payload.content_hash):
                raise MaterialUnavailable('CREDENTIAL_PAYLOAD_CHANGED')
            attempt = db.scalar(select(SocialPublishAttempt).where(SocialPublishAttempt.target_id == target.id,
                SocialPublishAttempt.operation_id == request.operation_id,SocialPublishAttempt.lease_epoch == claim.epoch,
                SocialPublishAttempt.completed_at.is_(None)))
            if attempt is None or attempt.receipt.get('intent',{}).get('mutating') is not request.mutating:
                raise MaterialUnavailable('CREDENTIAL_PERMISSION_MISSING')
            if request.mutating and (str(account.publish_lease_token) != claim.token or account.publish_lease_target_id != target.id
                    or not account.publish_lease_expires_at or utc(account.publish_lease_expires_at) <= now or not account.publishing_enabled):
                raise MaterialUnavailable('CREDENTIAL_ADMISSION_LOST')
            if account.publish_lease_target_id is not None and account.publish_lease_target_id != target.id:
                raise MaterialUnavailable('CREDENTIAL_ACCOUNT_BUSY')
            row = db.scalar(select(PlatformCredential).where(PlatformCredential.account_id == account.id).with_for_update())
            if (not row or row.id != request.credential_id or row.version != request.credential_version or row.platform != payload.platform
                    or row.revoked_at is not None or row.refresh_claim is not None or utc(row.access_expires_at) <= now
                    or row.refresh_expires_at is not None and utc(row.refresh_expires_at) <= now
                    or row.data_access_expires_at is not None and utc(row.data_access_expires_at) <= now):
                raise MaterialUnavailable('CREDENTIAL_CHANGED')
            try:
                bundle = self.cipher.decrypt(row.id, 'platform:'+payload.platform+':credential',row.key_version,row.encrypted_bundle)
                token, subject, scopes = bundle['access_token'],bundle.get('subject',bundle.get('open_id')),bundle['scopes']
                if (not isinstance(token,str) or not 1 <= len(token) <= 16384 or any(ord(c)<33 or ord(c)>126 for c in token)
                        or subject != payload.external_account_id or not isinstance(scopes,list)
                        or len(scopes)>200 or any(not isinstance(s,str) or not re.fullmatch(r'[a-z_.]{1,100}',s) for s in scopes)
                        or set(scopes) != set(account.granted_scopes)):
                    raise ValueError()
                admission = NativeCapabilityAdmission.from_snapshot(account.capability_snapshot)
            except Exception:
                raise MaterialUnavailable('CREDENTIAL_MATERIAL_INVALID') from None
            material = WorkerCredentialMaterial(account.id,row.id,row.version,payload.platform,payload.api_product,
                subject,subject,token,tuple(scopes),utc(row.access_expires_at),utc(row.data_access_expires_at) if row.data_access_expires_at else None,admission)
            if payload.platform == 'x':
                budget=db.scalar(select(SocialPlatformBudget).where(SocialPlatformBudget.account_id == account.id).with_for_update())
                if (not budget or budget.enabled is not True or budget.access_verified is not True
                        or attempt.cost_reservation_state != 'reserved' or type(attempt.estimated_cost_microusd) is not int
                        or attempt.estimated_cost_microusd <= 0 or budget.reserved_microusd < attempt.estimated_cost_microusd
                        or budget.limit_microusd < budget.reserved_microusd + budget.spent_microusd):
                    raise MaterialUnavailable('BUDGET_EXHAUSTED')
                material=replace(material,x_access_verified=True,
                    x_budget_remaining_microusd=budget.limit_microusd-budget.spent_microusd-budget.reserved_microusd+attempt.estimated_cost_microusd,
                    x_reserved_cost_microusd=attempt.estimated_cost_microusd,x_reservation_operation_id=request.operation_id)
            elif payload.platform == 'tiktok':
                config=self.configurations.get('tiktok')
                material=replace(material,tiktok_product_approved=bool(config and config.access_verified is True),
                    tiktok_verified_origins=tuple(self.tiktok_verified_origins))
            return material


class CombinedCredentialLoader:
    def __init__(self, meta, platforms):
        self.meta,self.platforms=meta,platforms
    async def __call__(self,request):
        loader=self.meta if request.payload.platform in {'facebook','instagram'} else self.platforms
        if loader is None:
            raise MaterialUnavailable('CREDENTIAL_LOADER_UNAVAILABLE')
        return await loader(request)

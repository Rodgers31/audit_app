"""Ephemeral, server-only provider material; never persistent delivery data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, TYPE_CHECKING
from uuid import UUID

from ..contracts import InspectedAsset, ResolvedPostPayload, canonical_hash
from ..native_admission import NativeCapabilityAdmission

if TYPE_CHECKING:
    from .repository import Claim


@dataclass(frozen=True)
class WorkerCredentialMaterial:
    account_id: UUID
    credential_id: UUID
    credential_version: int
    platform: str
    api_product: str
    external_account_id: str
    page_id: str
    page_access_token: str = field(repr=False)
    granted_scopes: tuple[str, ...]
    access_expires_at: datetime | None
    data_access_expires_at: datetime | None
    capability_admission: NativeCapabilityAdmission | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ProviderFetchURL:
    url: str = field(repr=False)
    expires_at: datetime
    asset_id: UUID
    sha256: str


class InspectedMediaAccess(Protocol):
    async def read_bytes(self, asset: InspectedAsset, maximum_bytes: int) -> bytes: ...
    async def provider_fetch_url(self, asset: InspectedAsset, minimum_ttl_seconds: int) -> ProviderFetchURL: ...


@dataclass(frozen=True)
class CredentialLoadRequest:
    claim: Claim
    payload: ResolvedPostPayload
    operation_id: UUID
    credential_id: UUID | None
    credential_version: int | None
    mutating: bool


class MaterialUnavailable(ValueError):
    """Contains an allowlisted local code, never raw provider material."""


class CredentialMaterialLoader:
    def __init__(self, engine, cipher):
        self.engine, self.cipher = engine, cipher

    async def __call__(self, request: CredentialLoadRequest) -> WorkerCredentialMaterial:
        import asyncio
        return await asyncio.to_thread(self._load, request)

    def _load(self, request):
        from datetime import timezone
        import re
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session
        from ..connections.models import SocialCredential
        from ..models import SocialAccount, SocialControls, SocialPostTarget, SocialPublication, SocialPublishAttempt
        from ..service import utc

        from .repository import Claim
        if (not isinstance(request, CredentialLoadRequest) or not isinstance(request.claim, Claim)
                or not isinstance(request.payload, ResolvedPostPayload) or type(request.mutating) is not bool
                or type(request.claim.epoch) is not int or request.claim.epoch < 1
                or not isinstance(request.credential_id, UUID)
                or type(request.credential_version) is not int or request.credential_version < 1
                or not isinstance(request.operation_id, UUID)):
            raise MaterialUnavailable('CREDENTIAL_REQUEST_INVALID')
        claim, payload = request.claim, request.payload
        try:
            if any(not isinstance(value, str) or value != str(UUID(value)) for value in
                   (claim.target_id, claim.account_id, claim.publication_id, claim.token)):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise MaterialUnavailable('CREDENTIAL_REQUEST_INVALID') from None
        with Session(self.engine) as db, db.begin():
            # Match command/worker lock order; close before any provider await.
            db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
            account = db.scalar(select(SocialAccount).where(SocialAccount.id == UUID(claim.account_id)).with_for_update())
            publication = db.scalar(select(SocialPublication).where(SocialPublication.id == UUID(claim.publication_id)).with_for_update())
            target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.id == UUID(claim.target_id)).with_for_update())
            now = utc(db.scalar(select(func.clock_timestamp()))) if db.bind.dialect.name == 'postgresql' else datetime.now(timezone.utc)
            if (not account or not publication or not target or str(target.lease_token) != claim.token
                    or target.lease_epoch != claim.epoch or target.lease_expires_at is None
                    or utc(target.lease_expires_at) <= now or target.account_id != account.id
                    or target.publication_id != publication.id):
                raise MaterialUnavailable('CREDENTIAL_CLAIM_FENCED')
            if (payload.account_id != account.id or payload.platform != account.platform
                    or payload.api_product != account.api_product or payload.external_account_id != account.external_account_id
                    or account.credential_id != request.credential_id or account.connection_method != 'facebook_login'
                    or account.connection_state != 'connected'
                    or (account.platform, account.api_product) not in {('facebook', 'facebook_pages'), ('instagram', 'instagram_graph_facebook_login')}):
                raise MaterialUnavailable('CREDENTIAL_ACCOUNT_CHANGED')
            if (ResolvedPostPayload.model_validate(target.resolved_payload) != payload or target.payload_hash != payload.content_hash
                    or canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != payload.content_hash):
                raise MaterialUnavailable('CREDENTIAL_PAYLOAD_CHANGED')
            attempt = db.scalar(select(SocialPublishAttempt).where(
                SocialPublishAttempt.target_id == target.id, SocialPublishAttempt.operation_id == request.operation_id,
                SocialPublishAttempt.lease_epoch == claim.epoch, SocialPublishAttempt.completed_at.is_(None)))
            if attempt is None or attempt.receipt.get('intent', {}).get('mutating') is not request.mutating:
                raise MaterialUnavailable('CREDENTIAL_PERMISSION_MISSING')
            if request.mutating and (str(account.publish_lease_token) != claim.token
                    or account.publish_lease_target_id != target.id or account.publish_lease_expires_at is None
                    or utc(account.publish_lease_expires_at) <= now or not account.publishing_enabled):
                raise MaterialUnavailable('CREDENTIAL_ADMISSION_LOST')
            if account.publish_lease_target_id is not None and account.publish_lease_target_id != target.id:
                raise MaterialUnavailable('CREDENTIAL_ACCOUNT_BUSY')
            credential = db.scalar(select(SocialCredential).where(SocialCredential.id == request.credential_id).with_for_update())
            if (not credential or credential.provider != 'meta' or credential.credential_kind != 'facebook_page'
                    or credential.version != request.credential_version or credential.revoked_at is not None):
                raise MaterialUnavailable('CREDENTIAL_CHANGED')
            parent = db.scalar(select(SocialCredential).where(SocialCredential.id == credential.parent_credential_id).with_for_update())
            if not parent or parent.provider != 'meta' or parent.credential_kind != 'facebook_user' or parent.revoked_at is not None:
                raise MaterialUnavailable('CREDENTIAL_PARENT_UNAVAILABLE')
            for row in (credential, parent):
                if row.refresh_lease_token is not None:
                    # Expiry alone does not establish the refresh stopped.
                    raise MaterialUnavailable('CREDENTIAL_REFRESH_UNSETTLED')
                if any(value is not None and utc(value) <= now for value in (row.access_expires_at, row.data_access_expires_at)):
                    raise MaterialUnavailable('CREDENTIAL_EXPIRED')
            try:
                bundle = self.cipher.decrypt(credential.id, 'facebook_page', credential.key_version, credential.encrypted_bundle)
                grant = self.cipher.decrypt(parent.id, 'facebook_user', parent.key_version, parent.encrypted_bundle)
                if (set(bundle) != {'access_token', 'page_id', 'external_user_id', 'scopes'}
                        or set(grant) != {'access_token', 'external_user_id', 'scopes'}
                        or not isinstance(bundle['access_token'], str) or not 1 <= len(bundle['access_token']) <= 16384
                        or any(ord(c) < 33 or ord(c) > 126 for c in bundle['access_token'])
                        or not isinstance(grant['access_token'], str) or not 1 <= len(grant['access_token']) <= 16384
                        or any(ord(c) < 33 or ord(c) > 126 for c in grant['access_token'])
                        or not isinstance(bundle['page_id'], str) or not re.fullmatch(r'[0-9]{1,64}', bundle['page_id'])
                        or not isinstance(bundle['external_user_id'], str) or not re.fullmatch(r'[0-9]{1,64}', bundle['external_user_id'])
                        or not isinstance(grant['external_user_id'], str) or not re.fullmatch(r'[0-9]{1,64}', grant['external_user_id'])
                        or bundle['external_user_id'] != grant['external_user_id']
                        or any(not isinstance(row['scopes'], list) or len(row['scopes']) > 200
                            or any(not isinstance(s, str) or not re.fullmatch(r'[a-z_]{1,100}', s) for s in row['scopes'])
                            for row in (bundle, grant))
                        or set(account.granted_scopes) != set(bundle['scopes'])
                        or not set(bundle['scopes']) <= set(grant['scopes'])
                        or (payload.platform == 'facebook' and bundle['page_id'] != payload.external_account_id)):
                    raise ValueError()
            except Exception:
                raise MaterialUnavailable('CREDENTIAL_MATERIAL_INVALID') from None
            access_expiry = [utc(row.access_expires_at) for row in (credential, parent) if row.access_expires_at]
            data_expiry = [utc(row.data_access_expires_at) for row in (credential, parent) if row.data_access_expires_at]
            try:
                admission = NativeCapabilityAdmission.from_snapshot(account.capability_snapshot)
            except (ValueError, TypeError):
                # An unreadable publishing gate cannot authorize another write,
                # but authenticated recovery still needs the owned credentials.
                admission = None
            return WorkerCredentialMaterial(account.id, credential.id, credential.version,
                account.platform, account.api_product, account.external_account_id, bundle['page_id'],
                bundle['access_token'], tuple(account.granted_scopes),
                min(access_expiry) if access_expiry else None,
                min(data_expiry) if data_expiry else None, admission)


class VerifiedMediaAccess:
    """A payload-scoped port that only exposes verified immutable final objects."""
    def __init__(self, engine, storage, *, allowed_origin: str, assets=()):
        self.engine, self.storage, self.allowed_origin = engine, storage, allowed_origin
        self.assets = {asset.asset_id: asset for asset in assets}

    def for_payload(self, payload):
        return VerifiedMediaAccess(self.engine, self.storage, allowed_origin=self.allowed_origin, assets=payload.assets)

    def _snapshot(self, asset):
        from sqlalchemy.orm import Session
        from ..models import SocialMediaAsset
        from ..media.storage import ObjectSnapshot
        if not isinstance(asset, InspectedAsset) or self.assets.get(asset.asset_id) != asset:
            raise MaterialUnavailable('MEDIA_OUTSIDE_AUTHORIZATION')
        with Session(self.engine) as db:
            row = db.get(SocialMediaAsset, asset.asset_id)
            if (not row or row.state != 'ready' or row.deleted_at is not None
                    or row.storage_provider != self.storage.provider or row.bucket != self.storage.bucket
                    or (row.sha256, row.mime_type, row.byte_size, row.width, row.height, row.duration_ms)
                    != (asset.sha256, asset.mime_type, asset.byte_size, asset.width, asset.height, asset.duration_ms)
                    or row.mime_type not in {'image/jpeg', 'image/png'}
                    or not isinstance(row.codec_metadata.get('storage_etag'), str)
                    or not row.codec_metadata['storage_etag']):
                raise MaterialUnavailable('MEDIA_FINAL_IDENTITY_CHANGED')
            return row.storage_key, ObjectSnapshot(row.byte_size, row.codec_metadata['storage_etag'],
                row.codec_metadata.get('storage_version'), row.sha256, row.mime_type)

    def _read(self, asset, maximum_bytes):
        import hashlib
        from pathlib import Path
        from tempfile import TemporaryDirectory
        if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= 8_000_000 or asset.byte_size > maximum_bytes:
            raise MaterialUnavailable('MEDIA_BYTE_LIMIT')
        key, expected = self._snapshot(asset)
        try:
            if self.storage.head(key) != expected:
                raise ValueError()
            with TemporaryDirectory(prefix='social-provider-media-') as directory:
                path = Path(directory) / 'verified-image'
                self.storage.download(key, expected, path, maximum_bytes)
                with path.open('rb') as source:
                    content = source.read(maximum_bytes + 1)
            if len(content) != asset.byte_size or hashlib.sha256(content).hexdigest() != asset.sha256 or self.storage.head(key) != expected:
                raise ValueError()
            return content
        except Exception:
            raise MaterialUnavailable('MEDIA_BYTES_UNVERIFIED') from None

    async def read_bytes(self, asset, maximum_bytes):
        import asyncio
        return await asyncio.to_thread(self._read, asset, maximum_bytes)

    def _fetch_url(self, asset, minimum_ttl_seconds):
        from datetime import timedelta, timezone
        from urllib.parse import parse_qs, quote, urlsplit
        if type(minimum_ttl_seconds) is not int or not 1 <= minimum_ttl_seconds <= 240:
            raise MaterialUnavailable('MEDIA_FETCH_TTL_INVALID')
        self._read(asset, 8_000_000)
        key, expected = self._snapshot(asset)
        try:
            signed = self.storage.preview(key, expected, 300)
            if (not isinstance(signed.url, str) or not 1 <= len(signed.url) <= 8000
                    or '\\' in signed.url or any(ord(c) < 33 or ord(c) > 126 for c in signed.url)):
                raise ValueError()
            parsed = urlsplit(signed.url)
            query = parse_qs(parsed.query, keep_blank_values=True)
            if query.get('versionId', []) != ([expected.version] if expected.version is not None else []):
                raise ValueError()
            # R2Storage derives expiry from this signature. Abstract test ports
            # may attest expiry directly, but cannot contradict present fields.
            if 'X-Amz-Date' in query or 'X-Amz-Expires' in query:
                if len(query.get('X-Amz-Date', [])) != 1 or query.get('X-Amz-Expires') != ['300']:
                    raise ValueError()
                actual_expiry = datetime.strptime(query['X-Amz-Date'][0], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc) + timedelta(seconds=300)
                if actual_expiry != signed.expires_at:
                    raise ValueError()
            now = datetime.now(timezone.utc)
            if (parsed.scheme != 'https' or parsed.hostname != self.allowed_origin or parsed.port not in {None, 443}
                    or parsed.username or parsed.password or parsed.fragment
                    or parsed.path != '/' + quote(self.storage.bucket, safe='') + '/' + quote(key, safe='/')
                    or not isinstance(signed.expires_at, datetime) or signed.expires_at.tzinfo is None
                    or signed.expires_at < now + timedelta(seconds=minimum_ttl_seconds)
                    or signed.expires_at > now + timedelta(seconds=301)
                    or self.storage.head(key) != expected):
                raise ValueError()
            return ProviderFetchURL(signed.url, signed.expires_at, asset.asset_id, asset.sha256)
        except Exception:
            raise MaterialUnavailable('MEDIA_FETCH_UNAVAILABLE') from None

    async def provider_fetch_url(self, asset, minimum_ttl_seconds):
        import asyncio
        return await asyncio.to_thread(self._fetch_url, asset, minimum_ttl_seconds)

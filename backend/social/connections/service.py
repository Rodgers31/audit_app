"""Durable, session-bound OAuth state and account mutations.

Transactions finish before provider HTTP. Account changes lock controls, then
accounts in UUID order, then credentials. A provider exchange is never retried
because its single-use state was already consumed before the external request.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import select, text

from ..contracts import CapabilitySet, canonical_hash
from ..models import SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls
from ..service import SocialError, SocialService, iso, utc
from ..telemetry import log_event
from .config import SCOPES, PAGE_SCOPES, IG_SCOPES
from .crypto import CredentialCipher
from .models import SocialCredential, SocialOAuthFlow
from .provider import MetaProvider


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session_binding(actor: UUID, session_id: UUID):
    return digest(str(actor) + ':' + str(session_id))


def date(value):
    return datetime.fromisoformat(value) if value else None


class ConnectionService:
    def __init__(self, db, config, *, provider_factory=MetaProvider, available_adapters=frozenset()):
        self.db, self.config, self.provider_factory = db, config, provider_factory
        self.base = SocialService(db, available_adapters=available_adapters)

    @property
    def cipher(self):
        return CredentialCipher(self.config.active_key_version, self.config.encryption_keys)

    def _audit(self, actor, request_id, action, *, account=None, previous=None, new=None, reason=None, details=None):
        self.db.add(SocialAuditEvent(actor_id=actor, actor_kind='admin', account_id=account.id if account else None, action=action, previous_state=previous, new_state=new, reason=reason, details=details or {}, request_id=str(request_id)))

    def status(self):
        self.db.execute(select(SocialOAuthFlow.id).limit(1))  # Missing schema is unavailable, never a success.
        errors = self.config.blockers()
        return {'provider': 'meta', 'available': not errors, 'blockers': errors, 'access_mode': self.config.access_mode if self.config.access_mode in {'owned_standard','advanced'} else 'unverified', 'scopes': list(SCOPES), 'publishing_adapter_available': False}

    def _body(self, body, binding):
        # Only a digest is persisted by SocialService.command. No code/state body is logged.
        return {'command': body.model_dump(mode='json'), 'binding_hash': binding}

    def _receipt(self, actor, route, key, body):
        if self.db.bind.dialect.name == 'postgresql':
            value = int(canonical_hash([str(actor), route, str(key)])[:16], 16)
            self.db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': value if value < 2**63 else value - 2**64})
        receipt = self.db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.actor_key == str(actor), SocialCommandReceipt.route_key == route, SocialCommandReceipt.idempotency_key == key))
        if receipt and receipt.request_hash != canonical_hash(body):
            raise SocialError('IDEMPOTENCY_CONFLICT', 'This command key was already used with different input or another administrator session.')
        return receipt

    def _flow(self, flow_id, actor, binding):
        flow = self.db.scalar(select(SocialOAuthFlow).where(SocialOAuthFlow.id == flow_id).with_for_update().execution_options(populate_existing=True))
        if not flow or flow.actor_id != actor or not hmac.compare_digest(flow.binding_hash, binding):
            raise SocialError('OAUTH_STATE_INVALID', 'This connection belongs to another or expired administrator session. Start a new connection.', 409)
        if utc(flow.expires_at) <= self.base.now():
            raise SocialError('OAUTH_STATE_EXPIRED', 'This connection flow expired. Start a new connection.', 409)
        return flow

    def start(self, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        self.config.require_redirect(body.redirect_uri)
        def action():
            if body.reconnect_account_id:
                row = self.db.get(SocialAccount, body.reconnect_account_id)
                if not row or row.connection_method != 'facebook_login':
                    raise SocialError('NOT_FOUND', 'This Meta account was not found.', 404)
            now = self.base.now()
            flow = SocialOAuthFlow(id=uuid4(), actor_id=actor, state_hash='0' * 64, binding_hash=binding, redirect_uri=body.redirect_uri, reconnect_account_id=body.reconnect_account_id, status='initiated', expires_at=now + timedelta(minutes=10))
            state = secrets.token_urlsafe(32)
            flow.state_hash = digest(state)
            flow.key_version, flow.encrypted_verifier = self.cipher.encrypt(flow.id, 'oauth_start', {'state': state})
            self.db.add(flow)
            self._audit(actor, request_id, 'connection.started', reason=body.reason, details={'flow_id': str(flow.id), 'reconnect_account_id': str(body.reconnect_account_id) if body.reconnect_account_id else None})
            return {'flow_id': str(flow.id), 'expires_at': iso(flow.expires_at)}
        _, result = self.base.command(actor=actor, route=route, key=key, body=self._body(body, binding), request_id=request_id, action=action)
        with self.db.begin():
            flow = self._flow(UUID(result['flow_id']), actor, binding)
            if flow.status != 'initiated':
                raise SocialError('OAUTH_STATE_USED', 'This connection already advanced. Start a new connection.')
            state = self.cipher.decrypt(flow.id, 'oauth_start', flow.key_version, flow.encrypted_verifier)['state']
        result = dict(result)
        result['authorize_url'] = f'https://www.facebook.com/{self.config.graph_version}/dialog/oauth?' + urlencode({'client_id': self.config.app_id, 'redirect_uri': body.redirect_uri, 'state': state, 'response_type': 'code', 'scope': ','.join(SCOPES), 'auth_type': 'rerequest'})
        return result

    def _discovery_dto(self, flow, grant):
        choices = []
        for p in grant['choices']:
            ig = p['instagram']
            choices.append({k: p[k] for k in ('page_id','display_name','tasks','page_eligible','instagram_eligible','missing_page_scopes','missing_instagram_scopes')} | {'instagram_id': ig['id'] if ig else None, 'instagram_name': ig['name'] if ig else None, 'instagram_handle': ig['username'] if ig else None})
        return {'flow_id': str(flow.id), 'expires_at': iso(flow.expires_at), 'granted_scopes': grant['metadata']['scopes'], 'choices': choices}

    def complete(self, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        self.config.require_redirect(body.redirect_uri)
        command_body = self._body(body, binding)
        with self.db.begin():
            receipt = self._receipt(actor, route, key, command_body)
            if receipt:
                return receipt.response
            flow = self.db.scalar(select(SocialOAuthFlow).where(SocialOAuthFlow.state_hash == digest(body.state)).with_for_update())
            if not flow:
                raise SocialError('OAUTH_STATE_INVALID', 'This connection state is invalid. Start a new connection.')
            flow = self._flow(flow.id, actor, binding)
            if flow.redirect_uri != body.redirect_uri:
                raise SocialError('REDIRECT_MISMATCH', 'The callback URL differs from the URL used to start this connection.', 422)
            if flow.status != 'initiated':
                raise SocialError('OAUTH_STATE_USED', 'This connection state was already consumed. Start a new connection.')
            flow_id = flow.id
            flow.status, flow.consumed_at, flow.encrypted_verifier = 'exchanging', self.base.now(), None
            flow.updated_at = self.base.now()
            self._audit(actor, request_id, 'connection.state_consumed', details={'flow_id': str(flow.id)})
        try:
            provider = self.provider_factory(self.config)
            try:
                grant = provider.discover(body.code, body.redirect_uri)
            finally:
                provider.close()
            def save():
                current = self._flow(flow_id, actor, binding)
                if current.status != 'exchanging':
                    raise SocialError('OAUTH_STATE_USED', 'This connection state was already consumed.')
                current.status = 'awaiting_selection'
                current.key_version, current.encrypted_pending_grant = self.cipher.encrypt(current.id, 'oauth_pending', grant)
                current.updated_at = self.base.now()
                self._audit(actor, request_id, 'connection.discovered', details={'flow_id': str(current.id), 'page_count': len(grant['choices'])})
                return self._discovery_dto(current, grant)
            _, result = self.base.command(actor=actor, route=route, key=key, body=command_body, request_id=request_id, action=save)
            return result
        except Exception as error:
            # Transaction failure may contain bind parameters; never serialize it.
            self.db.rollback()
            with self.db.begin():
                current = self.db.scalar(select(SocialOAuthFlow).where(SocialOAuthFlow.id == flow_id).with_for_update())
                if current and current.status == 'exchanging':
                    current.status, current.encrypted_verifier, current.encrypted_pending_grant = 'failed', None, None
                    current.updated_at = self.base.now()
                    self._audit(actor, request_id, 'connection.failed', details={'flow_id': str(flow_id), 'error_code': error.code if isinstance(error, SocialError) else 'CONNECTION_FAILED'})
            log_event('social.connection_failed', request_id=request_id, error_code=error.code if isinstance(error, SocialError) else 'CONNECTION_FAILED', error_type=type(error).__name__)
            raise

    def discovery(self, flow_id, actor, binding):
        with self.db.begin():
            flow = self._flow(flow_id, actor, binding)
            if flow.status != 'awaiting_selection':
                raise SocialError('OAUTH_SELECTION_UNAVAILABLE', 'This connection is not awaiting account selection. Start a new connection.')
            grant = self.cipher.decrypt(flow.id, 'oauth_pending', flow.key_version, flow.encrypted_pending_grant)
            return self._discovery_dto(flow, grant)

    def _controls_lock(self):
        controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))
        if not controls:
            if self.db.bind.dialect.name == 'postgresql':
                self.db.execute(text('SELECT pg_advisory_xact_lock(6384952001)'))
                controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))
            if not controls:
                controls = SocialControls(id=1, version=1)
                self.db.add(controls)
                self.db.flush()
        return controls

    def _lock_accounts(self, accounts):
        self._controls_lock()
        rows = list(self.db.scalars(select(SocialAccount).where(SocialAccount.id.in_(accounts)).order_by(SocialAccount.id).with_for_update().execution_options(populate_existing=True))) if accounts else []
        for row in rows:
            if row.publish_lease_token or row.publish_lease_target_id:
                raise SocialError('ACCOUNT_BUSY', 'This account has an unresolved publication lease. Resolve that delivery before changing credentials.')
        return rows

    def _credential(self, row, expected_version=None, expected_id=None):
        credential = self.db.scalar(select(SocialCredential).where(SocialCredential.id == row.credential_id).with_for_update().execution_options(populate_existing=True))
        if not credential:
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'This account credential is unavailable. Reconnect.', 409)
        if expected_id is not None and credential.id != expected_id:
            raise SocialError('VERSION_CONFLICT', 'This account was reconnected with another credential. Refresh account health before continuing.')
        if expected_version is not None and credential.version != expected_version:
            raise SocialError('VERSION_CONFLICT', 'This credential changed. Refresh account health before continuing.')
        if credential.refresh_lease_token and utc(credential.refresh_lease_expires_at) > self.base.now():
            raise SocialError('CREDENTIAL_BUSY', 'This credential is being renewed. Refresh account health before continuing.')
        return credential

    def _new_credential(self, kind, bundle, metadata, parent=None):
        row = SocialCredential(id=uuid4(), credential_kind=kind, parent_credential_id=parent, access_expires_at=date(metadata['access_expires_at']), data_access_expires_at=date(metadata['data_access_expires_at']))
        row.key_version, row.encrypted_bundle = self.cipher.encrypt(row.id, kind, bundle)
        self.db.add(row)
        self.db.flush()
        return row

    def _account_dto(self, row):
        return {'id': str(row.id), 'platform': row.platform, 'display_name': row.display_name, 'handle': row.handle, 'profile_url': row.profile_url, 'connection_state': row.connection_state, 'publishing_enabled': row.publishing_enabled, 'capabilities': CapabilitySet.model_validate(row.capability_snapshot).model_dump(mode='json')}

    def select(self, flow_id, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        def action():
            self._controls_lock()
            flow = self._flow(flow_id, actor, binding)
            if flow.status != 'awaiting_selection':
                raise SocialError('OAUTH_STATE_USED', 'This connection was already confirmed or is unavailable.')
            grant = self.cipher.decrypt(flow.id, 'oauth_pending', flow.key_version, flow.encrypted_pending_grant)
            page = next((p for p in grant['choices'] if p['page_id'] == body.page_id), None)
            if not page or (body.instagram_id and (not page['instagram'] or page['instagram']['id'] != body.instagram_id)):
                raise SocialError('ASSET_SELECTION_INVALID', 'Choose a Page and its exact linked Instagram account from this connection.', 422)
            if not page['page_eligible'] or (body.instagram_id and not page['instagram_eligible']):
                raise SocialError('PERMISSIONS_REQUIRED', 'The selected assets lack required grants, professional eligibility or Page content tasks.')
            now = self.base.now()
            for metadata in (grant['metadata'], page['metadata']):
                if any(date(metadata[k]) and date(metadata[k]) <= now for k in ('access_expires_at','data_access_expires_at')):
                    raise SocialError('GRANT_REVOKED', 'This grant expired before selection. Reconnect.')
            identities = [('facebook','facebook_pages', page['page_id'], page['display_name'], None)]
            if body.instagram_id:
                ig = page['instagram']
                identities.append(('instagram','instagram_graph_facebook_login', ig['id'], ig['name'], ig['username']))
            existing = []
            for platform, product, external_id, _, _ in identities:
                row = self.db.scalar(select(SocialAccount).where(SocialAccount.platform == platform, SocialAccount.api_product == product, SocialAccount.external_account_id == external_id))
                if row:
                    existing.append(row)
            if flow.reconnect_account_id and flow.reconnect_account_id not in {a.id for a in existing}:
                raise SocialError('RECONNECT_IDENTITY_MISMATCH', 'Reconnect must confirm the same account identity. Start a separate connection for a different asset.')
            # Lock all sibling accounts of any old Page credential before replacing/revoking it.
            old_ids = {a.credential_id for a in existing if a.credential_id}
            siblings = list(self.db.scalars(select(SocialAccount).where(SocialAccount.credential_id.in_(old_ids)))) if old_ids else []
            self._lock_accounts({a.id for a in existing + siblings})
            parent = self._new_credential('facebook_user', {'access_token': grant['user_token'], 'external_user_id': grant['metadata']['external_user_id'], 'scopes': grant['metadata']['scopes']}, grant['metadata'])
            credential = self._new_credential('facebook_page', {'access_token': page['page_token'], 'page_id': page['page_id'], 'external_user_id': page['metadata']['external_user_id'], 'scopes': page['metadata']['scopes']}, page['metadata'], parent.id)
            accounts = []
            for platform, product, external_id, name, handle in identities:
                row = next((a for a in existing if a.platform == platform and a.external_account_id == external_id), None)
                previous = row.connection_state if row else None
                if row is None:
                    row = SocialAccount(id=uuid4(), platform=platform, api_product=product, connection_method='facebook_login', external_account_id=external_id, granted_scopes=[])
                    self.db.add(row)
                row.display_name, row.handle = name, handle
                row.profile_url = f'https://www.instagram.com/{handle}/' if handle else f'https://www.facebook.com/{external_id}'
                row.credential_id, row.connection_state, row.publishing_enabled, row.hold_reason = credential.id, 'connected', False, None
                row.granted_scopes = page['metadata']['scopes']
                required = PAGE_SCOPES if platform == 'facebook' else IG_SCOPES
                row.capability_snapshot = CapabilitySet(provider_api_version=self.config.graph_version, eligible=True, supported_formats=(), granted_scopes=tuple(row.granted_scopes), required_scopes=tuple(sorted(required)), price_class='free', verified_at=now, adapter_available=False, feature_states={'publishing':'unsupported','media_upload':'unsupported'}, source_links=('https://developers.facebook.com/docs/pages-api/', 'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/')).model_dump(mode='json')
                from ..validation import registered_capability
                if self.base.available_adapters:
                    row.capability_snapshot = registered_capability(row, self.base.available_adapters).model_dump(mode='json')
                row.capabilities_checked_at, row.last_api_success_at, row.updated_at = now, now, now
                self._audit(actor, request_id, 'connection.reconnected' if previous else 'connection.connected', account=row, previous=previous, new='connected', reason=body.reason, details={'flow_id': str(flow.id), 'credential_id': str(credential.id)})
                accounts.append(row)
            # The administrator selected exact identities. Unselected former siblings
            # must reconnect; they cannot keep an obsolete credential silently.
            for sibling in siblings:
                if sibling.id not in {a.id for a in accounts}:
                    previous = sibling.connection_state
                    sibling.connection_state, sibling.publishing_enabled, sibling.hold_reason = 'disconnected', False, 'RECONNECT_REQUIRED'
                    sibling.updated_at = now
                    self._audit(actor, request_id, 'connection.disconnected', account=sibling, previous=previous, new='disconnected', reason=body.reason)
            for old_id in sorted(old_ids):
                old = self.db.scalar(select(SocialCredential).where(SocialCredential.id == old_id).with_for_update())
                if old:
                    if old.refresh_lease_token and utc(old.refresh_lease_expires_at) > now:
                        raise SocialError('CREDENTIAL_BUSY', 'The previous credential is being renewed. Try again after renewal completes.')
                    old.revoked_at, old.version, old.updated_at = now, old.version + 1, now
            flow.status, flow.encrypted_pending_grant, flow.updated_at = 'completed', None, now
            self.db.flush()
            return {'flow_id': str(flow.id), 'accounts': [self._account_dto(a) for a in accounts]}
        _, result = self.base.command(actor=actor, route=route, key=key, body=self._body(body, binding), request_id=request_id, action=action)
        return result

    def health(self, account_id):
        def compact(model, fields, identifier):
            value = self.db.execute(select(*(getattr(model, field) for field in fields)).where(model.id == identifier)).one_or_none()
            return SimpleNamespace(**value._mapping) if value else None
        row = compact(SocialAccount, ('id','platform','external_account_id','api_product','connection_method','connection_state','credential_id','granted_scopes','publishing_enabled','capabilities_checked_at','last_api_success_at'), account_id)
        if not row or row.connection_method != 'facebook_login':
            raise SocialError('NOT_FOUND', 'This Meta account was not found.', 404)
        fields = ('id','credential_kind','parent_credential_id','access_expires_at','data_access_expires_at','revoked_at','version','key_version')
        credential = compact(SocialCredential, fields, row.credential_id)
        if not credential or credential.credential_kind != 'facebook_page':
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'This account credential is unavailable. Reconnect.')
        parent = compact(SocialCredential, fields, credential.parent_credential_id)
        now = self.base.now()
        expired = any(v and utc(v) <= now for v in (credential.access_expires_at, credential.data_access_expires_at))
        parent_expired = bool(parent and any(v and utc(v) <= now for v in (parent.access_expires_at, parent.data_access_expires_at)))
        revoked = credential.revoked_at is not None or parent is None or parent.revoked_at is not None
        state = 'revoked' if revoked and row.connection_state == 'connected' else 'expired' if expired and row.connection_state == 'connected' else row.connection_state
        required = PAGE_SCOPES if row.platform == 'facebook' else IG_SCOPES
        # A long-lived parent User grant's expiry is not a Page-token expiry.
        # Keep actual metadata separate; never invent a scheduled Page expiry.
        access, data_access = credential.access_expires_at, credential.data_access_expires_at
        return {'account_id': str(row.id), 'external_account_id': row.external_account_id, 'api_product': row.api_product, 'connection_method': 'facebook_login', 'connection_state': state, 'credential_kind': 'facebook_page', 'credential_id': str(credential.id), 'credential_version': credential.version, 'key_version': credential.key_version, 'access_expires_at': iso(access), 'data_access_expires_at': iso(data_access), 'parent_access_expires_at': iso(parent.access_expires_at) if parent else None, 'parent_data_access_expires_at': iso(parent.data_access_expires_at) if parent else None, 'parent_grant_reconnect_required': parent_expired or revoked, 'granted_scopes': row.granted_scopes, 'missing_scopes': sorted(required - set(row.granted_scopes)), 'checked_at': iso(row.capabilities_checked_at), 'last_api_success_at': iso(row.last_api_success_at), 'reconnect_required': state != 'connected' or bool(required - set(row.granted_scopes)), 'publishing_enabled': row.publishing_enabled, 'renewal_strategy': 'facebook_login_reconnect', 'provider_revocation_confirmed': False}

    def account_command(self, account_id, actor, binding, route, key, body, request_id, *, rotate=False):
        def action():
            self._controls_lock()
            row = self.db.scalar(select(SocialAccount).where(SocialAccount.id == account_id).execution_options(populate_existing=True))
            if not row or row.connection_method != 'facebook_login':
                raise SocialError('NOT_FOUND', 'This Meta account was not found.', 404)
            affected_ids = {row.credential_id}
            if rotate:
                current = self.db.get(SocialCredential, row.credential_id)
                if not current:
                    raise SocialError('CREDENTIAL_UNAVAILABLE', 'This account credential is unavailable. Reconnect.')
                affected_ids.add(current.parent_credential_id)
                affected_ids.update(self.db.scalars(select(SocialCredential.id).where(SocialCredential.parent_credential_id == current.parent_credential_id)))
            siblings = list(self.db.scalars(select(SocialAccount).where(SocialAccount.credential_id.in_(affected_ids))))
            rows = self._lock_accounts({a.id for a in siblings})
            related = list(self.db.scalars(select(SocialCredential).where(SocialCredential.id.in_(affected_ids)).order_by(SocialCredential.id).with_for_update().execution_options(populate_existing=True))) if rotate else []
            credential = self._credential(row, body.expected_credential_version, body.expected_credential_id)
            now = self.base.now()
            if rotate:
                for item in related:
                    if item.refresh_lease_token and utc(item.refresh_lease_expires_at) > now:
                        raise SocialError('CREDENTIAL_BUSY', 'A related credential is being renewed. Try again after renewal completes.')
                    item.key_version, item.encrypted_bundle = self.cipher.rotate(item.id, item.credential_kind, item.key_version, item.encrypted_bundle)
                    item.version, item.updated_at = item.version + 1, now
                self._audit(actor, request_id, 'credential.rotated', account=row, reason=body.reason, details={'credential_version': credential.version, 'key_version': credential.key_version, 'credential_count': len(related)})
            else:
                credential.revoked_at, credential.version, credential.updated_at = now, credential.version + 1, now
                for sibling in rows:
                    previous = sibling.connection_state
                    sibling.connection_state, sibling.publishing_enabled, sibling.hold_reason, sibling.updated_at = 'disconnected', False, 'LOCAL_DISCONNECT', now
                    self._audit(actor, request_id, 'connection.disconnected', account=sibling, previous=previous, new='disconnected', reason=body.reason, details={'provider_revocation_confirmed': False})
            self.db.flush()
            return self.health(account_id)
        _, result = self.base.command(actor=actor, route=route, key=key, body=self._body(body, binding), request_id=request_id, action=action)
        return result

    def expire_flows(self, *, limit=100):
        """Explicit maintenance hook; no scheduler/startup side effects.

        Purge pending grants after ten minutes even when no browser returns.
        An in-flight exchange cannot persist after this transition.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SocialError('INVALID_REQUEST', 'Flow maintenance is bounded to 100 rows.', 422)
        with self.db.begin():
            now = self.base.now()
            rows = list(self.db.scalars(select(SocialOAuthFlow).where(SocialOAuthFlow.expires_at <= now, SocialOAuthFlow.status.in_(('initiated','exchanging','awaiting_selection'))).order_by(SocialOAuthFlow.expires_at, SocialOAuthFlow.id).limit(limit).with_for_update(skip_locked=True)))
            for flow in rows:
                flow.status, flow.encrypted_verifier, flow.encrypted_pending_grant, flow.updated_at = 'expired', None, None, now
            return len(rows)

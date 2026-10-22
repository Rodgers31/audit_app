"""Receipt-bound durable OAuth and renewal, never an in-memory publisher.

The database commit consumes OAuth state and claims refresh before HTTP. Any
uncertain refresh retains its claim until an explicit fresh authorization.
"""
import hmac
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update, text

from ..contracts import CapabilitySet
from ..connections.crypto import CredentialCipher
from ..connections.service import digest
from ..models import SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls
from ..service import SocialError, SocialService, iso, utc
from .models import PlatformCredential, PlatformOAuthFlow, SocialPlatformConnectionBudget
from .provider import OAuthProvider


class PlatformConnectionService:
    def __init__(self, db, config, *, provider_factory=None, available_adapters=frozenset()):
        if provider_factory is None:
            from .tiktok_provider import TikTokConnectionProvider
            provider_factory = TikTokConnectionProvider if config.platform == 'tiktok' else (lambda c: OAuthProvider(c, admission=self.connection_admission))
        self.db, self.config, self.provider_factory = db, config, provider_factory
        self.base = SocialService(db, available_adapters=available_adapters)
        self.available_adapters = available_adapters

    @property
    def cipher(self):
        return CredentialCipher(self.config.active_key_version, self.config.encryption_keys)

    def purpose(self, kind):
        return 'platform:' + self.config.platform + ':' + kind

    def _audit(self, actor, request_id, action, *, account_id=None, reason=None, details=None):
        self.db.add(SocialAuditEvent(actor_id=actor, actor_kind='admin', request_id=str(request_id), action='platform_connection.' + action, account_id=account_id, reason=reason, details=details or {}))

    def _connection_budget(self, cost):
        self.config.require_ready()
        if self.config.platform != 'x':
            return
        row = self.db.scalar(select(SocialPlatformConnectionBudget).where(SocialPlatformConnectionBudget.client_key == digest('x:' + self.config.client_id)).with_for_update().execution_options(populate_existing=True))
        if (type(cost) is not int or cost < 0 or cost > 2**63 - 1 or row is None or row.enabled is not True or row.access_verified is not True
                or type(row.limit_microusd) is not int or type(row.reserved_microusd) is not int or not 0 <= row.reserved_microusd < row.limit_microusd <= 2**63 - 1
                or row.limit_microusd - row.reserved_microusd < max(1, cost)):
            raise SocialError('X_BUDGET_UNAVAILABLE', 'X connection access and a positive durable read budget are required.', 503)
        if cost:
            reserved, version = row.reserved_microusd + cost, row.version + 1
            result = self.db.execute(update(SocialPlatformConnectionBudget).where(SocialPlatformConnectionBudget.client_key == row.client_key, SocialPlatformConnectionBudget.version == row.version).values(reserved_microusd=reserved, version=version))
            if result.rowcount != 1:
                raise SocialError('X_BUDGET_RESERVATION_FAILED', 'The durable read reservation did not commit the required row.', 503)
            if self.db.bind.dialect.name == 'postgresql':
                self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            actual = self.db.execute(select(SocialPlatformConnectionBudget.reserved_microusd, SocialPlatformConnectionBudget.version).where(SocialPlatformConnectionBudget.client_key == row.client_key)).one()
            if type(actual[0]) is not int or type(actual[1]) is not int or actual != (reserved, version):
                raise SocialError('X_BUDGET_RESERVATION_FAILED', 'Stored read reservation differs from the required reservation.', 503)

    def connection_admission(self, cost=0):
        # Persist reservation before HTTP; failures/crashes never refund it.
        with self.db.begin():
            self._connection_budget(cost)
        return True

    def _command(self, actor, binding, route, key, body, request_id, action):
        return self.base.command(actor=actor, route=route, key=key, body={'platform': self.config.platform, 'binding': binding, 'command': body.model_dump(mode='json')}, request_id=request_id, action=action)[1]

    def _receipt(self, actor, binding, route, key, body):
        # Reuse the same receipt and advisory-key semantics as SocialService.
        from ..connections.service import ConnectionService
        payload = {'platform': self.config.platform, 'binding': binding, 'command': body.model_dump(mode='json')}
        return ConnectionService._receipt(self, actor, route, key, payload)

    def _flow(self, flow_id, actor, binding):
        row = self.db.scalar(select(PlatformOAuthFlow).where(PlatformOAuthFlow.id == flow_id).with_for_update().execution_options(populate_existing=True))
        if not row or row.platform != self.config.platform or row.actor_id != actor or not hmac.compare_digest(row.binding_hash, binding):
            raise SocialError('OAUTH_STATE_INVALID', 'This connection belongs to another administrator session.', 409)
        if utc(row.expires_at) <= self.base.now():
            raise SocialError('OAUTH_STATE_EXPIRED', 'This connection expired. Start a fresh authorization.', 409)
        return row

    def status(self):
        blockers = self.config.blockers()
        if not blockers:
            # Configured access cannot certify a missing durable store as ready.
            self.db.execute(select(PlatformOAuthFlow.id).limit(1))
            self.db.execute(select(PlatformCredential.id).limit(1))
            if self.config.platform == 'x':
                from ..platform_budget import SocialPlatformBudget
                self.db.execute(select(SocialPlatformBudget.account_id).limit(1))
                try:
                    self._connection_budget(0)
                except SocialError as error:
                    blockers.append(error.code)
        from ..connections.callback_ingress import BLOCKER
        if BLOCKER in self.config.oauth_blockers():
            blockers.append(BLOCKER)
        return {'provider': self.config.platform, 'available': not blockers, 'blockers': blockers, 'scopes': self.config.scopes, 'provider_api_version': {'threads':'v1.0', 'x':'v2', 'tiktok':'v1.3'}[self.config.platform], 'publishing_enabled': False}

    def start(self, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        self.config.require_redirect(body.redirect_uri)
        if body.reconnect_account_id is not None:
            raise SocialError('RECONNECT_ID_UNSUPPORTED', 'Confirm the freshly authorized identity to reconnect its existing account.', 422)
        def action():
            self._connection_budget(0)
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
            row = PlatformOAuthFlow(id=uuid4(), platform=self.config.platform, actor_id=actor, binding_hash=binding, state_hash=digest(state), redirect_uri=body.redirect_uri, expires_at=self.base.now() + timedelta(minutes=10))
            row.key_version, row.encrypted_secret = self.cipher.encrypt(row.id, self.purpose('start'), {'state': state, 'verifier': verifier})
            self.db.add(row)
            self._audit(actor, request_id, 'started', reason=body.reason, details={'flow_id': str(row.id), 'platform': row.platform})
            return {'flow_id': str(row.id), 'expires_at': iso(row.expires_at)}
        result = dict(self._command(actor, binding, route, key, body, request_id, action))
        with self.db.begin():
            row = self._flow(UUID(result['flow_id']), actor, binding)
            if row.status != 'initiated':
                raise SocialError('OAUTH_STATE_USED', 'This authorization already advanced.', 409)
            secret = self.cipher.decrypt(row.id, self.purpose('start'), row.key_version, row.encrypted_secret)
        provider = self.provider_factory(self.config)
        try:
            result['authorize_url'] = provider.authorize_url(secret['state'], body.redirect_uri, secret['verifier'])
        finally:
            provider.close()
        return result

    def _choice(self, row, grant):
        return {'flow_id': str(row.id), 'external_account_id': grant['subject'], 'display_name': grant['display_name'], 'handle': grant['username'], 'granted_scopes': grant['scopes'], 'expires_at': iso(row.expires_at)}

    def complete(self, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        self.config.require_redirect(body.redirect_uri)
        with self.db.begin():
            receipt = self._receipt(actor, binding, route, key, body)
            if receipt:
                return receipt.response
            self._connection_budget(0)
            row = self.db.scalar(select(PlatformOAuthFlow).where(PlatformOAuthFlow.state_hash == digest(body.state)).with_for_update())
            row = self._flow(row.id if row else uuid4(), actor, binding)
            if row.status != 'initiated':
                raise SocialError('OAUTH_STATE_USED', 'This authorization was already consumed. Start a fresh connection.', 409)
            if row.redirect_uri != body.redirect_uri:
                raise SocialError('REDIRECT_MISMATCH', 'This callback differs from the initiating callback.', 422)
            secret = self.cipher.decrypt(row.id, self.purpose('start'), row.key_version, row.encrypted_secret)
            flow_id = row.id
            row.status, row.consumed_at, row.encrypted_secret = 'exchanging', self.base.now(), None
            self._audit(actor, request_id, 'state_consumed', details={'flow_id': str(row.id)})
        try:
            provider = self.provider_factory(self.config)
            try:
                grant = provider.exchange(body.code, body.redirect_uri, secret['verifier'])
            finally:
                provider.close()
            def save():
                row = self._flow(flow_id, actor, binding)
                if row.status != 'exchanging':
                    raise SocialError('OAUTH_STATE_USED', 'This connection advanced concurrently.', 409)
                row.status = 'awaiting_confirmation'
                row.key_version, row.encrypted_secret = self.cipher.encrypt(row.id, self.purpose('pending'), grant)
                self._audit(actor, request_id, 'identity_observed', details={'flow_id': str(row.id), 'platform': row.platform})
                return self._choice(row, grant)
            return self._command(actor, binding, route, key, body, request_id, save)
        except Exception:
            # State was already committed consumed: failed persistence cannot replay HTTP.
            self.db.rollback()
            with self.db.begin():
                row = self.db.scalar(select(PlatformOAuthFlow).where(PlatformOAuthFlow.id == flow_id).with_for_update())
                if row and row.status == 'exchanging':
                    row.status, row.encrypted_secret = 'failed', None
                    self._audit(actor, request_id, 'exchange_failed', details={'flow_id': str(flow_id)})
            raise

    def choice(self, flow_id, actor, binding):
        self.config.require_ready()
        with self.db.begin():
            row = self._flow(flow_id, actor, binding)
            if row.status != 'awaiting_confirmation':
                raise SocialError('OAUTH_CONFIRMATION_UNAVAILABLE', 'This connection is not awaiting confirmation.', 409)
            return self._choice(row, self.cipher.decrypt(row.id, self.purpose('pending'), row.key_version, row.encrypted_secret))

    def _lock_account(self, account_id):
        # Shared order: controls, account, then provider credential.
        self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
        row = self.db.scalar(select(SocialAccount).where(SocialAccount.id == account_id).with_for_update().execution_options(populate_existing=True))
        if not row or row.platform != self.config.platform:
            raise SocialError('NOT_FOUND', 'This provider account was not found.', 404)
        if row.publish_lease_token or row.publish_lease_target_id:
            raise SocialError('ACCOUNT_BUSY', 'Resolve the retained publication lease before changing credentials.', 409)
        return row

    def _credential(self, account_id, expected_id=None, expected_version=None):
        row = self.db.scalar(select(PlatformCredential).where(PlatformCredential.account_id == account_id, PlatformCredential.platform == self.config.platform).with_for_update().execution_options(populate_existing=True))
        if not row:
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'Reconnect this provider account.', 409)
        if (expected_id is not None and row.id != expected_id) or (expected_version is not None and row.version != expected_version):
            raise SocialError('VERSION_CONFLICT', 'This credential changed. Refresh the account before continuing.', 409)
        return row

    def _capabilities(self, account, scopes, now):
        """Freeze exactly the registered native adapter contract, with DB X gates."""
        adapter = self.available_adapters.get((account.platform, account.api_product)) if isinstance(self.available_adapters, Mapping) else None
        if adapter is None:
            return CapabilitySet(provider_api_version={'threads':'v1.0', 'x':'v2', 'tiktok':'v1.3'}[account.platform], eligible=False, granted_scopes=tuple(scopes), required_scopes=self.config.scopes, verified_at=now, adapter_available=False).model_dump(mode='json')
        inspected = {'id': account.id, 'platform': account.platform, 'api_product': account.api_product, 'connection_state': 'connected', 'granted_scopes': scopes, 'capability_snapshot': {'eligible': True}}
        if account.platform == 'x':
            from ..platform_budget import SocialPlatformBudget, budget_available
            budget = self.db.get(SocialPlatformBudget, account.id)
            values = {name: getattr(budget, name) for name in ('enabled','access_verified','limit_microusd','reserved_microusd','spent_microusd')} if budget else None
            admitted = budget_available(values, 1)
            inspected['x_access_verified'] = admitted
            inspected['x_budget_remaining_microusd'] = values['limit_microusd'] - values['reserved_microusd'] - values['spent_microusd'] if admitted else 0
        if account.platform == 'tiktok':
            inspected['tiktok_product_approved'] = self.config.access_verified is True and not self.config.blockers()
        return adapter.capabilities(inspected).model_dump(mode='json')

    def confirm(self, flow_id, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        def action():
            self._connection_budget(0)
            # Serialize new identity acquisition even when there is no account row yet.
            from ..connections.service import ConnectionService
            ConnectionService._controls_lock(self)
            row = self._flow(flow_id, actor, binding)
            if row.status != 'awaiting_confirmation':
                raise SocialError('OAUTH_STATE_USED', 'This identity has already been confirmed.', 409)
            grant = self.cipher.decrypt(row.id, self.purpose('pending'), row.key_version, row.encrypted_secret)
            if grant['subject'] != body.external_account_id:
                raise SocialError('IDENTITY_MISMATCH', 'Confirm the exact observed account identity.', 422)
            now = self.base.now()
            if datetime.fromisoformat(grant['expires_at']) <= now:
                raise SocialError('GRANT_EXPIRED', 'The pending grant expired. Reconnect.', 409)
            product = {'threads':'threads', 'x':'x_api_v2', 'tiktok':'tiktok_accounts_api'}[self.config.platform]
            account = self.db.scalar(select(SocialAccount).where(SocialAccount.platform == row.platform, SocialAccount.api_product == product, SocialAccount.external_account_id == grant['subject']))
            if account:
                account = self._lock_account(account.id)
                credential = self._credential(account.id)
                if credential.refresh_claim is not None:
                    # Unknown refresh completion remains sticky; never force clear it.
                    raise SocialError('CREDENTIAL_BUSY', 'A prior renewal has an unresolved outcome; reconcile its retained ownership before reconnecting.', 409)
                credential.version += 1
            else:
                account = SocialAccount(id=uuid4(), platform=row.platform, api_product=product, external_account_id=grant['subject'], connection_method=row.platform + '_oauth2', display_name=grant['display_name'])
                self.db.add(account)
                self.db.flush()
                credential = PlatformCredential(id=uuid4(), account_id=account.id, platform=row.platform, version=1)
                self.db.add(credential)
            credential.key_version, credential.encrypted_bundle = self.cipher.encrypt(credential.id, self.purpose('credential'), grant)
            credential.access_expires_at = datetime.fromisoformat(grant['expires_at'])
            credential.data_access_expires_at = datetime.fromisoformat(grant['data_access_expires_at']) if grant.get('data_access_expires_at') else None
            credential.refresh_expires_at = datetime.fromisoformat(grant['refresh_expires_at']) if grant.get('refresh_expires_at') else None
            credential.issued_at = datetime.fromisoformat(grant['issued_at'])
            credential.revoked_at = None
            credential.updated_at = now
            account.display_name, account.handle = grant['display_name'], grant['username']
            account.profile_url = (('https://www.threads.com/@' if row.platform == 'threads' else 'https://x.com/') + grant['username']) if grant['username'] else None
            account.granted_scopes, account.connection_state, account.publishing_enabled = grant['scopes'], 'connected', False
            account.capabilities_checked_at = account.last_api_success_at = now
            account.capability_snapshot = self._capabilities(account, grant['scopes'], now)
            row.status, row.encrypted_secret, row.updated_at = 'completed', None, now
            self._audit(actor, request_id, 'confirmed', account_id=account.id, reason=body.reason, details={'flow_id': str(row.id), 'credential_version': credential.version})
            from ..connections.service import ConnectionService
            return {'flow_id': str(row.id), 'account': ConnectionService._account_dto(self, account), 'credential_id': str(credential.id), 'credential_version': credential.version}
        return self._command(actor, binding, route, key, body, request_id, action)

    def material(self, account_id, expected_id=None, expected_version=None):
        """Call inside the worker's fenced admission transaction, never via browser."""
        self.config.require_ready()
        account = self.db.scalar(select(SocialAccount).where(SocialAccount.id == account_id).execution_options(populate_existing=True))
        if not account or account.platform != self.config.platform or account.connection_state != 'connected':
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'This provider account requires reconnecting.', 409)
        row = self._credential(account_id, expected_id, expected_version)
        if row.revoked_at or row.refresh_claim or utc(row.access_expires_at) <= self.base.now() or (row.data_access_expires_at and utc(row.data_access_expires_at) <= self.base.now()):
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'This provider credential is expired, revoked or has unresolved renewal ownership.', 409)
        bundle = self.cipher.decrypt(row.id, self.purpose('credential'), row.key_version, row.encrypted_bundle)
        if bundle.get('subject') != account.external_account_id or not set(self.config.scopes) <= set(bundle.get('scopes', ())):
            raise SocialError('CREDENTIAL_UNAVAILABLE', 'The saved provider grant no longer matches its account identity and required scopes.', 409)
        return bundle

    def _health(self, account, credential):
        return {'account_id': str(account.id), 'platform': account.platform, 'connection_state': account.connection_state, 'credential_id': str(credential.id), 'credential_version': credential.version, 'access_expires_at': iso(credential.access_expires_at), 'refresh_pending': credential.refresh_claim is not None, 'reconnect_required': credential.revoked_at is not None or credential.refresh_claim is not None or utc(credential.access_expires_at) <= self.base.now() or bool(credential.data_access_expires_at and utc(credential.data_access_expires_at) <= self.base.now()), 'publishing_enabled': account.publishing_enabled}

    def health(self, account_id):
        account = self.db.get(SocialAccount, account_id)
        if not account or account.platform != self.config.platform:
            raise SocialError('NOT_FOUND', 'This provider account was not found.', 404)
        return self._health(account, self._credential(account_id))

    def creator_settings(self, account_id):
        self.config.require_ready()
        if self.config.platform != 'tiktok':
            raise SocialError('UNSUPPORTED_PLATFORM', 'Creator privacy settings are specific to TikTok Accounts API.', 422)
        with self.db.begin():
            bundle = self.material(account_id)
            account = self.db.get(SocialAccount, account_id)
            credential = self._credential(account_id)
            credential_id, version = credential.id, credential.version
            subject = account.external_account_id
            display_name, handle = account.display_name, account.handle
        provider = self.provider_factory(self.config)
        try:
            settings = provider.creator_settings(bundle)
        finally:
            provider.close()
        # A disconnect or rotated grant during HTTP invalidates this observation.
        with self.db.begin():
            self.material(account_id, credential_id, version)
            checked = self.base.now()
        return {'account_id': str(account_id), 'external_account_id': subject, 'display_name': display_name, 'handle': handle, 'settings': settings.model_dump(mode='json'), 'checked_at': iso(checked), 'settings_hash': settings.bound_hash(subject), 'credential_version': version}

    def refresh(self, account_id, actor, binding, route, key, body, request_id):
        self.config.require_ready()
        with self.db.begin():
            receipt = self._receipt(actor, binding, route, key, body)
            if receipt:
                return receipt.response
            self._connection_budget(0)
            account = self._lock_account(account_id)
            credential = self._credential(account_id, body.expected_credential_id, body.expected_credential_version)
            if credential.refresh_claim or credential.revoked_at:
                raise SocialError('CREDENTIAL_BUSY', 'This credential has retained renewal ownership or is revoked.', 409)
            if account.connection_state not in {'connected', 'expired'}:
                raise SocialError('CREDENTIAL_UNAVAILABLE', 'A disconnected or blocked account cannot renew its grant.', 409)
            grant = self.cipher.decrypt(credential.id, self.purpose('credential'), credential.key_version, credential.encrypted_bundle)
            if grant['subject'] != account.external_account_id:
                raise SocialError('IDENTITY_MISMATCH', 'This credential differs from the saved account identity.', 409)
            if self.config.platform == 'threads' and (utc(credential.access_expires_at) <= self.base.now() or (credential.data_access_expires_at and utc(credential.data_access_expires_at) <= self.base.now())):
                raise SocialError('REFRESH_INELIGIBLE', 'Threads requires an unexpired token and data-access grant.', 409)
            if self.config.platform != 'threads' and (not grant.get('refresh_token') or (credential.refresh_expires_at and utc(credential.refresh_expires_at) <= self.base.now())):
                raise SocialError('GRANT_EXPIRED', 'A valid refresh grant is required. Reconnect.', 409)
            if self.config.platform == 'threads' and (self.base.now() - utc(credential.issued_at)).total_seconds() < 86400:
                raise SocialError('REFRESH_INELIGIBLE', 'Threads requires a long-lived token at least 24 hours old.', 409)
            claim, version, credential_id = uuid4(), credential.version, credential.id
            credential.refresh_claim = claim
            self._audit(actor, request_id, 'refresh_claimed', account_id=account_id, reason=body.reason)
        provider = self.provider_factory(self.config)
        try:
            renewed = provider.refresh(grant)
        finally:
            provider.close()
        def save():
            account = self._lock_account(account_id)
            current = self._credential(account_id, credential_id, version)
            if current.refresh_claim != claim:
                raise SocialError('CREDENTIAL_BUSY', 'Renewal ownership changed; retain the unresolved grant.', 409)
            current.key_version, current.encrypted_bundle = self.cipher.encrypt(current.id, self.purpose('credential'), renewed)
            current.version += 1
            current.access_expires_at = datetime.fromisoformat(renewed['expires_at'])
            current.data_access_expires_at = datetime.fromisoformat(renewed['data_access_expires_at']) if renewed.get('data_access_expires_at') else None
            current.refresh_expires_at = datetime.fromisoformat(renewed['refresh_expires_at']) if renewed.get('refresh_expires_at') else None
            current.issued_at = datetime.fromisoformat(renewed['issued_at'])
            current.refresh_claim = None
            account.granted_scopes = renewed['scopes']
            account.connection_state = 'connected'
            account.capability_snapshot = self._capabilities(account, renewed['scopes'], self.base.now())
            account.last_api_success_at = self.base.now()
            self._audit(actor, request_id, 'refreshed', account_id=account.id, reason=body.reason, details={'credential_version': current.version})
            return self._health(account, current)
        return self._command(actor, binding, route, key, body, request_id, save)

    def disconnect(self, account_id, actor, binding, route, key, body, request_id):
        # Local revocation works while disabled; never calls a provider or clears claims.
        def action():
            account = self._lock_account(account_id)
            current = self._credential(account_id, body.expected_credential_id, body.expected_credential_version)
            current.revoked_at, current.version = self.base.now(), current.version + 1
            account.publishing_enabled, account.connection_state = False, 'disconnected'
            self._audit(actor, request_id, 'disconnected_local', account_id=account.id, reason=body.reason)
            return self._health(account, current)
        return self._command(actor, binding, route, key, body, request_id, action)

    def rotate_key(self, account_id, actor, binding, route, key, body, request_id):
        # Local envelope rotation needs the stable key ring, never provider HTTP.
        def action():
            account = self._lock_account(account_id)
            current = self._credential(account_id, body.expected_credential_id, body.expected_credential_version)
            if current.refresh_claim is not None:
                raise SocialError('CREDENTIAL_BUSY', 'Resolve retained renewal ownership before rotating this envelope.', 409)
            prior_key = current.key_version
            current.key_version, current.encrypted_bundle = self.cipher.rotate(current.id, self.purpose('credential'), current.key_version, current.encrypted_bundle)
            current.version += 1
            current.updated_at = self.base.now()
            self._audit(actor, request_id, 'key_rotated', account_id=account.id, reason=body.reason, details={'previous_key_version': prior_key, 'key_version': current.key_version, 'credential_version': current.version})
            return self._health(account, current)
        return self._command(actor, binding, route, key, body, request_id, action)

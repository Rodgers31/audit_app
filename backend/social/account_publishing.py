"""Local admin account consent. Never calls a provider or changes global ceilings.

The controls row serializes toggles with connection/dispatch commands. Its existing
monotonic version prevents ABA without adding a second account version column.
The state digest additionally fences connection, credential and recovery changes.
"""
from collections.abc import Mapping
from uuid import UUID
from types import SimpleNamespace

from pydantic import StrictBool
from sqlalchemy import select, text, or_, func

from .contracts import Hash, PositiveVersion, Reason, StrictModel, canonical_hash
from .models import SocialAccount, SocialControls, SocialAuditEvent
from .service import SocialError, iso, utc
from .validation import capability_context, capability_for, registered_capability


class AccountPublishingCommand(StrictModel):
    expected_controls_version: PositiveVersion
    expected_state: Hash
    publishing_enabled: StrictBool
    reason: Reason


class AccountPublishingDTO(StrictModel):
    account_id: UUID
    publishing_enabled: StrictBool
    controls_version: PositiveVersion
    state_token: Hash
    enable_available: StrictBool
    enable_blockers: tuple[str, ...]
    global_publishing_enabled: StrictBool
    delivery_holds: tuple[str, ...]


def _controls(svc, lock):
    query = select(SocialControls).where(SocialControls.id == 1)
    row = svc.db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if row is None and lock:
        if svc.db.bind.dialect.name == 'postgresql':
            svc.db.execute(text('SELECT pg_advisory_xact_lock(6384952001)'))
            row = svc.db.scalar(query.with_for_update().execution_options(populate_existing=True))
        if row is None:
            row = SocialControls(id=1, version=1)
            svc.db.add(row)
            svc.db.flush()
    return row


CREDENTIAL_METADATA = ('id','version','created_at','updated_at','parent_credential_id','credential_kind','provider','platform',
    'revoked_at','access_expires_at','data_access_expires_at','refresh_lease_token','refresh_lease_expires_at','refresh_claim')


def _credential_rows(svc, account, lock):
    from .connections.models import SocialCredential
    from .platform_connections.models import PlatformCredential
    model = SocialCredential if account.platform in ('facebook', 'instagram') else PlatformCredential
    predicate = model.id == account.credential_id if model is SocialCredential else model.account_id == account.id
    def compact(model, predicate):
        query = select(*(getattr(model,name) for name in CREDENTIAL_METADATA if hasattr(model,name))).where(predicate)
        value = svc.db.execute(query.with_for_update() if lock else query).mappings().first()
        return SimpleNamespace(**value) if value else None
    credential = compact(model, predicate)
    parent = None
    if credential is not None and model is SocialCredential and credential.parent_credential_id:
        parent = compact(SocialCredential, SocialCredential.id == credential.parent_credential_id)
    return credential, parent


def _snapshot(row):
    if row is None:
        return None
    # Excludes ciphertext and keys. A digest binds metadata, not secret material.
    fields = CREDENTIAL_METADATA
    return {name: iso(value) if hasattr(value, 'tzinfo') else str(value) if isinstance(value, UUID) else value
            for name in fields if hasattr(row, name) for value in (getattr(row, name),)}


def _privacy_state(svc, account, page, parent):
    """Metadata-only consent guard; never decrypts or declares ownership.

    Indexed current User/Page ownership can identify unrelated retained events.
    A legacy grant without that index cannot dismiss same-app retained history.
    Unknown app namespaces are conservative only when history actually exists.
    """
    if account.platform not in ('facebook', 'instagram'):
        return None, None
    import re
    from .privacy.models import SocialPrivacyOwnership, SocialPrivacyReceipt
    pairs = {(item.id,item.version) for item in (page,parent) if item is not None}
    owners = []
    if pairs:
        query = select(SocialPrivacyOwnership.__table__).where(or_(*(
            (SocialPrivacyOwnership.credential_id == identifier) & (SocialPrivacyOwnership.credential_version == version)
            for identifier,version in pairs))).order_by(SocialPrivacyOwnership.id).limit(1001)
        owners = list(svc.db.execute(query).mappings())
    configured = getattr(svc,'privacy_app_id',None)
    configured = configured if type(configured) is str and re.fullmatch(r'[0-9]{1,64}',configured) else None
    apps = {o['app_id'] for o in owners}
    if configured is not None:
        apps.add(configured)
    query = select(SocialPrivacyReceipt.id,SocialPrivacyReceipt.app_id,SocialPrivacyReceipt.digest_version,
                   SocialPrivacyReceipt.subject_digest,SocialPrivacyReceipt.received_at,SocialPrivacyReceipt.state)
    if apps:
        query = query.where(SocialPrivacyReceipt.app_id.in_(apps))
    generation = parent.created_at if parent is not None else page.created_at if page is not None else None
    if generation is not None:
        query = query.where(func.julianday(SocialPrivacyReceipt.received_at) >= func.julianday(utc(generation).replace(microsecond=0))
            if svc.db.bind.dialect.name == 'sqlite' else SocialPrivacyReceipt.received_at >= generation)
    receipts = list(svc.db.execute(query.order_by(SocialPrivacyReceipt.id).limit(1001)).mappings())
    def normalized(row):
        return {name:iso(value) if hasattr(value,'tzinfo') else str(value) if isinstance(value,UUID) else value for name,value in row.items()}
    witness = {'app_id':configured,'owners':[normalized(o) for o in owners], 'receipts':[normalized(r) for r in receipts]}
    if len(owners)>1000:
        return 'PRIVACY_STATE_UNAVAILABLE', witness
    if not receipts:
        return None, witness
    if len(receipts)>1000 or len(apps)!=1 or page is None or parent is None:
        return 'PRIVACY_STATE_UNAVAILABLE', witness
    bindings = {}
    selected = set()
    for owner in owners:
        key = (owner['app_id'],owner['digest_version'],owner['subject_digest'])
        bindings.setdefault(key,set()).add(owner['credential_id'])
        if owner['credential_id']==page.id and owner['account_id']==account.id:
            selected.add(key)
    complete = {key for key,identifiers in bindings.items() if {page.id,parent.id} <= identifiers and key in selected}
    if not complete or set(bindings)!=complete:
        return 'PRIVACY_STATE_UNAVAILABLE', witness
    versions = {key[1] for key in complete}
    for receipt in receipts:
        if (receipt['app_id'],receipt['digest_version'],receipt['subject_digest']) in complete:
            return 'PRIVACY_GRANT_BLOCKED', witness
        if receipt['digest_version'] not in versions:
            return 'PRIVACY_STATE_UNAVAILABLE', witness
    return None, witness


def _platform_controls(controls, platform):
    if controls is None:
        return {}, False
    policy = controls.platform_controls
    if not isinstance(policy, dict):
        return {}, True
    if platform not in policy:
        return {}, False
    selected = policy[platform]
    if not isinstance(selected, dict):
        return {}, True
    if 'publishing_enabled' in selected and type(selected['publishing_enabled']) is not bool:
        return {}, True
    return selected, False


def _view(svc, account_id, lock=False):
    controls = _controls(svc, lock)
    query = select(SocialAccount).where(SocialAccount.id == account_id)
    account = svc.db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if account is None:
        raise SocialError('NOT_FOUND', 'This social account was not found.', 404)
    credential, parent = _credential_rows(svc, account, lock)
    now = svc.now()
    blockers = []
    platform_controls, platform_controls_unavailable = _platform_controls(controls, account.platform)
    if platform_controls_unavailable:
        blockers.append('PLATFORM_CONTROLS_UNAVAILABLE')
    if account.connection_state != 'connected':
        blockers.append('ACCOUNT_DISCONNECTED')
    context = capability_context(svc.db, account)
    registered = registered_capability(account, svc.available_adapters, context)
    caps = capability_for(account, svc.available_adapters, context)
    if (not isinstance(svc.available_adapters, Mapping) or not caps.eligible or not caps.adapter_available
            or caps.feature_states.get('publishing') not in ('supported', 'restricted', 'paid')
            or not set(caps.required_scopes) <= set(account.granted_scopes or ())):
        blockers.append('NATIVE_ADMISSION_UNAVAILABLE')
    if account.hold_reason:
        blockers.append('ACCOUNT_HELD')
    if account.publish_lease_token is not None or account.publish_lease_target_id is not None:
        blockers.append('DELIVERY_UNRESOLVED')
    credential_bad = credential is None
    if credential is not None:
        credential_bad = bool(credential.revoked_at or getattr(credential,'refresh_lease_token',None)
                              or getattr(credential,'refresh_claim',None))
        credential_bad |= any(value is not None and utc(value) <= now for value in
                              (credential.access_expires_at, credential.data_access_expires_at))
        if account.platform in ('facebook','instagram'):
            credential_bad |= credential.provider != 'meta' or credential.credential_kind != 'facebook_page'
            # Parent User access expiry affects discovery; it does not invent a
            # timed Page-token expiry. Revocation and unresolved ownership do.
            credential_bad |= parent is None or bool(parent and (parent.revoked_at or parent.refresh_lease_token
                                    or parent.provider != 'meta' or parent.credential_kind != 'facebook_user'
                                    or parent.data_access_expires_at is not None and utc(parent.data_access_expires_at) <= now))
        else:
            credential_bad |= credential.platform != account.platform
    if credential_bad:
        blockers.append('CREDENTIAL_UNAVAILABLE')
    privacy_problem, privacy_witness = _privacy_state(svc, account, credential, parent)
    if privacy_problem:
        blockers.append(privacy_problem)
    state = {name: iso(value) if hasattr(value, 'tzinfo') else str(value) if isinstance(value, UUID) else value
             for name in ('id','platform','api_product','external_account_id','connection_state','publishing_enabled',
                          'updated_at','credential_id','granted_scopes','capability_snapshot','hold_reason',
                          'publish_lease_target_id','publish_lease_token','publish_lease_expires_at')
             for value in (getattr(account,name),)}
    state['credential'], state['parent'] = _snapshot(credential), _snapshot(parent)
    state['controls_version'] = controls.version if controls else 1
    state['privacy'] = privacy_witness
    holds = []
    if privacy_problem:
        holds.append(privacy_problem)
    if not controls or not controls.publishing_enabled:
        holds.append('GLOBAL_PUBLISHING_DISABLED')
    if platform_controls_unavailable:
        holds.append('PLATFORM_CONTROLS_UNAVAILABLE')
    elif platform_controls.get('publishing_enabled') is False:
        holds.append('PLATFORM_PUBLISHING_DISABLED')
    if not registered.adapter_available:
        holds.append('NATIVE_RUNTIME_UNAVAILABLE')
    # Queue acceptance is separate from a live worker. The existing system
    # status endpoint reports heartbeat readiness at the moment of publication.
    return account, controls, {'account_id':str(account.id), 'publishing_enabled':bool(account.publishing_enabled),
        'controls_version':controls.version if controls else 1, 'state_token':canonical_hash(state),
        'enable_available':not blockers, 'enable_blockers':blockers,
        'global_publishing_enabled':bool(controls and controls.publishing_enabled), 'delivery_holds':holds}


def account_publishing(svc, account_id):
    return _view(svc, account_id)[2]


def set_account_publishing(svc, account_id, body):
    # Internal callers receive the same strict shape checks as HTTP callers.
    body = AccountPublishingCommand.model_validate(body.model_dump() if isinstance(body, AccountPublishingCommand) else body)
    # Require the final transaction witness even through non-HTTP callers.
    if svc._command_postconditions is None:
        raise SocialError('COMMAND_REQUIRED', 'Account publishing changes require a durable command transaction.', 503)
    account, controls, current = _view(svc, account_id, lock=True)
    if controls.version != body.expected_controls_version or current['state_token'] != body.expected_state:
        raise SocialError('VERSION_CONFLICT', 'Account publishing state changed. Refresh before updating.')
    if body.publishing_enabled and current['enable_blockers']:
        raise SocialError(current['enable_blockers'][0], 'This account is not ready to enable publishing. Refresh account readiness and resolve its reported blockers.')
    previous = account.publishing_enabled
    account.publishing_enabled = body.publishing_enabled
    account.updated_at = svc.now()
    controls.version += 1
    controls.updated_by, controls.updated_at = svc.actor, account.updated_at
    event = svc.audit('account.publishing_updated', previous=str(bool(previous)).lower(), new=str(body.publishing_enabled).lower(), reason=body.reason,
                     details={'publishing_enabled':body.publishing_enabled,'controls_version':controls.version})
    event.account_id = account.id
    svc.db.flush()
    observed = _view(svc, account_id)[2]
    if observed['publishing_enabled'] is not body.publishing_enabled or observed['controls_version'] != body.expected_controls_version + 1:
        raise SocialError('ACCOUNT_CONTROL_FAILED', 'The durable account publishing change could not be confirmed. The transaction was rolled back; retry the same command.', 503)
    expected_hash = canonical_hash(observed)
    audit_fields = ('id','post_id','target_id','account_id','actor_id','actor_kind','action',
                    'previous_state','new_state','reason','request_id')
    expected_audit = {field:getattr(event,field) for field in audit_fields}
    expected_audit_details = canonical_hash(event.details)
    def verify_committed_state():
        stored_audit = svc.db.execute(select(SocialAuditEvent.__table__).where(SocialAuditEvent.id == event.id)).mappings().first()
        if (stored_audit is None or any(stored_audit[field] != value for field,value in expected_audit.items())
                or canonical_hash(stored_audit['details']) != expected_audit_details):
            raise SocialError('ACCOUNT_CONTROL_FAILED', 'The durable account publishing audit could not be confirmed. The transaction was rolled back; retry the same command.', 503)
        if canonical_hash(_view(svc, account_id)[2]) != expected_hash:
            raise SocialError('ACCOUNT_CONTROL_FAILED', 'The durable account publishing state changed before its receipt could commit. The transaction was rolled back; retry the same command.', 503)
    svc._require_command_postcondition(verify_committed_state)
    return observed

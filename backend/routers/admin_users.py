"""Admin users: auth identities joined to profiles, with verified mutations."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from math import isfinite
from uuid import UUID

import httpx
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session

import admin_users_provider as supabase_admin
from admin_users_provider import record_admin_action
from supabase_auth import AdminUser, require_admin


class UsersRoute(APIRoute):
    """Keep private user responses uncacheable, including rejected requests."""
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handle(request):
            try:
                response = await original(request)
            except StarletteHTTPException as error:
                if error.status_code >= 500 and error.status_code not in {502, 503}:
                    error = HTTPException(503, 'User service is unavailable.', headers=error.headers)
                elif error.status_code >= 500:
                    error = HTTPException(error.status_code, 'User service is unavailable.', headers=error.headers)
                elif error.status_code in {401, 403}:
                    error.detail = 'Administrator access required.'
                response = await http_exception_handler(request, error)
            except RequestValidationError:
                response = JSONResponse(status_code=422, content={'detail': 'Invalid user request.'})
            except Exception:
                response = JSONResponse(status_code=503, content={'detail': 'User service is unavailable.'})
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Vary'] = 'Authorization'
            return response
        return handle


router = APIRouter(prefix='/api/v1/admin/users', tags=['Admin'],
                   dependencies=[Depends(require_admin)], route_class=UsersRoute)


class AdminUserSummary(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: List[str]
    created_at: Optional[datetime]
    last_sign_in_at: Optional[datetime]
    email_confirmed: bool
    banned_until: Optional[datetime]


class AdminUserList(BaseModel):
    users: List[AdminUserSummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class AdminUserDetail(AdminUserSummary):
    app_metadata: dict
    user_metadata: dict
    updated_at: Optional[datetime]


class AdminUserMutation(AdminUserDetail):
    ok: bool
    audit_recorded: bool


class AdminUserStats(BaseModel):
    total_users: int
    admin_users: int
    new_last_7_days: int
    new_last_30_days: int


class UpdateRolesBody(BaseModel):
    roles: List[str] = Field(max_length=32)


class SendResetBody(BaseModel):
    redirect_to: Optional[str] = Field(default=None, max_length=2048)


# The Auth API has no email-substring contract shared by all supported versions.
# Scan before filtering/pagination; never label a partial scan as an exact total.
_PROVIDER_PAGE_SIZE = 100
_MAX_PROVIDER_PAGES = 100
_KNOWN_ROLES = {'citizen', 'admin'}


def _bad_provider():
    raise HTTPException(502, 'User provider returned an invalid response.')


def _provider(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except supabase_admin.SupabaseAdminError as error:
        if error.status_code == 404:
            raise HTTPException(404, 'User or profile not found.') from None
        if error.status_code == 429:
            raise HTTPException(429, 'User provider rate limit reached. Try later.') from None
        if error.status_code == 503:
            raise HTTPException(503, 'User provider is unavailable. Try later.') from None
        raise HTTPException(502, 'User provider rejected the request.') from None
    except httpx.HTTPError:
        raise HTTPException(503, 'User provider is unavailable. Try later.') from None


def _id(value):
    if not isinstance(value, str):
        _bad_provider()
    try:
        return str(UUID(value))
    except ValueError:
        _bad_provider()


def _parse_iso(value) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, (str, datetime)):
        _bad_provider()
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        _bad_provider()


def _auth_user(value, expected_id=None):
    if not isinstance(value, dict):
        _bad_provider()
    _reject_failure(value)
    user = dict(value)
    user['id'] = _id(user.get('id'))
    if expected_id is not None and user['id'] != expected_id:
        _bad_provider()
    for field in ('email',):
        if user.get(field) is not None and not isinstance(user[field], str):
            _bad_provider()
    for field in ('created_at', 'updated_at', 'last_sign_in_at', 'banned_until', 'email_confirmed_at'):
        _parse_iso(user.get(field))
    for field in ('app_metadata', 'user_metadata'):
        if user.get(field) is not None and not isinstance(user[field], dict):
            _bad_provider()
        _safe_metadata(user.get(field) or {})
    return user


def _profile(value, expected_id):
    if not isinstance(value, dict) or _id(value.get('id')) != expected_id:
        _bad_provider()
    _reject_failure(value)
    roles = value.get('roles')
    if not isinstance(roles, list) or any(not isinstance(role, str) or not role.strip() for role in roles):
        _bad_provider()
    if value.get('display_name') is not None and not isinstance(value['display_name'], str):
        _bad_provider()
    return {**value, 'id': expected_id, 'roles': list(dict.fromkeys(roles))}


def _profile_map(user_ids):
    result = {}
    # Bound URL length and ensure provider row limits cannot silently drop roles.
    for offset in range(0, len(user_ids), _PROVIDER_PAGE_SIZE):
        batch = user_ids[offset:offset + _PROVIDER_PAGE_SIZE]
        rows = _provider(supabase_admin.get_profiles, batch)
        if not isinstance(rows, list):
            _bad_provider()
        for row in rows:
            if not isinstance(row, dict):
                _bad_provider()
            uid = _id(row.get('id'))
            if uid not in batch or uid in result:
                _bad_provider()
            result[uid] = _profile(row, uid)
    return result


def _all_users():
    users, seen = [], set()
    for page in range(1, _MAX_PROVIDER_PAGES + 1):
        response = _provider(supabase_admin.list_users, page=page, per_page=_PROVIDER_PAGE_SIZE)
        if not isinstance(response, dict) or not isinstance(response.get('users'), list):
            _bad_provider()
        _reject_failure(response)
        rows = response['users']
        if len(rows) > _PROVIDER_PAGE_SIZE:
            _bad_provider()
        for row in rows:
            user = _auth_user(row)
            if user['id'] in seen:
                raise HTTPException(503, 'User list changed while loading. Refresh to try again.')
            seen.add(user['id'])
            users.append(user)
        if len(rows) < _PROVIDER_PAGE_SIZE:
            return users
    raise HTTPException(503, 'User list exceeds the verified scan limit. Narrower provider query support is required.')


def _to_summary(auth_user, profile):
    return AdminUserSummary(id=auth_user['id'], email=auth_user.get('email'),
        display_name=(profile or {}).get('display_name'), roles=(profile or {}).get('roles', []),
        created_at=_parse_iso(auth_user.get('created_at')),
        last_sign_in_at=_parse_iso(auth_user.get('last_sign_in_at')),
        email_confirmed=auth_user.get('email_confirmed_at') is not None,
        banned_until=_parse_iso(auth_user.get('banned_until')))


_SENSITIVE_METADATA_KEYS = ('token', 'secret', 'password', 'credential', 'apikey',
                            'authorization', 'actionlink', 'emailotp', 'privatekey')


def _safe_metadata(value, depth=0):
    """Validate JSON metadata and strip credential fields at every depth."""
    if depth > 25:
        _bad_provider()
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _bad_provider()
            normalized = ''.join(character for character in key.lower() if character.isalnum())
            if not any(marker in normalized for marker in _SENSITIVE_METADATA_KEYS):
                result[key] = _safe_metadata(item, depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_metadata(item, depth + 1) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        try:
            if isfinite(value):
                return value
        except OverflowError:
            pass
    _bad_provider()


def _detail(auth_user, profile):
    return AdminUserDetail(**_to_summary(auth_user, profile).model_dump(),
        app_metadata=_safe_metadata(auth_user.get('app_metadata') or {}),
        user_metadata=_safe_metadata(auth_user.get('user_metadata') or {}),
        updated_at=_parse_iso(auth_user.get('updated_at')))


def _reject_failure(value):
    # HTTP 200 alone cannot override explicit rejection or malformed verdicts.
    if any(key in value for key in ('error', 'errors', 'error_code')):
        _bad_provider()
    if any(key in value and value[key] is not True for key in ('ok', 'success')):
        _bad_provider()


def _ack(value, expected_id=None):
    if not isinstance(value, dict):
        _bad_provider()
    _reject_failure(value)
    allowed = {'ok', 'success'} | ({'id'} if expected_id is not None else set())
    if set(value) - allowed:
        _bad_provider()
    if 'id' in value and _id(value['id']) != expected_id:
        _bad_provider()


def _delete_ack(value, expected_id):
    """Accept empty deletes and matching raw/wrapped Auth User responses."""
    if isinstance(value, dict):
        _reject_failure(value)
        if 'user' in value:
            if set(value) != {'user'}:
                _bad_provider()
            _auth_user(value['user'], expected_id)
            return
        if 'id' in value:
            _auth_user(value, expected_id)
            return
    _ack(value, expected_id)


@router.get('', response_model=AdminUserList, summary='List users')
def list_users(q: Optional[str] = Query(None, max_length=320),
                     page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    users = _all_users()
    needle = (q or '').strip().casefold()
    if needle:
        users = [user for user in users if needle in (user.get('email') or '').casefold()]
    total = len(users)
    start = (page - 1) * page_size
    selected = users[start:start + page_size]
    profiles = _profile_map([user['id'] for user in selected])
    return AdminUserList(users=[_to_summary(user, profiles.get(user['id'])) for user in selected],
                         total=total, page=page, page_size=page_size, has_more=start + page_size < total)


@router.get('/stats', response_model=AdminUserStats, summary='User stats summary')
def user_stats():
    users = _all_users()
    profiles = _profile_map([user['id'] for user in users])
    now = datetime.now(timezone.utc)
    created = [_parse_iso(user.get('created_at')) for user in users]
    return AdminUserStats(total_users=len(users),
        admin_users=sum('admin' in profiles.get(user['id'], {}).get('roles', []) for user in users),
        new_last_7_days=sum(date is not None and now - timedelta(days=7) <= date <= now for date in created),
        new_last_30_days=sum(date is not None and now - timedelta(days=30) <= date <= now for date in created))


@router.get('/{user_id}', response_model=AdminUserDetail, summary='Get user details')
def get_user(user_id: UUID):
    uid = str(user_id)
    user = _auth_user(_provider(supabase_admin.get_user, uid), uid)
    return _detail(user, _profile_map([uid]).get(uid))


@router.patch('/{user_id}/roles', response_model=AdminUserMutation, summary='Update user roles (profiles.roles)')
def update_user_roles(user_id: UUID, body: UpdateRolesBody,
                            actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    uid = str(user_id)
    new_roles = list(dict.fromkeys(role.strip() for role in body.roles))
    if any(not role for role in new_roles):
        raise HTTPException(422, 'Roles must be non-empty strings.')
    if UUID(actor.id) == user_id and 'admin' not in new_roles:
        raise HTTPException(400, 'You cannot remove the admin role from yourself.')
    # Load and validate identity before the irreversible provider call. Build the
    # response from its returned row; no fallible follow-up read after mutation.
    user = _auth_user(_provider(supabase_admin.get_user, uid), uid)
    old_profile = _provider(supabase_admin.get_profile, uid)
    if old_profile is None:
        raise HTTPException(404, 'Profile not found.')
    old_profile = _profile(old_profile, uid)
    if any(role not in _KNOWN_ROLES and role not in old_profile['roles'] for role in new_roles):
        raise HTTPException(422, 'Unknown roles cannot be granted.')
    updated = _profile(_provider(supabase_admin.update_profile_roles, uid, new_roles), uid)
    if set(updated['roles']) != set(new_roles):
        _bad_provider()
    audited = record_admin_action(db, actor=actor, action='users.update_roles', target_type='user',
                                 target_id=uid, payload={'old': old_profile['roles'], 'new': updated['roles']})
    return AdminUserMutation(**_detail(user, updated).model_dump(), ok=True, audit_recorded=audited is True)


@router.delete('/{user_id}', summary='Delete a user')
def delete_user(user_id: UUID, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    uid = str(user_id)
    if UUID(actor.id) == user_id:
        raise HTTPException(400, 'You cannot delete yourself.')
    snapshot = _auth_user(_provider(supabase_admin.get_user, uid), uid)
    _delete_ack(_provider(supabase_admin.delete_user, uid), uid)
    audited = record_admin_action(db, actor=actor, action='users.delete', target_type='user', target_id=uid,
                                 payload={'deleted_email': snapshot.get('email'), 'deleted_created_at': snapshot.get('created_at')})
    return {'ok': True, 'audit_recorded': audited is True}


@router.post('/{user_id}/send-reset', summary='Request password-reset email')
def send_reset(user_id: UUID, body: SendResetBody,
                     actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    uid = str(user_id)
    user = _auth_user(_provider(supabase_admin.get_user, uid), uid)
    email = user.get('email')
    if not email:
        raise HTTPException(400, 'User has no email address.')
    _ack(_provider(supabase_admin.send_password_reset, email, redirect_to=body.redirect_to))
    # Redirect URLs may contain tokens. Record the target, never arbitrary URLs.
    audited = record_admin_action(db, actor=actor, action='users.send_reset', target_type='user',
                                 target_id=uid, payload={'email': email})
    return {'ok': True, 'email': email, 'audit_recorded': audited is True}

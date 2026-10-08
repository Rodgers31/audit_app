"""Users-only provider transport and verifiable audit persistence.

Keeps Supabase credentials server-side and never returns raw provider errors or
recovery tokens to a caller. The shared auth provider remains unchanged.
"""
import logging
from typing import Optional

import httpx
from supabase_admin import SupabaseAdminError, _config, _headers

logger = logging.getLogger(__name__)


def _request(method, path, *, headers=None, **kwargs):
    base, _ = _config()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.request(method, base + path, headers={**_headers(), **(headers or {})}, **kwargs)
        if not 200 <= response.status_code < 300:
            raise SupabaseAdminError(response.status_code, None)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
    except httpx.HTTPError:
        raise SupabaseAdminError(503, None) from None
    except ValueError:
        raise SupabaseAdminError(502, None) from None


def list_users(*, page=1, per_page=100):
    return _request('GET', '/auth/v1/admin/users', params={'page': page, 'per_page': per_page})


def get_user(user_id):
    return _request('GET', f'/auth/v1/admin/users/{user_id}')


def get_profiles(user_ids):
    if not user_ids:
        return []
    return _request('GET', '/rest/v1/profiles', params={
        'select': 'id,display_name,roles', 'id': f'in.({",".join(user_ids)})',
    })


def get_profile(user_id):
    rows = get_profiles([user_id])
    if not isinstance(rows, list) or len(rows) > 1:
        raise SupabaseAdminError(502, None)
    return rows[0] if rows else None


def update_profile_roles(user_id, roles):
    rows = _request('PATCH', '/rest/v1/profiles', params={'id': f'eq.{user_id}'},
                    json={'roles': roles}, headers={'Prefer': 'return=representation'})
    if not isinstance(rows, list) or len(rows) != 1:
        raise SupabaseAdminError(502, None)
    return rows[0]


def delete_user(user_id):
    return _request('DELETE', f'/auth/v1/admin/users/{user_id}')


def send_password_reset(email, redirect_to: Optional[str] = None):
    params = {'redirect_to': redirect_to} if redirect_to else {}
    return _request('POST', '/auth/v1/recover', params=params, json={'email': email})


def record_admin_action(db, *, actor, action, target_type=None, target_id=None, payload=None) -> bool:
    """Report audit commit separately from an already accepted provider mutation."""
    from database import SessionLocal
    from models import AdminAuditLog
    del db
    session = None
    try:
        session = SessionLocal()
        session.add(AdminAuditLog(actor_id=actor.id, actor_email=actor.email,
                                 action=action, target_type=target_type,
                                 target_id=target_id, payload=dict(payload or {})))
        session.commit()
        return True
    except Exception:
        # Never log exception text, SQL parameters or provider responses.
        logger.error('Users audit persistence failed', extra={'action': action, 'target_id': target_id})
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        return False
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

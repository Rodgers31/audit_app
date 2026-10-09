"""Users-lane behavioral boundaries: inert provider, audit and auth identities.

These tests mount the actual users router. No main-app startup, database
connection, mail request or real identity is needed. The provider interface
is intentionally fake; provider transport tests below use memory responses.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

import database
import supabase_admin as shared_provider
import supabase_auth
from routers import admin_users


ACTOR = "00000000-0000-4000-8000-000000000001"
TARGET = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
ROOT = "/api/v1/admin/users"


def identity(user_id, email=None, **extra):
    return {
        "id": user_id,
        "email": email or f"fixture-{user_id[-4:]}@example.invalid",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "email_confirmed_at": None,
        "app_metadata": {},
        "user_metadata": {},
        **extra,
    }


class InertUsersProvider:
    def __init__(self):
        self.users = [identity(ACTOR), identity(TARGET)]
        self.profiles = {
            ACTOR: {"id": ACTOR, "roles": ["admin"], "display_name": "Fixture admin"},
            TARGET: {"id": TARGET, "roles": ["citizen"], "display_name": "Fixture citizen"},
        }
        self.calls = []
        self.overrides = {}

    def result(self, operation, fallback):
        value = self.overrides.get(operation, fallback)
        if isinstance(value, BaseException):
            raise value
        return deepcopy(value)

    def list_users(self, *, page=1, per_page=50):
        self.calls.append(("list", page, per_page))
        return self.result("list", {"users": self.users[(page - 1) * per_page:page * per_page]})

    def get_user(self, user_id):
        self.calls.append(("get_user", user_id))
        matches = [user for user in self.users if user["id"] == user_id]
        fallback = matches[0] if matches else shared_provider.SupabaseAdminError(404, {"message": "not found"})
        return self.result("get_user", fallback)

    def get_profiles(self, user_ids):
        self.calls.append(("profiles", tuple(user_ids)))
        return self.result("profiles", [self.profiles[user_id] for user_id in user_ids if user_id in self.profiles])

    def get_profile(self, user_id):
        self.calls.append(("profile", user_id))
        return self.result("profile", self.profiles.get(user_id))

    def update_profile_roles(self, user_id, roles):
        self.calls.append(("update_roles", user_id, tuple(roles)))
        if "update_roles" in self.overrides:
            return self.result("update_roles", None)
        if user_id not in self.profiles:
            raise shared_provider.SupabaseAdminError(404, "profile not found")
        self.profiles[user_id]["roles"] = list(roles)
        return deepcopy(self.profiles[user_id])

    def delete_user(self, user_id):
        self.calls.append(("delete", user_id))
        if "delete" in self.overrides:
            return self.result("delete", None)
        self.users = [user for user in self.users if user["id"] != user_id]
        self.profiles.pop(user_id, None)
        return {"id": user_id}

    def generate_recovery_link(self, email, redirect_to=None):
        self.calls.append(("generate_link", email, redirect_to))
        return self.result("generate_link", {"action_link": "https://example.invalid/private-fixture-token"})

    def send_password_reset(self, email, redirect_to=None):
        self.calls.append(("recover", email, redirect_to))
        return self.result("recover", {})

    def count_profiles(self, **filters):
        self.calls.append(("count_profiles", filters))
        if filters.get("column") == "roles":
            count = sum("admin" in row["roles"] for row in self.profiles.values())
        else:
            count = len(self.profiles)
        return self.result("count_profiles", count)


@pytest.fixture
def harness(monkeypatch):
    provider = InertUsersProvider()
    # Patch the router's provider alias: the owned helper can replace the shared
    # client without coupling these behavioral tests to its implementation.
    for name in (
        "list_users", "get_user", "get_profiles", "get_profile",
        "update_profile_roles", "delete_user", "generate_recovery_link",
        "send_password_reset", "count_profiles",
    ):
        monkeypatch.setattr(admin_users.supabase_admin, name, getattr(provider, name), raising=False)

    actor = supabase_auth.AdminUser(id=ACTOR, email="admin@example.invalid", roles=["admin"])
    app = FastAPI()
    app.include_router(admin_users.router)
    app.dependency_overrides[supabase_auth.get_current_user] = lambda: actor
    app.dependency_overrides[database.get_db] = lambda: object()
    audits = []

    def audit(_db, **details):
        audits.append(deepcopy(details))
        return True

    monkeypatch.setattr(admin_users, "record_admin_action", audit)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(app=app, client=client, provider=provider, actor=actor, audits=audits)


@pytest.mark.parametrize("method,path,body", [
    ("GET", ROOT, None),
    ("GET", ROOT + "/stats", None),
    ("GET", ROOT + "/" + TARGET, None),
    ("PATCH", ROOT + "/" + TARGET + "/roles", {"roles": ["admin"]}),
    ("DELETE", ROOT + "/" + TARGET, None),
    ("POST", ROOT + "/" + TARGET + "/send-reset", {}),
])
def test_unauthenticated_call_never_reaches_provider(harness, method, path, body):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    response = harness.client.request(method, path, json=body)
    assert response.status_code in (401, 403)
    assert harness.provider.calls == []
    assert harness.audits == []


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None), ("GET", "/stats", None), ("GET", "/" + TARGET, None),
    ("PATCH", "/" + TARGET + "/roles", {"roles": ["admin"]}),
    ("DELETE", "/" + TARGET, None), ("POST", "/" + TARGET + "/send-reset", {}),
])
def test_forbidden_citizen_never_reaches_provider(harness, method, suffix, body):
    harness.actor.roles = ["citizen"]
    response = harness.client.request(method, ROOT + suffix, json=body)
    assert response.status_code == 403
    assert harness.provider.calls == []
    assert harness.audits == []


def test_expired_signed_token_never_reaches_provider(harness, monkeypatch):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "inert-test-secret-not-a-production-secret")
    token = jwt.encode(
        {"sub": ACTOR, "aud": "authenticated", "exp": datetime.now(timezone.utc) - timedelta(seconds=60)},
        "inert-test-secret-not-a-production-secret", algorithm="HS256",
    )
    response = harness.client.get(ROOT, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert harness.provider.calls == []


def test_malformed_token_never_reaches_provider(harness):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    response = harness.client.get(ROOT, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert harness.provider.calls == []


def test_list_returns_exact_population_and_no_phantom_next_page(harness):
    response = harness.client.get(ROOT, params={"page_size": 2})
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["has_more"] is False


def test_search_finds_match_beyond_first_provider_page(harness):
    harness.provider.users = [
        identity(str(UUID(int=index + 10)), email=f"ordinary-{index}@example.invalid")
        for index in range(105)
    ]
    harness.provider.users[-1]["email"] = "Needle@example.invalid"
    response = harness.client.get(ROOT, params={"q": " needle ", "page_size": 2})
    assert response.status_code == 200
    assert [row["email"] for row in response.json()["users"]] == ["Needle@example.invalid"]
    assert response.json()["total"] == 1
    assert response.json()["has_more"] is False


def test_page_beyond_population_has_exact_total_and_is_empty(harness):
    response = harness.client.get(ROOT, params={"page": 8, "page_size": 2})
    assert response.status_code == 200
    assert response.json()["users"] == []
    assert response.json()["total"] == 2
    assert response.json()["has_more"] is False


def test_statistics_share_auth_population_and_exclude_orphan_profiles(harness):
    harness.provider.profiles[OTHER] = {"id": OTHER, "roles": ["admin"]}
    response = harness.client.get(ROOT + "/stats")
    assert response.status_code == 200
    assert response.json() == {"total_users": 2, "admin_users": 1, "new_last_7_days": 2, "new_last_30_days": 2}


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None), ("PATCH", "/roles", {"roles": ["admin"]}),
    ("DELETE", "", None), ("POST", "/send-reset", {}),
])
@pytest.mark.parametrize("bad_id", ["not-a-uuid", "null", "00000000-0000-4000-8000-000000000002?roles=admin"])
def test_malformed_user_id_is_rejected_before_provider(harness, method, suffix, body, bad_id):
    response = harness.client.request(method, ROOT + "/" + bad_id.replace("?", "%3F") + suffix, json=body)
    assert response.status_code == 422
    assert harness.provider.calls == []
    assert harness.audits == []


@pytest.mark.parametrize("roles", [["superadmin"], ["ADMIN"], ["admin", "unknown"], [" "], [None]])
def test_unknown_or_malformed_roles_are_rejected_without_mutation(harness, roles):
    response = harness.client.patch(ROOT + "/" + TARGET + "/roles", json={"roles": roles})
    assert response.status_code == 422
    assert not any(call[0] == "update_roles" for call in harness.provider.calls)
    assert harness.audits == []


def test_empty_roles_remains_supported_for_other_user(harness):
    response = harness.client.patch(ROOT + "/" + TARGET + "/roles", json={"roles": []})
    assert response.status_code == 200
    assert response.json()["roles"] == []


def test_existing_legacy_role_can_be_preserved_without_allowing_new_legacy_role(harness):
    harness.provider.profiles[TARGET]["roles"] = ["citizen", "legacy-auditor"]
    response = harness.client.patch(ROOT + "/" + TARGET + "/roles", json={"roles": ["admin", "legacy-auditor"]})
    assert response.status_code == 200
    assert set(response.json()["roles"]) == {"admin", "legacy-auditor"}


def test_admin_cannot_demote_self(harness):
    response = harness.client.patch(ROOT + "/" + ACTOR + "/roles", json={"roles": ["citizen"]})
    assert response.status_code == 400
    assert not any(call[0] == "update_roles" for call in harness.provider.calls)


def test_admin_cannot_delete_self(harness):
    response = harness.client.delete(ROOT + "/" + ACTOR)
    assert response.status_code == 400
    assert not any(call[0] == "delete" for call in harness.provider.calls)


@pytest.mark.parametrize("method,suffix,body", [
    ("PATCH", "/roles", {"roles": []}), ("DELETE", "", None),
])
def test_self_protection_canonicalizes_equivalent_uuid(harness, method, suffix, body):
    # UUID representations without hyphens remain valid UUIDs and refer to
    # exactly the same provider identity, even though the strings differ.
    response = harness.client.request(method, ROOT + "/" + UUID(ACTOR).hex + suffix, json=body)
    assert response.status_code == 400
    assert not any(call[0] in ("update_roles", "delete") for call in harness.provider.calls)


def test_repeat_delete_reports_not_found_without_second_mutation(harness):
    first = harness.client.delete(ROOT + "/" + TARGET)
    second = harness.client.delete(ROOT + "/" + TARGET)
    assert first.status_code == 200
    assert second.status_code == 404
    assert sum(call[0] == "delete" for call in harness.provider.calls) == 1
    assert len(harness.audits) == 1


def test_repeat_role_update_returns_verified_state(harness):
    for _ in range(2):
        response = harness.client.patch(ROOT + "/" + TARGET + "/roles", json={"roles": ["admin"]})
        assert response.status_code == 200
        assert response.json()["roles"] == ["admin"]
        assert response.json()["audit_recorded"] is True


@pytest.mark.parametrize("provider_ack", [None, {}, {"id": OTHER, "roles": ["admin"]}, {"id": TARGET, "roles": ["citizen"]}])
def test_roles_do_not_report_success_for_unverified_provider_result(harness, provider_ack):
    harness.provider.overrides["update_roles"] = provider_ack
    response = harness.client.patch(ROOT + "/" + TARGET + "/roles", json={"roles": ["admin"]})
    assert response.status_code == 502
    assert harness.audits == []


def test_reset_requests_provider_mail_instead_of_only_generating_link(harness):
    response = harness.client.post(ROOT + "/" + TARGET + "/send-reset", json={})
    assert response.status_code == 200
    assert any(call[0] == "recover" for call in harness.provider.calls)
    assert not any(call[0] == "generate_link" for call in harness.provider.calls)
    assert response.json()["audit_recorded"] is True
    assert "action_link" not in response.text
    assert "private-fixture-token" not in response.text


@pytest.mark.parametrize("provider_ack", [None, {"error": "rejected"}, {"ok": False}, {"id": OTHER}])
def test_delete_does_not_report_success_for_failed_or_wrong_identity_ack(harness, provider_ack):
    harness.provider.overrides["delete"] = provider_ack
    response = harness.client.delete(ROOT + "/" + TARGET)
    assert response.status_code == 502
    assert harness.audits == []


@pytest.mark.parametrize("provider_ack", [None, {"error": "rejected"}, {"ok": False}])
def test_reset_does_not_report_success_for_failed_provider_ack(harness, provider_ack):
    harness.provider.overrides["recover"] = provider_ack
    harness.provider.overrides["generate_link"] = provider_ack
    response = harness.client.post(ROOT + "/" + TARGET + "/send-reset", json={})
    assert response.status_code == 502
    assert harness.audits == []


def test_reset_user_without_email_is_rejected_without_mail(harness):
    harness.provider.users[1]["email"] = None
    response = harness.client.post(ROOT + "/" + TARGET + "/send-reset", json={})
    assert response.status_code == 400
    assert not any(call[0] in ("recover", "generate_link") for call in harness.provider.calls)
    assert harness.audits == []


def test_repeated_provider_page_does_not_certify_global_total(harness):
    harness.provider.overrides["list"] = {"users": [identity(str(UUID(int=index + 10))) for index in range(100)]}
    response = harness.client.get(ROOT)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")


def test_duplicate_provider_identity_does_not_certify_global_total(harness):
    harness.provider.users = [identity(TARGET), identity(TARGET)]
    response = harness.client.get(ROOT)
    assert response.status_code == 503


@pytest.mark.parametrize("profile_rows", [[{"id": OTHER, "roles": ["admin"]}], [{"id": TARGET, "roles": ["admin"]}, {"id": TARGET, "roles": ["citizen"]}]])
def test_wrong_or_duplicate_profile_identity_is_rejected(harness, profile_rows):
    harness.provider.overrides["profiles"] = profile_rows
    response = harness.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 502


@pytest.mark.parametrize("operation,method,suffix,body", [
    ("delete", "DELETE", "", None),
    ("recover", "POST", "/send-reset", {}),
    ("update_roles", "PATCH", "/roles", {"roles": ["admin"]}),
])
def test_provider_rejection_is_sanitized_and_not_audited(harness, operation, method, suffix, body):
    error = shared_provider.SupabaseAdminError(401, {"message": "fixture provider credential error", "access_token": "inert-sensitive-marker"})
    harness.provider.overrides[operation] = error
    # Baseline incorrectly calls generate_link, so retain the same rejection
    # for both mail paths until the owned mail helper is wired.
    if operation == "recover":
        harness.provider.overrides["generate_link"] = error
    response = harness.client.request(method, ROOT + "/" + TARGET + suffix, json=body)
    assert response.status_code == 502
    assert "inert-sensitive-marker" not in response.text
    assert harness.audits == []


@pytest.mark.parametrize("operation,path", [("list", ROOT), ("get_user", ROOT + "/" + TARGET)])
def test_transport_failure_is_recoverable_json(harness, operation, path):
    harness.provider.overrides[operation] = httpx.ConnectError("fixture transport unavailable")
    response = harness.client.get(path)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert harness.audits == []


@pytest.mark.parametrize("payload", [None, [], {}, {"users": None}, {"users": "not-a-list"}, {"users": [None]}, {"users": [{"id": TARGET, "email": 7}]}])
def test_malformed_provider_list_never_certifies_empty_or_success(harness, payload):
    harness.provider.overrides["list"] = payload
    response = harness.client.get(ROOT)
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("payload", [None, {}, {"id": OTHER}, identity(TARGET, email=7), identity(TARGET, app_metadata=[]), identity(TARGET, created_at="not-a-date")])
def test_malformed_provider_detail_is_rejected(harness, payload):
    harness.provider.overrides["get_user"] = payload
    response = harness.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 502


@pytest.mark.parametrize("roles", ["admin", {"admin": True}, [True], ["admin", None]])
def test_malformed_profile_roles_are_rejected(harness, roles):
    harness.provider.overrides["profiles"] = [{"id": TARGET, "roles": roles}]
    response = harness.client.get(ROOT + "/" + TARGET)
    assert response.status_code == 502


@pytest.mark.parametrize("method,suffix,body", [
    ("DELETE", "", None), ("POST", "/send-reset", {}),
    ("PATCH", "/roles", {"roles": ["admin"]}),
])
def test_committed_provider_mutation_discloses_audit_failure(harness, monkeypatch, method, suffix, body):
    monkeypatch.setattr(admin_users, "record_admin_action", lambda _db, **_details: False)
    response = harness.client.request(method, ROOT + "/" + TARGET + suffix, json=body)
    assert response.status_code == 200
    assert response.json()["audit_recorded"] is False
    assert response.json()["ok"] is True


@pytest.mark.parametrize("audit_result", [None, {"success": False}, "false"])
def test_truthy_audit_failure_is_not_certified_as_recorded(harness, monkeypatch, audit_result):
    monkeypatch.setattr(admin_users, "record_admin_action", lambda _db, **_details: audit_result)
    response = harness.client.delete(ROOT + "/" + TARGET)
    assert response.status_code == 200
    assert response.json()["audit_recorded"] is False


def test_actual_audit_writer_reports_failed_commit(monkeypatch):
    class FailingAuditSession:
        def add(self, row):
            pass

        def commit(self):
            raise RuntimeError("inert fixture audit commit rejected")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(database, "SessionLocal", FailingAuditSession)
    result = admin_users.record_admin_action(
        object(), actor=supabase_auth.AdminUser(id=ACTOR, email=None, roles=["admin"]),
        action="users.fixture", target_type="user", target_id=TARGET,
    )
    assert result is False


def test_shared_auth_rejects_malformed_role_mapping(harness, monkeypatch):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "inert-test-secret-not-a-production-secret")
    monkeypatch.setattr(shared_provider, "get_profile", lambda _uid: {"id": ACTOR, "roles": {"admin": False}})
    token = jwt.encode(
        {"sub": ACTOR, "aud": "authenticated", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "inert-test-secret-not-a-production-secret", algorithm="HS256",
    )
    response = harness.client.get(ROOT, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 403


def test_provider_role_transport_merges_prefer_header_once(monkeypatch):
    """Baseline shared provider raises TypeError before any PATCH request.

    Once the router uses its owned provider this exercises that client; the
    shared defect remains coordinator-owned and is not edited here.
    """
    requests = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            return httpx.Response(200, json=[{"id": TARGET, "roles": ["admin"]}])

    monkeypatch.setenv("SUPABASE_URL", "https://users-fixture.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "inert-fixture-service-role-key")
    monkeypatch.setattr(httpx, "Client", Client)
    row = admin_users.supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert row["roles"] == ["admin"]
    assert len(requests) == 1
    assert requests[0][2]["headers"]["Prefer"] == "return=representation"
    assert requests[0][2]["headers"]["Authorization"] == "Bearer inert-fixture-service-role-key"

@pytest.mark.parametrize('path', [ROOT, ROOT + '/stats', ROOT + '/' + TARGET])
def test_sensitive_read_success_is_not_stored(harness, path):
    response = harness.client.get(path)
    assert response.headers.get('cache-control') == 'no-store'

@pytest.mark.parametrize('failure', ['unauthenticated', 'forbidden', 'malformed', 'unavailable'])
def test_sensitive_error_response_is_not_stored(harness, failure):
    path = ROOT
    if failure == 'unauthenticated':
        harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    elif failure == 'forbidden':
        harness.actor.roles = ['citizen']
    elif failure == 'malformed':
        path += '/not-a-uuid'
    else:
        harness.provider.overrides['list'] = httpx.ConnectError('inert transport')
    response = harness.client.get(path)
    assert response.status_code >= 400
    assert response.headers.get('cache-control') == 'no-store'

@pytest.mark.parametrize('wrapped', [False, True])
def test_delete_accepts_verified_provider_user_response(harness, wrapped):
    result = identity(TARGET)
    harness.provider.overrides['delete'] = {'user': result} if wrapped else result
    response = harness.client.delete(ROOT + '/' + TARGET)
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'audit_recorded': True}
    assert len(harness.audits) == 1

@pytest.mark.parametrize('result', [{'user': identity(OTHER)}, {'user': None}, {'user': identity(TARGET), 'ok': False}])
def test_delete_rejects_unverified_wrapped_user_response(harness, result):
    harness.provider.overrides['delete'] = result
    response = harness.client.delete(ROOT + '/' + TARGET)
    assert response.status_code == 502
    assert harness.audits == []

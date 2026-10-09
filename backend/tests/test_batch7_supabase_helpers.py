"""Legacy compatibility helpers exercised through real in-memory HTTP transport."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import httpx
import pytest

import supabase_admin


TARGET = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SERVICE_KEY = "inert-batch7-service-key"


@pytest.fixture
def memory(monkeypatch):
    state = SimpleNamespace(
        requests=[],
        response=httpx.Response(200, json=[{"id": TARGET, "roles": ["admin"]}]),
    )

    def transport(request):
        state.requests.append(request)
        if isinstance(state.response, Exception):
            raise state.response
        return state.response

    real_client = httpx.Client
    monkeypatch.setenv("SUPABASE_URL", "https://batch7-helper.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    yield state


def test_role_update_requires_matching_provider_acknowledgment(memory):
    try:
        row = supabase_admin.update_profile_roles(TARGET, ["admin"])
    except TypeError:
        assert len(memory.requests) == 0, "Baseline duplicate keyword must precede transport"
        raise
    assert row == {"id": TARGET, "roles": ["admin"]}
    assert len(memory.requests) == 1
    request = memory.requests[0]
    assert request.method == "PATCH"
    assert request.url.path == "/rest/v1/profiles"
    assert request.url.params == httpx.QueryParams({"id": "eq." + TARGET})
    assert json.loads(request.content) == {"roles": ["admin"]}
    assert request.headers.get_list("prefer") == ["return=representation"]
    assert request.headers.get_list("apikey") == [SERVICE_KEY]
    assert request.headers.get_list("authorization") == ["Bearer " + SERVICE_KEY]


@pytest.mark.parametrize("filtered", [False, True])
def test_count_profiles_remains_a_passing_transport_control(memory, filtered):
    memory.response = httpx.Response(206, json=[{"id": TARGET}], headers={"Content-Range": "0-0/3"})
    filters = {"column": "roles", "op": "cs", "value": "{admin}"} if filtered else {}
    assert supabase_admin.count_profiles(**filters) == 3
    assert len(memory.requests) == 1
    request = memory.requests[0]
    assert request.method == "GET"
    assert request.url.params.get("select") == "id"
    assert request.url.params.get("roles") == ("cs.{admin}" if filtered else None)
    assert request.headers.get_list("prefer") == ["count=exact"]
    assert request.headers.get_list("range") == ["0-0"]
    assert request.headers.get_list("apikey") == [SERVICE_KEY]
    assert request.headers.get_list("authorization") == ["Bearer " + SERVICE_KEY]


@pytest.mark.parametrize("payload", [
    None, {}, "unexpected", 1, True,
    [{"id": TARGET}],
    [{"roles": ["admin"]}],
    [{"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "roles": ["admin"]}],
    [{"id": TARGET, "roles": ["citizen"]}],
    [{"id": TARGET, "roles": "admin"}],
    [{"id": TARGET, "roles": None}],
    [{"id": TARGET, "roles": {"admin": True}}],
    [None], ["unexpected"], [True],
    [{"id": TARGET, "roles": ["admin"]}, {"id": TARGET, "roles": ["admin"]}],
])
def test_unverified_role_acknowledgment_cannot_report_success(memory, payload):
    memory.response = httpx.Response(200, json=payload)
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == 502
    assert error.value.body is None
    assert len(memory.requests) == 1


def test_missing_profile_preserves_not_found_contract(memory):
    memory.response = httpx.Response(200, json=[])
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == 404
    assert len(memory.requests) == 1


@pytest.mark.parametrize("status,content", [(200, b"{broken"), (200, b""), (204, b"")])
def test_absent_or_invalid_json_does_not_acknowledge_role_change(memory, status, content):
    memory.response = httpx.Response(status, content=content)
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == 502
    assert error.value.body is None
    assert len(memory.requests) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 404, 409, 429, 500, 503])
def test_upstream_status_never_becomes_success(memory, status):
    memory.response = httpx.Response(status, json=[{"id": TARGET, "roles": ["admin"]}])
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == status
    assert len(memory.requests) == 1


@pytest.mark.parametrize("field,value", [
    ("ok", False), ("ok", 0), ("ok", "false"),
    ("success", False), ("success", 0), ("success", "false"),
    ("error", "provider rejected"), ("error_code", "provider rejected"),
    ("errors", []), ("error", None),
])
def test_matching_fields_with_failure_verdict_do_not_acknowledge_roles(memory, field, value):
    memory.response = httpx.Response(200, json=[{"id": TARGET, "roles": ["admin"], field: value}])
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == 502
    assert error.value.body is None
    assert len(memory.requests) == 1


@pytest.mark.parametrize("headers", [
    None, {},
    {"apikey": "caller-value", "Authorization": "caller-value", "Prefer": "return=representation"},
    {"APIKEY": "caller-value", "authorization": "caller-value", "prefer": "return=representation"},
    {"ApiKey": "caller-value", "AUTHORIZATION": "caller-value", "pReFeR": "return=representation"},
    [("apikey", "first"), ("APIKEY", "second"), ("authorization", "first"),
     ("AUTHORIZATION", "second"), ("Prefer", "return=minimal"), ("prefer", "return=representation")],
    httpx.Headers({"aPiKeY": "caller-value", "aUtHoRiZaTiOn": "caller-value", "PREFER": "return=representation"}),
])
def test_per_call_headers_cannot_replace_required_authentication(memory, headers):
    supabase_admin._raw_request("PATCH", "https://batch7-helper.invalid/rest/v1/profiles",
                               headers=headers, json={"roles": ["admin"]})
    assert len(memory.requests) == 1
    request = memory.requests[0]
    assert request.headers.get_list("apikey") == [SERVICE_KEY]
    assert request.headers.get_list("authorization") == ["Bearer " + SERVICE_KEY]
    assert request.headers.get_list("content-type") == ["application/json"]
    assert request.headers.get_list("prefer") == (["return=representation"] if headers else [])


def test_per_call_httpx_auth_cannot_replace_service_role_credentials(memory):
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin._raw_request("PATCH", "https://batch7-helper.invalid/rest/v1/profiles",
                                   auth=("caller", "inert"), json={"roles": ["admin"]})
    assert error.value.status_code == 400
    assert memory.requests == []


@pytest.mark.parametrize("roles", [[], ["citizen"], ["citizen", "admin", "legacy-role"]])
def test_matching_role_arrays_preserve_public_row_contract(memory, roles):
    row = {"id": TARGET, "roles": roles, "display_name": "Inert compatibility profile", "ok": True}
    memory.response = httpx.Response(200, json=[row])
    assert supabase_admin.update_profile_roles(TARGET, roles) == row
    assert json.loads(memory.requests[0].content) == {"roles": roles}


@pytest.mark.parametrize("failure", [httpx.ConnectError("inert unavailable"), httpx.ReadTimeout("inert timeout")])
def test_transport_failure_is_safe_without_role_success(memory, failure):
    memory.response = failure
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.update_profile_roles(TARGET, ["admin"])
    assert error.value.status_code == 503
    assert error.value.body is None
    assert len(memory.requests) == 1


def test_signed_authentication_still_looks_up_roles_through_actual_transport(memory, monkeypatch):
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import jwt
    import supabase_auth

    monkeypatch.setenv("SUPABASE_JWT_SECRET", "inert-batch7-jwt-secret")
    memory.response = httpx.Response(200, json=[{"id": TARGET, "email": "fixture@example.invalid", "roles": ["admin"]}])
    token = jwt.encode({"sub": TARGET, "aud": "authenticated", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       "inert-batch7-jwt-secret", algorithm="HS256")
    actor = supabase_auth.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert actor.id == TARGET
    assert actor.email == "fixture@example.invalid"
    assert actor.roles == ["admin"]
    assert len(memory.requests) == 1
    assert memory.requests[0].method == "GET"
    assert memory.requests[0].url.params.get("id") == "eq." + TARGET
    assert memory.requests[0].headers.get_list("authorization") == ["Bearer " + SERVICE_KEY]


@pytest.mark.parametrize("operation,args,response,expected,method,path", [
    ("list_users", (), {"users": []}, {"users": []}, "GET", "/auth/v1/admin/users"),
    ("get_user", (TARGET,), {"id": TARGET}, {"id": TARGET}, "GET", "/auth/v1/admin/users/" + TARGET),
    ("update_user", (TARGET, {"ban_duration": "none"}), {"id": TARGET}, {"id": TARGET}, "PUT", "/auth/v1/admin/users/" + TARGET),
    ("delete_user", (TARGET,), {}, {}, "DELETE", "/auth/v1/admin/users/" + TARGET),
    ("generate_recovery_link", ("fixture@example.invalid",), {}, {}, "POST", "/auth/v1/admin/generate_link"),
    ("get_profile", (TARGET,), [{"id": TARGET}], {"id": TARGET}, "GET", "/rest/v1/profiles"),
    ("get_profiles", ([TARGET],), [{"id": TARGET}], [{"id": TARGET}], "GET", "/rest/v1/profiles"),
])
def test_other_public_helper_transport_paths_remain_compatible(memory, operation, args, response, expected, method, path):
    memory.response = httpx.Response(200, json=response)
    assert getattr(supabase_admin, operation)(*args) == expected
    assert len(memory.requests) == 1
    request = memory.requests[0]
    assert (request.method, request.url.path) == (method, path)
    assert request.headers.get_list("apikey") == [SERVICE_KEY]
    assert request.headers.get_list("authorization") == ["Bearer " + SERVICE_KEY]


def test_empty_bulk_lookup_still_avoids_transport(memory):
    assert supabase_admin.get_profiles([]) == []
    assert memory.requests == []

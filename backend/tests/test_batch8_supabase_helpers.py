"""Retained profile reads and diagnostics at the public HTTP boundary."""

from types import SimpleNamespace
import socket
import traceback

import httpx
import pytest

import supabase_admin


TARGET = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MARKER = "inert-sensitive-diagnostic-marker"


@pytest.fixture
def memory(monkeypatch):
    state = SimpleNamespace(requests=[], response=httpx.Response(200, json=[{"id": TARGET}]))

    def deny(*args, **kwargs):
        raise AssertionError("No socket transport is permitted")

    def transport(request):
        state.requests.append(request)
        if isinstance(state.response, Exception):
            raise state.response
        return state.response

    real = httpx.Client
    monkeypatch.setenv("SUPABASE_URL", "https://batch8-helper.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "inert-batch8-service-key")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(transport), **kwargs))
    return state


def test_single_read_refuses_injected_identity_before_transport(memory):
    memory.response = httpx.Response(200, json=[{"id": OTHER, "roles": ["admin"]}])
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.get_profile("expected-identity&id=neq.expected-identity")
    assert error.value.status_code == 400
    assert memory.requests == []


def test_bulk_malformed_object_is_provider_failure_not_missing_profiles(memory):
    memory.response = httpx.Response(200, json={"unexpected": "shape"})
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin.get_profiles([TARGET])
    assert error.value.status_code == 502
    assert len(memory.requests) == 1


def test_valid_single_bulk_missing_and_empty_controls(memory):
    assert supabase_admin.get_profile(TARGET) == {"id": TARGET}
    assert supabase_admin.get_profiles([TARGET]) == [{"id": TARGET}]
    memory.response = httpx.Response(200, json=[])
    assert supabase_admin.get_profile(TARGET) is None
    assert supabase_admin.get_profiles([TARGET]) == []
    assert len(memory.requests) == 4
    assert supabase_admin.get_profiles([]) == []
    assert len(memory.requests) == 4


@pytest.mark.parametrize("operation,args", [
    ("get_profile", (TARGET,)), ("get_profiles", ([TARGET],)),
    ("list_users", ()), ("get_user", (TARGET,)),
    ("update_user", (TARGET, {"ban_duration": "none"})),
    ("delete_user", (TARGET,)), ("generate_recovery_link", ("fixture@example.invalid",)),
    ("update_profile_roles", (TARGET, ["admin"])), ("count_profiles", ()),
])
def test_http_errors_retain_status_without_provider_diagnostics(memory, operation, args):
    memory.response = httpx.Response(503, json={"message": MARKER})
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    error = raised.value
    assert error.status_code == 503
    assert error.body is None
    assert str(error) == "Supabase admin API returned 503"
    assert MARKER not in repr(error)
    print(operation, "status=", error.status_code, "str=", str(error), "body=", error.body)


@pytest.mark.parametrize("failure", [
    httpx.ConnectError(MARKER + " https://secret.invalid/?token=inert"),
    httpx.ReadTimeout(MARKER), httpx.RemoteProtocolError(MARKER),
])
@pytest.mark.parametrize("operation,args", [
    ("get_profile", (TARGET,)), ("update_profile_roles", (TARGET, ["admin"])),
    ("count_profiles", ()), ("list_users", ()),
])
def test_connection_errors_are_bounded_and_do_not_chain_sensitive_text(memory, operation, args, failure):
    memory.response = failure
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    assert raised.value.status_code == 503
    assert raised.value.body is None
    assert str(raised.value) == "Supabase admin API returned 503"
    assert MARKER not in "".join(traceback.format_exception(raised.value))


@pytest.mark.parametrize("content", [b'{"inert-sensitive-diagnostic-marker":', b'\xff', b'[' * 3000],
                         ids=["malformed", "invalid-encoding", "too-deep"])
@pytest.mark.parametrize("operation,args", [
    ("get_profile", (TARGET,)), ("get_profiles", ([TARGET],)), ("list_users", ()),
])
def test_rejected_json_has_safe_provider_failure(memory, operation, args, content):
    memory.response = httpx.Response(200, content=content)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    assert raised.value.status_code == 502
    assert raised.value.body is None
    assert str(raised.value) == "Supabase admin API returned 502"
    assert MARKER not in "".join(traceback.format_exception(raised.value))


@pytest.mark.parametrize("identity", [TARGET, TARGET.upper(), TARGET.replace("-", ""),
                                       "{" + TARGET + "}", "urn:uuid:" + TARGET,
                                       "{" + TARGET.replace("-", "") + "}",
                                       "urn:uuid:" + TARGET.replace("-", ""), "URN:UUID:" + TARGET.upper()])
@pytest.mark.parametrize("bulk", [False, True])
def test_valid_uuid_spellings_use_one_safe_filter_and_preserve_rows(memory, identity, bulk):
    row = {"id": identity, "roles": ["citizen", "legacy-role"], "display_name": "Inert profile"}
    memory.response = httpx.Response(200, json=[row])
    result = supabase_admin.get_profiles([identity]) if bulk else supabase_admin.get_profile(identity)
    assert result == ([row] if bulk else row)
    request = memory.requests[0]
    assert request.url.path == "/rest/v1/profiles"
    assert request.url.params.multi_items() == [
        ("select", "id,email,display_name,roles,created_at"),
        ("id", "in.(" + TARGET + ")" if bulk else "eq." + TARGET),
    ]
    assert request.headers.get_list("apikey") == ["inert-batch8-service-key"]
    assert request.headers.get_list("authorization") == ["Bearer inert-batch8-service-key"]


def test_bulk_deduplicates_requested_uuid_and_preserves_provider_order_and_missing_ids(memory):
    row = {"id": OTHER}
    memory.response = httpx.Response(200, json=[row, {"id": TARGET}])
    assert supabase_admin.get_profiles([TARGET, TARGET.upper(), OTHER]) == [row, {"id": TARGET}]
    assert memory.requests[0].url.params.get_list("id") == ["in.(" + TARGET + "," + OTHER + ")"]
    memory.response = httpx.Response(200, json=[row])
    assert supabase_admin.get_profiles([TARGET, OTHER]) == [row]


@pytest.mark.parametrize("identity", [
    None, True, 1, 0, 1.5, float("nan"), float("inf"), {}, [], "", "invalid", " " + TARGET,
    TARGET + "&id=neq." + TARGET, TARGET + "#fragment", TARGET + "?select=*",
    TARGET + "," + OTHER, TARGET + ")", TARGET + "%26id=neq.x", "x" * 100000,
], ids=["null", "bool", "int", "zero", "float", "nan", "inf", "dict", "list", "empty",
        "garbage", "space", "ampersand", "fragment", "question", "comma", "paren", "encoded", "oversized"])
@pytest.mark.parametrize("bulk", [False, True])
def test_invalid_uuid_inputs_fail_before_any_provider_request(memory, identity, bulk):
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        if bulk:
            supabase_admin.get_profiles([TARGET, identity])
        else:
            supabase_admin.get_profile(identity)
    assert raised.value.status_code == 400
    assert raised.value.body is None
    assert str(raised.value) == "Supabase admin API returned 400"
    assert memory.requests == []


@pytest.mark.parametrize("container", [None, "", TARGET, (), {}, True, 0])
def test_bulk_requires_list_container_even_when_falsey(memory, container):
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        supabase_admin.get_profiles(container)
    assert raised.value.status_code == 400
    assert memory.requests == []


@pytest.mark.parametrize("payload", [
    None, {}, "unexpected", 1, True, [None], [True], ["unexpected"], [{}],
    [{"id": None}], [{"id": True}], [{"id": 1}], [{"id": []}], [{"id": {}}],
    [{"id": "wrong-identity"}], [{"id": OTHER}],
    [{"id": TARGET}, {"id": TARGET.upper()}],
    [{"id": TARGET}, {"id": OTHER}],
    [{"id": TARGET, "error": None}], [{"id": TARGET, "errors": []}],
    [{"id": TARGET, "error_code": "rejected"}], [{"id": TARGET, "ok": False}],
    [{"id": TARGET, "success": 1}], [{"id": TARGET, "ok": "true"}],
], ids=["null", "object", "string", "int", "bool", "null-row", "bool-row", "string-row",
        "missing-id", "null-id", "bool-id", "int-id", "list-id", "object-id", "invalid-id",
        "unrequested-id", "duplicate-id", "mixed-unrequested", "error", "errors", "error-code",
        "false-ok", "numeric-success", "string-ok"])
@pytest.mark.parametrize("bulk", [False, True])
def test_malformed_or_unrequested_rows_reject_entire_response(memory, payload, bulk):
    memory.response = httpx.Response(200, json=payload)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        if bulk:
            supabase_admin.get_profiles([TARGET])
        else:
            supabase_admin.get_profile(TARGET)
    assert raised.value.status_code == 502
    assert raised.value.body is None
    assert len(memory.requests) == 1


@pytest.mark.parametrize("status,content", [(200, b""), (204, b"")])
@pytest.mark.parametrize("bulk", [False, True])
def test_absent_profile_container_is_not_a_missing_row(memory, status, content, bulk):
    memory.response = httpx.Response(status, content=content)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        supabase_admin.get_profiles([TARGET]) if bulk else supabase_admin.get_profile(TARGET)
    assert raised.value.status_code == 502


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 404, 409, 429, 500, 503])
@pytest.mark.parametrize("operation,args", [("get_profile", (TARGET,)), ("count_profiles", ())])
def test_non_success_http_status_is_preserved_safely(memory, status, operation, args):
    memory.response = httpx.Response(status, json={"message": MARKER})
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    assert raised.value.status_code == status
    assert raised.value.body is None


@pytest.mark.parametrize("content", [MARKER.encode() + b"x" * 1000000,
                                     b"x" * 1000000 + MARKER.encode(), b"\xff" * 1000000],
                         ids=["marker-prefix", "marker-suffix", "invalid-encoding"])
@pytest.mark.parametrize("operation,args", [("get_profile", (TARGET,)), ("count_profiles", ())])
def test_hostile_error_bodies_are_discarded_without_partial_secret_truncation(memory, operation, args, content):
    memory.response = httpx.Response(503, content=content)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    assert raised.value.args == ("Supabase admin API returned 503",)
    assert vars(raised.value) == {"status_code": 503, "body": None}


def test_exception_constructor_never_renders_or_retains_legacy_body():
    class UnprintableBody:
        def __str__(self):
            raise AssertionError("Provider bodies must not be formatted")

    error = supabase_admin.SupabaseAdminError(429, UnprintableBody())
    assert str(error) == "Supabase admin API returned 429"
    assert error.status_code == 429
    assert error.body is None


@pytest.mark.parametrize("status", [None, True, "https://secret.invalid/" + MARKER, -1, 0, 600,
                                    float("nan"), float("inf"), {}])
def test_invalid_exception_status_cannot_become_a_diagnostic_channel(status):
    error = supabase_admin.SupabaseAdminError(status, MARKER)
    assert error.status_code == 502
    assert str(error) == "Supabase admin API returned 502"
    assert error.body is None


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"unexpected": "shape"}),
    httpx.Response(200, json=[{"id": OTHER, "roles": ["admin"]}]),
    httpx.Response(503, json={"message": MARKER}),
    httpx.Response(200, content=b'{"inert-sensitive-diagnostic-marker":'),
    httpx.ConnectError(MARKER),
], ids=["wrong-container", "wrong-identity", "upstream", "invalid-json", "connection"])
def test_signed_auth_consumer_refuses_admin_when_actual_profile_read_fails(memory, response, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import jwt
    import supabase_auth

    secret = "inert-batch8-jwt-secret"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    memory.response = response
    token = jwt.encode({"sub": TARGET, "aud": "authenticated",
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       secret, algorithm="HS256")
    actor = supabase_auth.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert actor.id == TARGET and actor.roles == []
    with pytest.raises(HTTPException) as raised:
        supabase_auth.require_admin(actor)
    assert raised.value.status_code == 403
    assert raised.value.detail == "Admin role required"
    assert len(memory.requests) == 1


@pytest.mark.parametrize("operation,args", [
    ("get_profile", (TARGET,)), ("count_profiles", ()), ("list_users", ()),
])
@pytest.mark.parametrize("setting,value", [
    ("SUPABASE_URL", "https://secret.invalid:" + MARKER + "/?token=" + MARKER),
    ("SUPABASE_URL", "https://secret.invalid/\n" + MARKER),
    ("SUPABASE_SERVICE_ROLE_KEY", MARKER + "\u2603"),
], ids=["invalid-port", "control-character", "non-ascii-key"])
def test_invalid_config_raises_safe_error_before_transport(memory, monkeypatch, operation, args, setting, value):
    monkeypatch.setenv(setting, value)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        getattr(supabase_admin, operation)(*args)
    assert raised.value.status_code == 500
    assert raised.value.body is None
    assert MARKER not in repr(raised.value)
    assert MARKER not in "".join(traceback.format_exception(raised.value))
    assert memory.requests == []


def test_direct_raw_request_invalid_url_raises_safe_error(memory):
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        supabase_admin._raw_request("GET", "https://secret.invalid:" + MARKER)
    assert raised.value.status_code == 500
    assert MARKER not in repr(raised.value)
    assert MARKER not in "".join(traceback.format_exception(raised.value))
    assert memory.requests == []


def test_per_call_non_ascii_headers_cannot_escape_sensitive_encoding_error(memory):
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        supabase_admin._raw_request("GET", "https://batch8-helper.invalid/",
                                    headers={"X-Inert": MARKER + "\u2603"})
    assert raised.value.status_code == 400
    assert MARKER not in repr(raised.value)
    assert MARKER not in "".join(traceback.format_exception(raised.value))
    assert memory.requests == []


@pytest.mark.parametrize("identity", ["{" + TARGET, TARGET + "}", TARGET + "urn:uuid:",
                                     "uuid:" + TARGET, "urn:" + TARGET, TARGET.replace("-", "--")],
                         ids=["open-brace", "close-brace", "suffix-urn", "bare-uuid", "bare-urn", "extra-hyphens"])
@pytest.mark.parametrize("provider_row", [False, True])
def test_malformed_uuid_spellings_are_not_supported_inputs_or_provider_identities(memory, identity, provider_row):
    if provider_row:
        memory.response = httpx.Response(200, json=[{"id": identity}])
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        supabase_admin.get_profile(TARGET if provider_row else identity)
    assert raised.value.status_code == (502 if provider_row else 400)
    assert len(memory.requests) == (1 if provider_row else 0)


@pytest.mark.parametrize("setting,value", [
    ("SUPABASE_URL", "https://secret.invalid:" + MARKER),
    ("SUPABASE_SERVICE_ROLE_KEY", MARKER + "\u2603"),
], ids=["invalid-port", "non-ascii-key"])
def test_active_provider_shared_configuration_errors_remain_safe(memory, monkeypatch, setting, value):
    import admin_users_provider

    monkeypatch.setenv(setting, value)
    with pytest.raises(supabase_admin.SupabaseAdminError) as raised:
        admin_users_provider.get_profile(TARGET)
    assert raised.value.status_code == 500
    assert raised.value.body is None
    assert MARKER not in repr(raised.value)
    assert MARKER not in "".join(traceback.format_exception(raised.value))
    assert memory.requests == []

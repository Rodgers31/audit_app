"""Executed adjudication of PR579's HTTPX exception hierarchy claim."""

import hashlib
import json
import os
from pathlib import Path
import socket
import traceback

import httpx
import supabase_admin


def deny(*args, **kwargs):
    raise AssertionError("No socket transport is permitted")


socket.socket.connect = deny
socket.socket.connect_ex = deny
os.environ["SUPABASE_URL"] = "https://batch8-helper.invalid"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "inert-review-service-key"
marker = "inert-sensitive-diagnostic-marker"
target = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
requests = []
response = httpx.Response(200, json=[{"id": target, "roles": ["admin"]}])


def transport(request):
    requests.append(request)
    if isinstance(response, Exception):
        raise response
    return response


real_client = httpx.Client
httpx.Client = lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)
assert not issubclass(httpx.InvalidURL, httpx.HTTPError)
try:
    supabase_admin._raw_request("GET", "https://secret.invalid:" + marker)
except supabase_admin.SupabaseAdminError as error:
    malformed_status = error.status_code
    assert malformed_status == 500
    assert error.body is None
    assert marker not in repr(error)
    assert marker not in "".join(traceback.format_exception(error))
else:
    raise AssertionError("Malformed URL must fail")
assert requests == []
assert supabase_admin.get_profile(target) == {"id": target, "roles": ["admin"]}
response = httpx.ConnectError(marker)
try:
    supabase_admin.get_profile(target)
except supabase_admin.SupabaseAdminError as error:
    transport_status = error.status_code
    assert transport_status == 503
    assert error.body is None
    assert marker not in repr(error)
else:
    raise AssertionError("Transport failure must fail")
assert len(requests) == 2
print(json.dumps({
    "httpx_version": httpx.__version__,
    "httpx_path": httpx.__file__,
    "invalid_url_mro": [cls.__name__ for cls in httpx.InvalidURL.__mro__],
    "invalid_url_is_http_error": issubclass(httpx.InvalidURL, httpx.HTTPError),
    "real_malformed_url_status": malformed_status,
    "real_malformed_url_memory_calls": 0,
    "valid_profile_read": "PASS",
    "transport_error_status": transport_status,
    "socket_transport": "REFUSED",
    "helper_sha256": hashlib.sha256(Path(supabase_admin.__file__).read_bytes()).hexdigest(),
}, indent=2))

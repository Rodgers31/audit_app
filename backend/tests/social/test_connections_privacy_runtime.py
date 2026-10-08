"""Execute privacy helpers on the test interpreter without ORM dependencies.

Run this file with each supported Python runtime. The namespace only supplies
the source directory; the helpers and standard-library dataclasses are real.
"""
from pathlib import Path
import subprocess
import sys

import pytest


PROBE = '''
import base64
from dataclasses import FrozenInstanceError
import hmac
import importlib
import sys
import types
from uuid import UUID

package = types.ModuleType("privacy_runtime_probe")
package.__path__ = [sys.argv[1]]
sys.modules[package.__name__] = package
module = importlib.import_module(package.__name__ + "." + sys.argv[2])
signed_requests = importlib.import_module(package.__name__ + ".signed_requests")
secret = "runtime-probe-never-live"
payload = base64.urlsafe_b64encode(b'{"algorithm":"HMAC-SHA256","user_id":"819"}').decode().rstrip("=")
signature = base64.urlsafe_b64encode(hmac.digest(secret.encode(), payload.encode(), "sha256")).decode().rstrip("=")
request = signed_requests.verify_signed_request(signature + "." + payload, app_secret=secret, expected_app_id="714")
assert (request.app_id, request.app_scoped_user_id) == ("714", "819")
assert repr(request) == "VerifiedSignedRequest()"
try:
    request.app_scoped_user_id = "changed"
except FrozenInstanceError:
    pass
else:
    raise AssertionError("Request lost frozen behavior")
try:
    signed_requests.verify_signed_request("bad", app_secret=secret, expected_app_id="714")
except signed_requests.SignedRequestError as error:
    assert error.__context__ is None and error.__cause__ is None
else:
    raise AssertionError("Invalid request verified")
if sys.argv[2] == "ownership":
    identifier = UUID("00000000-0000-0000-0000-000000000001")
    declaration = module.DeclaredCredentialOwnership("714", "819", identifier, 1)
    binding = module.bind_declared_ownership(request, declaration, expected_app_id="714", expected_credential_id=identifier, expected_credential_version=1)
    assert binding.status == "declared_match" and binding.provider_verification_performed is False
    assert repr(declaration) == "DeclaredCredentialOwnership()"
    assert "714" not in repr(binding) and "819" not in repr(binding)
    for instance, name, value in ((declaration, "app_id", "changed"), (binding, "provider_verification_performed", True)):
        try:
            setattr(instance, name, value)
        except FrozenInstanceError:
            pass
        else:
            raise AssertionError("Ownership result lost frozen behavior")
    incomplete = object.__new__(signed_requests.VerifiedSignedRequest)
    assert module.bind_declared_ownership(incomplete, declaration, expected_app_id="714", expected_credential_id=identifier, expected_credential_version=1).status == "unverified"
print("privacy-runtime-ok")
'''


@pytest.mark.parametrize("module_name", ["signed_requests", "ownership"])
def test_supported_interpreter_imports_and_executes_privacy_helpers(module_name):
    source_directory = Path(__file__).resolve().parents[2] / "social" / "connections"
    result = subprocess.run(
        [sys.executable, "-B", "-I", "-c", PROBE, str(source_directory), module_name],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "privacy-runtime-ok\n" and result.stderr == ""

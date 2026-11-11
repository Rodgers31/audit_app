"""Execute the deployed workflow scripts against malformed HTTP success bodies."""

import json
import hmac
import hashlib
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/seed.yml").read_text())
PATHS = json.loads((ROOT / "frontend/lib/revalidation/paths.json").read_text())["paths"]


def run_refresh(tmp_path, invalidated, revalidated, *, expected_secret='test-only-key', return_outputs=False, needs_override=None, unsigned=False):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            calls.append(self.path)
            request_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            expected = hmac.new(expected_secret.encode(), request_body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(self.headers.get('x-revalidate-signature', ''), expected):
                body, code = {'invalidated':False}, 403
            else:
                body = invalidated if self.path.endswith("/invalidate") else revalidated
                census = {'scope':'container','instance':'d'*64,'supervisor':'1:100','workers':['2:200'],'worker':'2:200'}
                if self.path.endswith('/status'):
                    body = {'commit':'a'*40,'census':census,'pid':2,'synchronised':True,
                            'observed_identity':[123,456,32],'adopted_identity':[123,456,32]}
                code = 200
                if type(body) is tuple:
                    code, body = body
                sent = json.loads(request_body)
                if self.path == '/revalidate':
                    assert sent['paths'] == PATHS and sent['context']['source_sha'] == 'a'*40
                if type(body) is dict:
                    if self.path.endswith('/invalidate'):
                        body = {'commit':'a'*40,'census':census,'pid':2,'marker_identity':[123,456,32],**body}
                    if self.path == '/revalidate':
                        body = {'backend_adoption_sha256':sent['backend_adoption_sha256'],**body}
                    body = {'protocol':'nightly-refresh-v2','context':sent['context'],
                            'request_sha256':hashlib.sha256(request_body).hexdigest(),'at':int(__import__('time').time()),'result':body}
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(payload)))
            if not unsigned:
                self.send_header('x-revalidate-response-signature',hmac.new(expected_secret.encode(),payload,hashlib.sha256).hexdigest())
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    import ssl
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from test_treasury_transport_qualification import _certificate
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    cert = _certificate('localhost',key,ca=True)
    cert_file,key_file=tmp_path/'cert.pem',tmp_path/'key.pem'
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert_file,key_file)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    url = f"https://localhost:{server.server_address[1]}"
    env = {
        **os.environ,
        "REVALIDATE_SECRET": "test-only-key", "SSL_CERT_FILE":str(cert_file), "RUNNER_TEMP":str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_SHA": "a"*40, "GITHUB_RUN_ID":"1234", "GITHUB_RUN_ATTEMPT":"1",
        "REFRESH_NEEDS": json.dumps(needs_override or __import__('tests.test_refresh_eligibility',fromlist=['needs_fixture']).needs_fixture()),
        "API_BASE_URL": url,
        "REVALIDATE_URL": url + "/revalidate",
    }
    try:
        for step in WORKFLOW["jobs"]["revalidate"]["steps"]:
            if "run" not in step:
                continue
            script = (
                step["run"]
                .replace("${{ github.run_id }}", "regression")
                .replace("/tmp/", str(tmp_path) + "/")
            )
            result = subprocess.run(
                ["bash", "-eo", "pipefail", "-c", script],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode:
                break
        if return_outputs:
            path = tmp_path / 'outputs'
            outputs = path.read_text().splitlines() if path.exists() else []
            return result.returncode, calls, outputs
        return result.returncode, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        assert not thread.is_alive()


def test_valid_responses_refresh_in_order(tmp_path):
    code, calls = run_refresh(
        tmp_path, {"invalidated": True}, {"revalidated": PATHS, "rejected": []}
    )
    assert code == 0
    assert calls == ["/api/v1/system/cache/invalidate", "/api/v1/system/cache/status", "/revalidate"]


@pytest.mark.parametrize("value", ["true", False, None, 1])
def test_invalidation_requires_boolean_true(tmp_path, value):
    code, calls = run_refresh(
        tmp_path, {"invalidated": value}, {"revalidated": PATHS, "rejected": []}
    )
    assert code != 0
    assert calls == ["/api/v1/system/cache/invalidate"]


@pytest.mark.parametrize(
    "value",
    [
        "x" * len(PATHS),
        ["/"] * len(PATHS),
        ["/wrong" + str(i) for i in range(len(PATHS))],
        {},
        None,
    ],
)
def test_frontend_must_confirm_exact_requested_paths(tmp_path, value):
    code, _ = run_refresh(
        tmp_path, {"invalidated": True}, {"revalidated": value, "rejected": []}
    )
    assert code != 0


def test_invalidation_rejects_a_stream_of_conflicting_json_documents(tmp_path):
    code, calls = run_refresh(
        tmp_path,
        b'{"invalidated":false}\n{"invalidated":true}',
        {"revalidated": PATHS, "rejected": []},
    )
    assert code != 0
    assert calls == ["/api/v1/system/cache/invalidate"]


def test_revalidation_rejects_a_stream_of_conflicting_json_documents(tmp_path):
    receipts = (
        json.dumps({"revalidated": [], "rejected": []})
        + "\n"
        + json.dumps({"revalidated": PATHS, "rejected": []})
    )
    code, _ = run_refresh(tmp_path, {"invalidated": True}, receipts.encode())
    assert code != 0


@pytest.mark.parametrize('code',[201,204,301,302,307,401,403,404])
def test_backend_requires_actual_http_200(tmp_path,code):
    rc,calls=run_refresh(tmp_path,(code,{'invalidated':True}),{'revalidated':PATHS,'rejected':[]})
    assert rc != 0 and calls == ['/api/v1/system/cache/invalidate']


@pytest.mark.parametrize('body',[b'',b'not json',[],None,{},True])
def test_missing_wrong_schema_or_absent_backend_ack_refuses(tmp_path,body):
    rc,calls=run_refresh(tmp_path,body,{'revalidated':PATHS,'rejected':[]})
    assert rc != 0 and calls == ['/api/v1/system/cache/invalidate']


def test_stale_signing_key_refuses_before_pages(tmp_path):
    rc,calls=run_refresh(tmp_path,{'invalidated':True},{'revalidated':PATHS,'rejected':[]},expected_secret='different-inert-key')
    assert rc != 0 and calls == ['/api/v1/system/cache/invalidate']


@pytest.mark.parametrize('response',[(302,{'revalidated':PATHS,'rejected':[]}), b'',
    {'revalidated':PATHS,'rejected':['/']}, {'revalidated':PATHS[:-1],'rejected':[]}])
def test_backend_ack_is_preserved_when_pages_fail(tmp_path,response):
    rc,calls,outputs=run_refresh(tmp_path,{'invalidated':True},response,return_outputs=True)
    assert rc != 0 and calls == ['/api/v1/system/cache/invalidate','/api/v1/system/cache/status','/revalidate']
    assert outputs.count('acknowledged=true') == 1
    assert 'protocol=nightly-refresh-v2' in outputs
    assert (tmp_path/'nightly-refresh-1234-1.jsonl').is_file()


def test_http_zero_refuses_pages(tmp_path):
    rc,calls=run_refresh(tmp_path,(0,b''),{'revalidated':PATHS,'rejected':[]})
    assert rc!=0 and calls==['/api/v1/system/cache/invalidate']


def test_case_insensitive_job_selection_still_cannot_reach_http(tmp_path):
    from tests.test_refresh_eligibility import needs_fixture,expression_selected
    needs=needs_fixture();needs['seed']['outputs']['cache_eligible']='True'
    assert expression_selected(needs) is True
    rc,calls=run_refresh(tmp_path,{'invalidated':True},{'revalidated':PATHS,'rejected':[]},needs_override=needs)
    assert rc!=0 and calls==[]


def test_workflow_refuses_unsigned_backend_ack_even_if_true(tmp_path):
    code, calls = run_refresh(tmp_path, {'invalidated': True}, {'revalidated': PATHS, 'rejected': []}, unsigned=True)
    assert code != 0 and '/revalidate' not in calls

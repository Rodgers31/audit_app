"""Signed R2 boundary simulation; these checks do not contact Cloudflare."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from services.r2_receipt_store import R2ReceiptStore, ReceiptStorageError
from services.supabase_receipt_store import SupabaseReceiptStore
from test_supabase_receipt_store import URL, BUCKET, KEY

ACCOUNT = "a" * 32
R2_BUCKET = "audit-source-evidence-v1"
ACCESS, SECRET, CONTROL = "access" * 6, "secret" * 7, "control" * 6


class Boundary:
    def __init__(self, root):
        self.root = root
        self.requests = []
        self.managed = {"bucketId": "synthetic-id", "domain": "synthetic.r2.dev", "enabled": False}
        self.custom = {"domains": []}
        self.bucket = {"name": R2_BUCKET, "jurisdiction": "default", "storage_class": "Standard"}
        self.fail_path = None

    def __call__(self, request):
        self.requests.append(request)
        if request.url.host == "api.cloudflare.com":
            assert request.headers["authorization"] == "Bearer " + CONTROL
            assert request.headers["cf-r2-jurisdiction"] == "default"
            assert request.method == "GET"
            path = request.url.path
            data = self.managed if path.endswith("/domains/managed") else self.custom if path.endswith("/domains/custom") else self.bucket
            return httpx.Response(200, json={"success": True, "errors": [], "result": data})
        assert request.url.host == ACCOUNT + ".r2.cloudflarestorage.com"
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=" + ACCESS + "/")
        assert "/auto/s3/aws4_request" in request.headers["authorization"]
        assert CONTROL not in str(request.headers)
        assert request.headers["x-amz-content-sha256"] == hashlib.sha256(request.content).hexdigest()
        path = self.root / request.url.path.removeprefix("/" + R2_BUCKET + "/")
        if self.fail_path and self.fail_path in request.url.path:
            return httpx.Response(503, content=(SECRET + CONTROL).encode())
        if request.method == "PUT":
            assert request.headers["if-none-match"] == "*"
            assert "if-none-match" in request.headers["authorization"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                return httpx.Response(412)
            path.write_bytes(request.content)
            return httpx.Response(200)
        return httpx.Response(200, content=path.read_bytes()) if path.exists() else httpx.Response(404)

    def store(self, **kwargs):
        return R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, part_max_bytes=4, transport=httpx.MockTransport(self), **kwargs)


def test_signed_chunked_put_retry_fresh_read_and_manifest_wire(tmp_path):
    boundary = Boundary(tmp_path)
    body = b"same" * 3
    digest = boundary.store().put(body)
    puts = [r for r in boundary.requests if r.method == "PUT"]
    assert "/manifests/" in puts[-1].url.path
    assert all("/chunks/" in r.url.path for r in puts[:-1])
    assert len([r for r in boundary.requests if r.url.host == "api.cloudflare.com"]) == 3
    encoded = (tmp_path / "receipts-v1/manifests" / digest[:2] / digest).read_bytes()
    supabase = SupabaseReceiptStore(URL, BUCKET, KEY, max_bytes=1024, part_max_bytes=4)
    assert encoded == supabase._manifest(body, digest)[0]
    assert boundary.store().put(body) == digest
    assert Boundary(tmp_path).store().read(digest) == body


def test_supabase_codec_exact_baseline_wire():
    fixture = json.loads((Path(__file__).parent / "fixtures/receipt_manifest_v1_baseline.json").read_text())
    current = SupabaseReceiptStore(URL, BUCKET, KEY, max_bytes=1024, part_max_bytes=fixture["part_max_bytes"])
    for case in fixture["cases"]:
        body, encoded = bytes.fromhex(case["body_hex"]), case["manifest"].encode()
        assert current._manifest(body, case["digest"])[0] == encoded
        assert current._parse_manifest(encoded, case["digest"], None) == json.loads(encoded)


@pytest.mark.parametrize("operation", ["put", "read"])
@pytest.mark.parametrize("change", ["managed", "custom", "missing_managed", "missing_custom", "bucket_name", "bucket_class", "jurisdiction", "bool_string"])
def test_privacy_fail_closed_before_object_io(tmp_path, operation, change):
    boundary = Boundary(tmp_path)
    if change == "managed": boundary.managed["enabled"] = True
    if change == "custom": boundary.custom["domains"] = [{"domain": "public.example", "enabled": True}]
    if change == "missing_managed": del boundary.managed["enabled"]
    if change == "missing_custom": boundary.custom = {}
    if change == "bucket_name": boundary.bucket["name"] = "other"
    if change == "bucket_class": boundary.bucket["storage_class"] = "InfrequentAccess"
    if change == "jurisdiction": boundary.bucket["jurisdiction"] = "eu"
    if change == "bool_string": boundary.managed["enabled"] = "false"
    with pytest.raises(ReceiptStorageError):
        boundary.store().put(b"test") if operation == "put" else boundary.store().read("a" * 64)
    assert all(r.url.host == "api.cloudflare.com" for r in boundary.requests)


def test_corrupt_existing_chunk_never_overwritten_or_published(tmp_path):
    boundary = Boundary(tmp_path)
    part_digest = hashlib.sha256(b"test").hexdigest()
    path = tmp_path / "receipts-v1/chunks" / part_digest[:2] / part_digest
    path.parent.mkdir(parents=True)
    path.write_bytes(b"evil")
    with pytest.raises(ReceiptStorageError, match="part readback"):
        boundary.store().put(b"test")
    assert path.read_bytes() == b"evil"
    assert not (tmp_path / "receipts-v1/manifests").exists()


def test_partial_attempt_retry_and_provider_error_redacted(tmp_path):
    boundary = Boundary(tmp_path)
    boundary.fail_path = hashlib.sha256(b"efgh").hexdigest()
    with pytest.raises(ReceiptStorageError) as error:
        boundary.store().put(b"abcdefgh")
    assert SECRET not in str(error.value) and CONTROL not in str(error.value)
    assert not (tmp_path / "receipts-v1/manifests").exists()
    boundary.fail_path = None
    digest = boundary.store().put(b"abcdefgh")
    assert Boundary(tmp_path).store().read(digest) == b"abcdefgh"


def test_whole_operation_deadline_includes_all_three_privacy_checks(tmp_path, monkeypatch):
    from services import r2_receipt_store as module
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    boundary = Boundary(tmp_path)
    def delayed(request):
        response = boundary(request)
        clock[0] += 0.4
        return response
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, timeout_seconds=1, transport=httpx.MockTransport(delayed))
    with pytest.raises(ReceiptStorageError, match="time limit"):
        store.put(b"test")
    assert len(boundary.requests) == 3
    assert all(r.url.host == "api.cloudflare.com" for r in boundary.requests)


@pytest.mark.parametrize("kind", ["encoded", "oversize", "late_eof", "duplicate_metadata", "transport_secret"])
def test_hostile_stream_and_metadata(tmp_path, monkeypatch, kind):
    from services import r2_receipt_store as module
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"{}"
            clock[0] = 2.0
    def hostile(request):
        if kind == "encoded": return httpx.Response(200, headers={"content-encoding": "gzip"}, content=b"x")
        if kind == "oversize": return httpx.Response(200, headers={"content-length": "65537"}, stream=httpx.ByteStream(b""))
        if kind == "late_eof": return httpx.Response(200, stream=Stream())
        if kind == "duplicate_metadata": return httpx.Response(200, content=b'{"success":true,"success":false,"result":{}}')
        raise RuntimeError(SECRET + CONTROL)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, timeout_seconds=1, transport=httpx.MockTransport(hostile))
    with pytest.raises(ReceiptStorageError, match="time limit" if kind == "late_eof" else None) as error:
        store.put(b"test")
    assert SECRET not in str(error.value) and CONTROL not in str(error.value)


def test_capture_exact_parser_bytes_and_failed_storage_stays_missing(tmp_path, caplog):
    from services.response_receipts import capture_response
    body = b'{"amount":0,"other":null}'
    boundary = Boundary(tmp_path)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, part_max_bytes=1024, transport=httpx.MockTransport(boundary))
    response = httpx.Response(200, content=body, request=httpx.Request("GET", "https://publisher.example/source"))
    captured = capture_response(response, store)
    assert captured["storage_scope"] == "r2_private"
    assert captured["byte_check"]["status"] == "matched"
    assert captured["digest"] == hashlib.sha256(body).hexdigest()
    assert store.read(captured["digest"]) == body
    boundary.managed["enabled"] = True
    failed = capture_response(response, store)
    assert failed["byte_check"]["status"] == "missing" and failed["storage_key"] is None
    assert SECRET not in str(failed) + caplog.text and CONTROL not in str(failed) + caplog.text


@pytest.mark.parametrize("exception", [ReceiptStorageError, type("HostileSubclass", (ReceiptStorageError,), {})])
def test_same_type_and_subclass_transport_error_cannot_leak(tmp_path, caplog, exception):
    from services.response_receipts import capture_response
    def hostile(request): raise exception(SECRET + CONTROL)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, transport=httpx.MockTransport(hostile))
    captured = capture_response(httpx.Response(200, content=b"test", request=httpx.Request("GET", "https://publisher.example")), store)
    assert captured["byte_check"]["status"] == "missing"
    assert captured["failure_reason"] == "ReceiptStorageError: Receipt storage transport failed"
    assert SECRET not in str(captured) + caplog.text and CONTROL not in str(captured) + caplog.text


@pytest.mark.parametrize("errors", [None, {}, "", False, 0, [{"code": 1000, "message": "synthetic contradictory failure"}], "missing"])
@pytest.mark.parametrize("step", [1, 2, 3])
def test_privacy_error_envelope_unknown_or_contradictory_refuses(tmp_path, errors, step):
    boundary = Boundary(tmp_path)
    calls = [0]
    def contradictory(request):
        response = boundary(request)
        calls[0] += 1
        if calls[0] == step:
            envelope = json.loads(response.content)
            if errors == "missing": del envelope["errors"]
            else: envelope["errors"] = errors
            return httpx.Response(200, json=envelope)
        return response
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024, transport=httpx.MockTransport(contradictory))
    with pytest.raises(ReceiptStorageError, match="privacy metadata malformed"):
        store.put(b"test")
    assert len(boundary.requests) == step
    assert all(request.url.host == "api.cloudflare.com" for request in boundary.requests)

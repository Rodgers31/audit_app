"""Actual R2 capture recovery with inert conditional object IO; no Cloudflare."""
import hashlib

import httpx
import pytest

from services.response_receipts import capture_response
from services.r2_receipt_store import R2ReceiptStore
from services.receipt_retention import RetentionScope
from test_r2_receipt_store import Boundary, ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL


BODY = b"abcdefgh"


def source_response():
    return httpx.Response(200, content=BODY, request=httpx.Request(
        "GET", "https://source.example.test/report.pdf"))


@pytest.mark.parametrize("failure", [502, 503, "ambiguous_write"])
def test_capture_recovers_transient_second_chunk_without_overwriting(tmp_path, failure):
    boundary = Boundary(tmp_path)
    first = hashlib.sha256(BODY[:4]).hexdigest()
    path = tmp_path / "receipts-v1/chunks" / first[:2] / first
    path.parent.mkdir(parents=True)
    path.write_bytes(BODY[:4])  # The first chunk already exists, as in #838.
    second = hashlib.sha256(BODY[4:]).hexdigest()
    puts = []

    def transport(request):
        if request.method == "PUT" and request.url.path.endswith(second):
            puts.append(request)
            assert request.headers["if-none-match"] == "*"
            assert "if-none-match" in request.headers["authorization"]
            if len(puts) == 1:
                if failure == "ambiguous_write":
                    boundary(request)  # Stored, but the response never arrives.
                    raise httpx.ReadError("inert lost response", request=request)
                return httpx.Response(failure)
        return boundary(request)

    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        max_bytes=1024, part_max_bytes=4, transport=httpx.MockTransport(transport))
    receipt = capture_response(source_response(), store, source_kind="pdf")
    assert receipt["byte_check"]["status"] == "matched", receipt
    assert receipt["storage_key"] == hashlib.sha256(BODY).hexdigest()
    assert len(puts) == 2
    assert puts[0].url == puts[1].url and puts[0].content == puts[1].content == BODY[4:]
    assert Boundary(tmp_path).store().read(receipt["storage_key"]) == BODY


@pytest.mark.parametrize("phase", ["privacy", "chunk_put", "chunk_get", "manifest_put", "manifest_get"])
def test_gateway_recovery_at_every_storage_phase_records_verified_capture(tmp_path, monkeypatch, phase):
    from services import r2_receipt_store as adapter
    monkeypatch.setattr(adapter.time, "sleep", lambda delay: None)
    boundary = Boundary(tmp_path)
    failed = False

    def transport(request):
        nonlocal failed
        selected = ((phase == "privacy" and request.url.host == "api.cloudflare.com")
                    or (phase.startswith("chunk_") and "/chunks/" in request.url.path and request.method.lower() == phase.split('_')[1])
                    or (phase.startswith("manifest_") and "/manifests/" in request.url.path and request.method.lower() == phase.split('_')[1]))
        if selected and not failed:
            failed = True
            return httpx.Response(504, content=(SECRET + CONTROL).encode())
        return boundary(request)

    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        max_bytes=1024, part_max_bytes=4, transport=httpx.MockTransport(transport))
    scope = RetentionScope()
    try:
        receipt = capture_response(source_response(), store)
        assert receipt["byte_check"]["status"] == "matched"
        assert scope.summary() == dict(state="confirmed", observed=1, retained=1, missing=0, recovered=1, retry_requests=1)
    finally:
        scope.close()
    assert failed


@pytest.mark.parametrize("failure", [502, 503, 504, "timeout", "network"])
def test_exhaustion_is_bounded_and_never_certifies_partial_receipt(tmp_path, monkeypatch, failure):
    from services import r2_receipt_store as adapter
    monkeypatch.setattr(adapter.time, "sleep", lambda delay: None)
    boundary = Boundary(tmp_path)
    second = hashlib.sha256(BODY[4:]).hexdigest()
    attempts = []

    def transport(request):
        if request.method == "PUT" and request.url.path.endswith(second):
            attempts.append(request)
            if failure == "timeout":
                raise httpx.ReadTimeout(SECRET, request=request)
            if failure == "network":
                raise httpx.ConnectError(CONTROL, request=request)
            return httpx.Response(failure, content=SECRET.encode())
        return boundary(request)

    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        max_bytes=1024, part_max_bytes=4, transport=httpx.MockTransport(transport))
    scope = RetentionScope()
    try:
        receipt = capture_response(source_response(), store)
        assert receipt["storage_key"] is None and receipt["byte_check"]["status"] == "missing"
        assert SECRET not in receipt["failure_reason"] and CONTROL not in receipt["failure_reason"]
        assert scope.summary() == dict(state="missing_bytes", observed=1, retained=0, missing=1, recovered=0, retry_requests=2)
    finally:
        scope.close()
    assert len(attempts) == 3
    assert len({(str(r.url), r.content) for r in attempts}) == 1
    assert all(r.headers['if-none-match'] == '*' for r in attempts)
    assert not (tmp_path / "receipts-v1/manifests").exists()


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 409, 429, 500])
def test_non_gateway_refusals_are_not_retried(tmp_path, status):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://untrusted.example/"})
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        transport=httpx.MockTransport(transport))
    receipt = capture_response(source_response(), store)
    assert receipt["byte_check"]["status"] == "missing"
    assert len(calls) == 1 and calls[0].url.host == 'api.cloudflare.com'


def test_backoff_and_attempts_share_original_transfer_deadline(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from services import r2_receipt_store as adapter
    elapsed = [0.0]
    def sleep(seconds):
        elapsed[0] += seconds
    monkeypatch.setattr(adapter, "time", SimpleNamespace(monotonic=lambda: elapsed[0], sleep=sleep))
    calls = []
    def transport(request):
        calls.append(request)
        elapsed[0] += .3
        return httpx.Response(503)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        timeout_seconds=1, transport=httpx.MockTransport(transport))
    receipt = capture_response(source_response(), store)
    assert len(calls) == 2 and elapsed[0] == pytest.approx(.85)
    assert receipt["byte_check"]["status"] == "missing"
    assert "transfer time limit" in receipt["failure_reason"]


def test_overslept_backoff_does_not_count_a_request_that_never_started(monkeypatch):
    from types import SimpleNamespace
    from services import r2_receipt_store as adapter
    now = [0.0]
    def sleep(delay):
        now[0] += 1  # Scheduling resumes after the original transfer deadline.
    monkeypatch.setattr(adapter, 'time', SimpleNamespace(monotonic=lambda:now[0], sleep=sleep))
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(503)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
                           timeout_seconds=.5, transport=httpx.MockTransport(transport))
    scope = RetentionScope()
    try:
        receipt = capture_response(source_response(), store)
        assert receipt['byte_check']['status'] == 'missing' and len(calls) == 1
        assert scope.summary()['retry_requests'] == 0
    finally:
        scope.close()


def test_ambiguous_write_with_wrong_existing_bytes_stays_missing(tmp_path, monkeypatch):
    from services import r2_receipt_store as adapter
    monkeypatch.setattr(adapter.time, "sleep", lambda delay: None)
    boundary = Boundary(tmp_path)
    corrupted = False
    def transport(request):
        nonlocal corrupted
        if request.method == 'PUT' and not corrupted:
            boundary(request)
            path = tmp_path / request.url.path.removeprefix('/' + R2_BUCKET + '/')
            path.write_bytes(b'evil')
            corrupted = True
            raise httpx.ReadError(SECRET, request=request)
        return boundary(request)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL,
        max_bytes=1024, part_max_bytes=4, transport=httpx.MockTransport(transport))
    receipt = capture_response(source_response(), store)
    assert receipt['storage_key'] is None and receipt['byte_check']['status'] == 'missing'
    assert 'digest mismatch' in receipt['failure_reason']
    assert not (tmp_path / 'receipts-v1/manifests').exists()

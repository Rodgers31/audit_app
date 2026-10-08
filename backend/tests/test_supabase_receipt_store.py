"""Executed local REST simulation; these controls make no provider durability claim."""
import hashlib
import json
import traceback

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from services.receipt_store import LocalReceiptStore, configured_receipt_store
from services.response_receipts import capture_response, persist_receipt, seal_receipt
from services.supabase_receipt_store import ReceiptStorageError, SupabaseReceiptStore

URL = "https://abcdefghijklmnopqrst.supabase.co"
BUCKET = "receipt-evidence"
KEY = "sb_secret_" + "fake_credential_for_local_execution_123456"
BODY = b"source entity bytes\x00\xff"


class Boundary:
    """File-backed local HTTP simulation with exclusive inserts and request capture."""

    def __init__(self, root):
        self.root = root
        self.requests = []
        self.metadata = {"id": BUCKET, "public": False, "file_size_limit": 1024}
        self.read_status = 200
        self.read_headers = {}
        self.upload_status = None

    def __call__(self, request):
        self.requests.append(request)
        assert request.headers["apikey"] == KEY
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        path = request.url.path
        if path == f"/storage/v1/bucket/{BUCKET}":
            return httpx.Response(200, json=self.metadata)
        prefix = f"/storage/v1/object/{BUCKET}/sha256/"
        if request.method == "POST" and path.startswith(prefix):
            assert request.headers["x-upsert"] == "false"
            digest = path.rsplit("/", 1)[1]
            dest = self.root / digest
            try:
                with dest.open("xb") as out:
                    out.write(request.content)
                status = 200
            except FileExistsError:
                status = 400
            return httpx.Response(
                self.upload_status or status,
                content=b"provider body must never be trusted",
            )
        if request.method == "GET" and path.startswith(
            f"/storage/v1/object/authenticated/{BUCKET}/sha256/"
        ):
            dest = self.root / path.rsplit("/", 1)[1]
            return httpx.Response(
                self.read_status if dest.exists() else 404,
                content=dest.read_bytes() if dest.exists() else b"missing",
                headers=self.read_headers,
            )
        raise AssertionError(f"Unexpected operation {request.method} {path}")

    def store(self, **kwargs):
        return SupabaseReceiptStore(
            URL,
            BUCKET,
            KEY,
            max_bytes=1024,
            transport=httpx.MockTransport(self),
            **kwargs,
        )


def test_local_boundary_put_get_fresh_adapter_and_no_overwrite(tmp_path):
    boundary = Boundary(tmp_path)
    digest = boundary.store().put(BODY)
    assert digest == hashlib.sha256(BODY).hexdigest()
    # New boundary and new adapter have no shared connection/in-memory byte cache.
    fresh_boundary = Boundary(tmp_path)
    assert fresh_boundary.store().read(digest) == BODY
    assert fresh_boundary.store().put(BODY) == digest
    assert list(tmp_path.iterdir()) == [tmp_path / digest]
    changed = BODY + b"changed at same publisher URL"
    changed_digest = boundary.store().put(changed)
    assert changed_digest != digest
    assert boundary.store().read(digest) == BODY
    (tmp_path / digest).write_bytes(b"corrupt")
    with pytest.raises(ReceiptStorageError, match="digest mismatch"):
        boundary.store().read(digest)
    with pytest.raises(ReceiptStorageError, match="digest mismatch"):
        boundary.store().put(BODY)
    assert (tmp_path / digest).read_bytes() == b"corrupt"


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        [],
        {},
        "private",
        {"id": BUCKET},
        {"id": BUCKET, "public": True},
        {"id": BUCKET, "public": 0},
        {"id": "wrong", "public": False},
        {"id": BUCKET, "public": False, "file_size_limit": True},
        {"id": BUCKET, "public": False, "file_size_limit": 1023},
    ],
)
def test_bucket_unknown_or_public_refuses_before_write(tmp_path, metadata):
    boundary = Boundary(tmp_path)
    boundary.metadata = metadata
    with pytest.raises(ReceiptStorageError):
        boundary.store().put(BODY)
    assert not list(tmp_path.iterdir())
    assert len(boundary.requests) == 1


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://abcdefghijklmnopqrst.supabase.co",
        URL + "/storage/v1",
        URL + "?token=bad",
        URL + "#fragment",
        URL + ":443",
        "https://secret@abcdefghijklmnopqrst.supabase.co",
        "https://evil.example",
        "https://abcdefghijklmnopqrst.supabase.co.evil.example",
        "https://127.0.0.1",
    ],
)
def test_hostile_url_refuses_without_request(url):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(url, BUCKET, KEY)


@pytest.mark.parametrize(
    "bucket", [None, "", "../public", "public/a", "a%2fb", "Upper", "a?x", "a" * 64]
)
def test_hostile_bucket_refuses(bucket):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(URL, bucket, KEY)


@pytest.mark.parametrize(
    "key", [None, "", "sb_publishable_" + "a" * 32, "anon", KEY + "\n", "Bearer " + KEY]
)
def test_public_or_malformed_key_refuses(key):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(URL, BUCKET, key)


@pytest.mark.parametrize(
    "limit", [None, True, False, 0, -1, 1024.0, float("nan"), float("inf"), 67108865]
)
def test_direct_byte_guard(limit):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(URL, BUCKET, KEY, max_bytes=limit)


@pytest.mark.parametrize(
    "timeout", [None, True, False, 0, -1, float("nan"), float("inf"), 121, "30"]
)
def test_direct_timeout_guard(timeout):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(URL, BUCKET, KEY, timeout_seconds=timeout)


@pytest.mark.parametrize("body", [None, b"", "text", bytearray(b"bytes"), b"x" * 1025])
def test_direct_body_guard_without_network(tmp_path, body):
    boundary = Boundary(tmp_path)
    with pytest.raises(ValueError):
        boundary.store().put(body)
    assert not boundary.requests


@pytest.mark.parametrize("digest", [None, "", "../file", "A" * 64, "a" * 63, True])
def test_direct_key_guard_without_network(tmp_path, digest):
    boundary = Boundary(tmp_path)
    with pytest.raises(ValueError):
        boundary.store().read(digest)
    assert not boundary.requests


@pytest.mark.parametrize(
    "status", [201, 206, 301, 302, 307, 400, 401, 403, 404, 429, 500]
)
def test_partial_redirect_missing_denied_read_refuses(tmp_path, status):
    boundary = Boundary(tmp_path)
    digest = boundary.store().put(BODY)
    boundary.read_status = status
    with pytest.raises(ReceiptStorageError, match=f"HTTP {status}"):
        boundary.store().read(digest)
    assert all(str(r.url).startswith(URL) for r in boundary.requests)


@pytest.mark.parametrize(
    "body,headers",
    [
        (b"", {}),
        (b"hostile", {}),
        (b"x" * 1025, {}),
        (BODY, {"content-length": "invalid"}),
        (BODY, {"content-length": "-1"}),
        (BODY, {"content-length": "1025"}),
        (BODY, {"content-length": str(len(BODY) + 1)}),
        (BODY, {"content-encoding": "gzip"}),
    ],
)
def test_hostile_readback_refuses(tmp_path, body, headers):
    boundary = Boundary(tmp_path)
    digest = hashlib.sha256(BODY).hexdigest()
    (tmp_path / digest).write_bytes(body)
    boundary.read_headers = headers
    with pytest.raises(ReceiptStorageError):
        boundary.store().read(digest)


def test_stream_without_declared_size_is_bounded():
    class ChunkStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"a" * 700
            yield b"b" * 700
            raise AssertionError("must stop reading after byte cap")

    def handler(request):
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"id": BUCKET, "public": False})
        return httpx.Response(200, stream=ChunkStream())

    store = SupabaseReceiptStore(
        URL, BUCKET, KEY, max_bytes=1024, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ReceiptStorageError, match="read limit"):
        store.read(hashlib.sha256(BODY).hexdigest())


def test_transport_errors_redacted_in_receipt_and_logs(caplog):
    def failed(request):
        raise httpx.ReadError(KEY + " secret source body", request=request)

    store = SupabaseReceiptStore(
        URL, BUCKET, KEY, transport=httpx.MockTransport(failed)
    )
    response = httpx.Response(
        200,
        content=BODY,
        request=httpx.Request("GET", "https://publisher.example/data"),
    )
    receipt = capture_response(response, store)
    assert receipt["byte_check"]["status"] == "missing"
    assert (
        receipt["failure_reason"]
        == "ReceiptStorageError: Receipt storage transport failed"
    )
    assert KEY not in json.dumps(receipt) + caplog.text
    with pytest.raises(ReceiptStorageError) as error:
        store.read(hashlib.sha256(BODY).hexdigest())
    assert KEY not in "".join(traceback.format_exception(error.value))


def test_config_binding_local_and_durable_failure_never_falls_back(
    tmp_path, monkeypatch
):
    from config import secrets

    monkeypatch.setattr(
        secrets,
        "get_secret",
        lambda name: KEY if name == "RECEIPT_SUPABASE_SECRET_KEY" else None,
    )
    assert isinstance(
        configured_receipt_store(SeedingSettings(storage_path=tmp_path)),
        LocalReceiptStore,
    )
    settings = SeedingSettings(
        storage_path=tmp_path,
        receipt_storage_backend="supabase",
        receipt_supabase_url=URL,
        receipt_supabase_bucket=BUCKET,
        receipt_max_bytes=1024,
    )
    with SeedingHttpClient(settings) as client:
        assert isinstance(client.receipt_store, SupabaseReceiptStore)
    settings.receipt_supabase_url = "https://evil.example"
    with pytest.raises(ValueError):
        SeedingHttpClient(settings)
    settings.receipt_supabase_url = URL
    monkeypatch.setattr(secrets, "get_secret", lambda name: None)
    with pytest.raises(ValueError):
        configured_receipt_store(settings)
    settings.receipt_max_bytes = None
    with pytest.raises(ValueError, match="explicitly configured"):
        configured_receipt_store(settings)
    assert not (tmp_path / "response-receipts").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"receipt_storage_backend": "unknown"},
        {"receipt_max_bytes": True},
        {"receipt_max_bytes": 0},
        {"receipt_storage_timeout_seconds": float("nan")},
        {"receipt_storage_timeout_seconds": True},
    ],
)
def test_settings_shape_guards(change):
    with pytest.raises(ValueError):
        SeedingSettings(**change)


def test_pdf_fallback_binding_honors_selected_store(tmp_path, monkeypatch):
    from seeding import pdf_evidence

    boundary = Boundary(tmp_path)
    monkeypatch.setattr(
        pdf_evidence, "configured_receipt_store", lambda settings: boundary.store()
    )
    settings = SeedingSettings(
        storage_path=tmp_path,
        receipt_storage_backend="supabase",
        receipt_supabase_url=URL,
        receipt_supabase_bucket=BUCKET,
        receipt_max_bytes=1024,
    )
    client = type("Client", (), {"_settings": settings})()
    response = httpx.Response(
        200,
        content=BODY,
        headers={"content-type": "application/pdf"},
        request=httpx.Request("GET", "https://publisher.example/file.pdf"),
    )
    receipt = pdf_evidence.receipt_for_response(client, response, "fixture-parser")
    assert receipt["byte_check"]["status"] == "matched"
    assert boundary.store().read(receipt["digest"]) == BODY
    assert not (tmp_path / "response-receipts").exists()


@pytest.mark.parametrize(
    "pair",
    [
        ("a" * 64, BODY),
        (hashlib.sha256(BODY).hexdigest(), b"wrong"),
        (None, BODY),
        (hashlib.sha256(BODY).hexdigest(), None),
    ],
)
def test_capture_refuses_hostile_optimized_pair(pair):
    class BadStore:
        def put_and_read(self, body):
            return pair

    response = httpx.Response(
        200,
        content=BODY,
        request=httpx.Request("GET", "https://publisher.example/data"),
    )
    receipt = capture_response(response, BadStore())
    assert receipt["byte_check"]["status"] == "missing"
    assert receipt["storage_key"] is None


@pytest.mark.parametrize(
    "exception", [RuntimeError, OSError, ValueError, TypeError, ReceiptStorageError]
)
def test_unexpected_transport_exceptions_do_not_leak(exception, caplog):
    def failed(request):
        raise exception(KEY + " secret response")

    store = SupabaseReceiptStore(
        URL, BUCKET, KEY, transport=httpx.MockTransport(failed)
    )
    response = httpx.Response(
        200,
        content=BODY,
        request=httpx.Request("GET", "https://publisher.example/data"),
    )
    receipt = capture_response(response, store)
    assert receipt["byte_check"]["status"] == "missing"
    assert KEY not in json.dumps(receipt) + caplog.text
    assert receipt["storage_scope"] == "supabase_private"


def test_capture_and_many_fact_associations_have_bounded_storage_gets(
    tmp_path, db_session
):
    """Actual SQLite ORM persistence; file-backed REST simulation, no provider claim."""
    from models import Country, SourceDocument, GDPData, Extraction, DocumentType
    from datetime import datetime, timezone
    from sqlalchemy import select

    boundary = Boundary(tmp_path)
    response = httpx.Response(
        200,
        content=BODY,
        request=httpx.Request("GET", "https://publisher.example/data"),
    )
    receipt = capture_response(response, boundary.store())
    assert receipt["storage_scope"] == "supabase_private"
    seal_receipt(receipt, observations=[{"raw_value": "1"}])
    session = db_session
    session.add(
        Country(
            id=1,
            name="Kenya",
            iso_code="KEN",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en",
        )
    )
    source = SourceDocument(
        country_id=1,
        publisher="Publisher",
        title="Source",
        url="https://publisher.example/data",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
    )
    session.add(source)
    session.flush()
    first = persist_receipt(session, source, receipt)
    one_fact_reads = sum(
        "/object/authenticated/" in r.url.path for r in boundary.requests
    )
    assert one_fact_reads == 2  # capture + immutable persistence revalidation
    for year in range(2000, 2020):
        assert persist_receipt(session, source, receipt) is first
        session.add(
            GDPData(
                year=year,
                gdp_value=1,
                source_document_id=source.id,
                meta={
                    "source_evidence": [
                        {
                            "receipt": {
                                "extraction_id": first.id,
                                "digest": receipt["digest"],
                            }
                        }
                    ]
                },
            )
        )
    session.flush()
    rows = session.scalars(select(GDPData)).all()
    assert len(rows) == 20
    assert {r.meta["source_evidence"][0]["receipt"]["extraction_id"] for r in rows} == {
        first.id
    }
    assert len(session.scalars(select(Extraction)).all()) == 1
    assert (
        sum("/object/authenticated/" in r.url.path for r in boundary.requests)
        == one_fact_reads
    )
    receipt["byte_size"] += 1
    with pytest.raises(ValueError, match="intact captured"):
        persist_receipt(session, source, receipt)
    assert len(session.scalars(select(Extraction)).all()) == 1


def test_storage_operation_deadline_spans_requests(tmp_path, monkeypatch):
    from services import supabase_receipt_store

    boundary = Boundary(tmp_path)
    ticks = iter([0, 0, 0, 0, 31])
    monkeypatch.setattr(supabase_receipt_store.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ReceiptStorageError, match="time limit"):
        boundary.store().put(BODY)
    assert len(boundary.requests) == 1
    assert not list(tmp_path.iterdir())


def test_valid_body_with_late_eof_cannot_certify_timed_out_read():
    import time

    class LateEof(httpx.SyncByteStream):
        def __iter__(self):
            yield BODY
            time.sleep(0.12)

    def handler(request):
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"id": BUCKET, "public": False})
        return httpx.Response(200, stream=LateEof())

    store = SupabaseReceiptStore(
        URL, BUCKET, KEY, timeout_seconds=0.03, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ReceiptStorageError, match="time limit"):
        store.read(hashlib.sha256(BODY).hexdigest())

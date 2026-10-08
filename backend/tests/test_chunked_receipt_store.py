"""Strict chunk manifests and exact-source reconstruction, local simulation only."""
import hashlib
import json

import httpx
import pytest

from seeding.config import SeedingSettings
from services.supabase_receipt_store import ReceiptStorageError, SupabaseReceiptStore
from test_supabase_receipt_store import Boundary, BUCKET, KEY, URL


def store(boundary, *, part_bytes=4, max_bytes=1024):
    return SupabaseReceiptStore(
        URL,
        BUCKET,
        KEY,
        part_max_bytes=part_bytes,
        max_bytes=max_bytes,
        transport=httpx.MockTransport(boundary),
    )


@pytest.mark.parametrize(
    "body,part_count",
    [(b"abcd", 1), (b"abcde", 2), (b"abcdefghijkl", 3), (b"same" * 3, 3)],
)
def test_one_boundary_multiple_and_legitimate_repeated_parts(
    tmp_path, body, part_count
):
    boundary = Boundary(tmp_path)
    digest, retained = store(boundary).put_and_read(body)
    assert digest == hashlib.sha256(body).hexdigest()
    assert retained == body
    manifest = json.loads(boundary.object_file("manifests", digest).read_bytes())
    assert len(manifest["parts"]) == part_count
    assert [part["index"] for part in manifest["parts"]] == list(range(part_count))
    assert sum(part["byte_size"] for part in manifest["parts"]) == len(body)
    posts = [r for r in boundary.requests if r.method == "POST"]
    assert "/manifests/" in posts[-1].url.path
    assert all("/chunks/" in r.url.path for r in posts[:-1])
    assert store(Boundary(tmp_path)).read(digest) == body
    assert store(boundary).put(body) == digest
    # Manifest and chunk namespaces remain distinct even for a one-part source.
    assert boundary.object_file(
        "chunks", manifest["parts"][0]["sha256"]
    ) != boundary.object_file("manifests", digest)


def test_source_json_never_guessed_to_be_manifest(tmp_path):
    source = b'{"version":1,"type":"source-receipt-chunks","parts":[]}'
    boundary = Boundary(tmp_path)
    digest = store(boundary, part_bytes=1024).put(source)
    assert store(Boundary(tmp_path), part_bytes=1024).read(digest) == source


@pytest.mark.parametrize(
    "change",
    [
        "version_bool",
        "unknown_version",
        "type",
        "sha",
        "size_bool",
        "size_zero",
        "size_excess",
        "size_sum",
        "parts_dict",
        "parts_empty",
        "count_bool",
        "count_mismatch",
        "parts_excess",
        "index_bool",
        "index_duplicate",
        "hash_upper",
        "part_size_bool",
        "part_size_zero",
        "part_size_excess",
        "unexpected_field",
        "duplicate_field",
    ],
)
def test_hostile_manifest_refuses_before_part_downloads(tmp_path, change):
    boundary = Boundary(tmp_path)
    digest = store(boundary).put(b"abcdefgh")
    path = boundary.object_file("manifests", digest)
    manifest = json.loads(path.read_bytes())
    if change == "version_bool":
        manifest["version"] = True
    elif change == "unknown_version":
        manifest["version"] = 2
    elif change == "type":
        manifest["type"] = "anything"
    elif change == "sha":
        manifest["sha256"] = "a" * 64
    elif change == "size_bool":
        manifest["byte_size"] = True
    elif change == "size_zero":
        manifest["byte_size"] = 0
    elif change == "size_excess":
        manifest["byte_size"] = 1025
    elif change == "size_sum":
        manifest["byte_size"] = 7
    elif change == "parts_dict":
        manifest["parts"] = {}
    elif change == "parts_empty":
        manifest["parts"] = []
    elif change == "count_bool":
        manifest["part_count"] = True
    elif change == "count_mismatch":
        manifest["part_count"] = 1
    elif change == "parts_excess":
        manifest["parts"] *= 33
    elif change == "index_bool":
        manifest["parts"][0]["index"] = False
    elif change == "index_duplicate":
        manifest["parts"][1]["index"] = 0
    elif change == "hash_upper":
        manifest["parts"][0]["sha256"] = "A" * 64
    elif change == "part_size_bool":
        manifest["parts"][0]["byte_size"] = True
    elif change == "part_size_zero":
        manifest["parts"][0]["byte_size"] = 0
    elif change == "part_size_excess":
        manifest["parts"][0]["byte_size"] = 5
    elif change == "unexpected_field":
        manifest["path"] = "https://evil.example"
    if change == "duplicate_field":
        path.write_text('{"version":1,' + json.dumps(manifest)[1:])
    else:
        path.write_text(json.dumps(manifest))
    boundary.requests.clear()
    with pytest.raises(ReceiptStorageError):
        store(boundary).read(digest)
    assert not any("/chunks/" in r.url.path for r in boundary.requests)


@pytest.mark.parametrize(
    "change", ["reordered", "substituted_duplicate", "missing", "corrupt", "oversized"]
)
def test_changed_order_duplicate_missing_or_hostile_part_cannot_reconstruct(
    tmp_path, change
):
    boundary = Boundary(tmp_path)
    digest = store(boundary).put(b"abcdefgh")
    manifest_path = boundary.object_file("manifests", digest)
    manifest = json.loads(manifest_path.read_bytes())
    path = boundary.object_file("chunks", manifest["parts"][1]["sha256"])
    if change == "reordered":
        manifest["parts"].reverse()
        for i, part in enumerate(manifest["parts"]):
            part["index"] = i
        manifest_path.write_text(json.dumps(manifest))
    elif change == "substituted_duplicate":
        manifest["parts"][1]["sha256"] = manifest["parts"][0]["sha256"]
        manifest_path.write_text(json.dumps(manifest))
    elif change == "missing":
        path.unlink()
    elif change == "corrupt":
        path.write_bytes(b"nope")
    elif change == "oversized":
        path.write_bytes(b"excess")
    with pytest.raises(ReceiptStorageError):
        store(boundary).read(digest)


def test_oversized_manifest_bounded_before_download(tmp_path):
    boundary = Boundary(tmp_path)
    digest = store(boundary).put(b"abcdefgh")
    boundary.metadata["file_size_limit"] = None
    boundary.object_file("manifests", digest).write_bytes(b" " * (65536 + 1))
    boundary.requests.clear()
    with pytest.raises(ReceiptStorageError, match="size"):
        store(boundary).read(digest)
    assert not any("/chunks/" in r.url.path for r in boundary.requests)


def test_deep_json_boundary_returns_safe_refusal():
    def handler(request):
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"id": BUCKET, "public": False})
        return httpx.Response(200, content=b"[" * 32000 + b"]" * 32000)

    adapter = SupabaseReceiptStore(
        URL, BUCKET, KEY, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ReceiptStorageError, match="manifest malformed"):
        adapter.read("a" * 64)


def test_partial_insert_retry_and_manifest_last(tmp_path):
    boundary = Boundary(tmp_path)
    failed_digest = hashlib.sha256(b"efgh").hexdigest()
    fail = [True]

    def handler(request):
        if (
            request.method == "POST"
            and request.url.path.endswith(failed_digest)
            and fail[0]
        ):
            fail[0] = False
            return httpx.Response(503)
        return boundary(request)

    adapter = SupabaseReceiptStore(
        URL,
        BUCKET,
        KEY,
        max_bytes=1024,
        part_max_bytes=4,
        transport=httpx.MockTransport(handler),
    )
    digest = hashlib.sha256(b"abcdefgh").hexdigest()
    with pytest.raises(ReceiptStorageError, match="HTTP 503"):
        adapter.put(b"abcdefgh")
    assert not boundary.object_file("manifests", digest).exists()
    assert adapter.put(b"abcdefgh") == digest
    assert store(Boundary(tmp_path)).read(digest) == b"abcdefgh"


@pytest.mark.parametrize(
    "value", [None, True, False, 0, -1, 1.0, float("nan"), 33554433, "4"]
)
def test_direct_physical_cap_guards(value):
    with pytest.raises(ValueError):
        SupabaseReceiptStore(URL, BUCKET, KEY, part_max_bytes=value)


@pytest.mark.parametrize(
    "value", [True, False, 1.0, "1.0", "1e3", "NaN", "inf", "-1", "0", "33554433"]
)
def test_config_physical_cap_guards(value):
    with pytest.raises(ValueError):
        SeedingSettings(receipt_part_max_bytes=value)


def test_too_many_parts_refuses_before_storage(tmp_path):
    boundary = Boundary(tmp_path)
    with pytest.raises(ValueError, match="too many parts"):
        store(boundary, part_bytes=1).put(b"x" * 65)
    assert not boundary.requests


def test_part_count_preflight_refuses_before_any_source_slice(tmp_path):
    class SliceProbe(bytes):
        def __getitem__(self, key):
            raise AssertionError("Part allocation occurred before count refusal")

    boundary = Boundary(tmp_path)
    with pytest.raises(ValueError, match="too many parts"):
        store(boundary, part_bytes=1).put(SliceProbe(b"x" * 65))
    assert not boundary.requests


def test_bucket_cap_applies_physical_objects_not_logical_source(tmp_path):
    boundary = Boundary(tmp_path)
    # 1400 logical bytes exceed this simulated 1024-byte bucket object cap.
    body = bytes(range(250)) * 5 + bytes(range(150))
    adapter = store(boundary, part_bytes=700, max_bytes=2048)
    digest = adapter.put(body)
    assert adapter.read(digest) == body
    assert all(len(r.content) <= 1024 for r in boundary.requests if r.method == "POST")

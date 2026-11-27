"""Private transport, reviewed byte identity, and independent runner isolation."""

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import httpx
import pytest
import yaml

from seeding import county_archive, source_cache

SIGNED_URL = (
    "https://"
    + "1" * 32
    + ".r2.cloudflarestorage.com/private-receipts/"
    + county_archive.ARCHIVE_FILENAME
    + "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature="
    + "2" * 64
)


@pytest.fixture
def reviewed(monkeypatch):
    authority = {}
    documents = []
    members = {}
    entries = []
    for source_id, url in enumerate(source_cache.reviewed_sources(), 1):
        body = f"%PDF-1.4\nCounty fixture {source_id}\n%%EOF\n".encode()
        sha, md5 = hashlib.sha256(body).hexdigest(), hashlib.md5(body).hexdigest()
        name = hashlib.sha256(url.encode()).hexdigest() + ".pdf"
        locator = "/".join((*source_cache.CACHE_PARTS, name))
        members[locator] = body
        authority[url] = {"url": url, "sha256": sha, "md5": md5}
        documents.append(
            SimpleNamespace(
                id=source_id,
                url=url,
                md5=md5,
                file_path=locator,
                meta={},
                publisher="Office of the Auditor-General",
                title="County fixture",
                status="AVAILABLE",
                doc_type="AUDIT",
            )
        )
        entries.append(
            {
                "source_id": source_id,
                "source_url": url,
                "path": locator,
                "sha256": sha,
                "md5": md5,
                "bytes": len(body),
                "profile": "county",
            }
        )
    members["manifest.json"] = json.dumps(
        {
            "version": 1,
            "kind": "reviewed_pdf_bytes",
            "entries": entries,
        }
    ).encode()
    monkeypatch.setattr(source_cache, "reviewed_sources", lambda profile: authority)
    return documents, members


def _pin(monkeypatch, members):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    payload = buffer.getvalue()
    monkeypatch.setattr(county_archive, "ARCHIVE_BYTES", len(payload))
    monkeypatch.setattr(
        county_archive, "ARCHIVE_SHA256", hashlib.sha256(payload).hexdigest()
    )
    return payload


class ArchiveStream(httpx.SyncByteStream):
    def __init__(self, payload):
        self.payload = payload

    def __iter__(self):
        yield self.payload


def test_each_runner_restores_all_eight_without_publisher_or_secret_log(
    reviewed, monkeypatch, tmp_path, caplog
):
    documents, members = reviewed
    payload = _pin(monkeypatch, members)
    calls = []

    def request(req):
        assert str(req.url) == SIGNED_URL
        assert req.headers["accept-encoding"] == "identity"
        calls.append(req.method)
        return httpx.Response(200, stream=ArchiveStream(payload))

    with (
        caplog.at_level("INFO", logger="httpx"),
        httpx.Client(transport=httpx.MockTransport(request)) as client,
    ):
        for fetch, name in ((False, "seed"), (True, "validator")):
            root = tmp_path / name
            root.mkdir()
            result = source_cache.prepare_sources(
                documents,
                root=root,
                fetch=fetch,
                client=client,
                county_archive_url=SIGNED_URL,
            )
            assert result["ready"] and result["county_archive"] == "restored"
            assert result["database_mutations"] is False
            assert len(result["entries"]) == 8
            for entry in result["entries"]:
                path = root / entry["file_path"]
                assert path.read_bytes() == members[entry["file_path"]]
                sidecar = json.loads(path.with_suffix(".json").read_text())
                assert sidecar["restored_from"] == "county_archive"
                assert sidecar["fingerprint"] is None
            cached = source_cache.prepare_sources(
                documents,
                root=root,
                fetch=fetch,
                client=client,
                county_archive_url=SIGNED_URL,
            )
            assert cached["ready"] and cached["county_archive"] == "not_needed"
    assert calls == ["GET", "GET"]
    assert "X-Amz-Signature" not in caplog.text


def test_archive_cache_hit_preserves_existing_publisher_bookkeeping(
    reviewed, monkeypatch, tmp_path
):
    from seeding.config import SeedingSettings
    from seeding.fetch_documents import fetch_document
    from models import DocumentStatus, DocumentType

    documents, members = reviewed
    payload = _pin(monkeypatch, members)
    doc = documents[0]
    pdf = tmp_path / doc.file_path
    pdf.parent.mkdir(parents=True)
    pdf.with_suffix(".json").write_text('{"orphaned":true}')

    def download(req):
        assert str(req.url) == SIGNED_URL
        return httpx.Response(200, stream=ArchiveStream(payload))

    with httpx.Client(transport=httpx.MockTransport(download)) as client:
        result = source_cache.prepare_sources(
            documents, root=tmp_path, client=client, county_archive_url=SIGNED_URL
        )
    assert result["ready"]
    assert (
        json.loads(pdf.with_suffix(".json").read_text())["restored_from"]
        == "county_archive"
    )
    old_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    doc.last_verified_at = doc.last_seen_at = old_date
    doc.http_status = None
    doc.country_id = 1
    doc.status = DocumentStatus.AVAILABLE
    doc.doc_type = DocumentType.AUDIT
    monkeypatch.chdir(tmp_path)

    class Session:
        def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: doc)

        def flush(self):
            pass

    fetched = fetch_document(
        Session(),
        None,
        SeedingSettings(_env_file=None, cache_path=pdf.parent.parent),
        url=doc.url,
        country_id=1,
        publisher=doc.publisher,
        title="New listing title",
        doc_type=doc.doc_type,
        dataset_id="oag_county_audits",
    )
    assert fetched is doc
    assert doc.last_verified_at == doc.last_seen_at == old_date
    assert doc.http_status is None
    assert doc.title == "County fixture"
    assert "pdf_artifact_v1" not in doc.meta
    assert doc.meta["audit_acquisition_origin_v1"]["origin_qualified"] is False


@pytest.mark.parametrize("status", [None, 403, 404, 503, "timeout"])
def test_unavailable_private_archive_keeps_existing_official_fallback(
    status, reviewed, tmp_path
):
    documents, members = reviewed
    official = {doc.url: members[doc.file_path] for doc in documents}
    calls = []

    def request(req):
        url = str(req.url)
        calls.append(url)
        if url == SIGNED_URL:
            if status == "timeout":
                raise httpx.ReadTimeout("fixture", request=req)
            return httpx.Response(status)
        return httpx.Response(200, content=official[url])

    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        result = source_cache.prepare_sources(
            documents,
            root=tmp_path,
            fetch=True,
            client=client,
            county_archive_url=SIGNED_URL if status else "",
        )
    assert result["ready"]
    assert result["county_archive"] == ("unavailable" if status else "unconfigured")
    assert calls == ([SIGNED_URL] if status else []) + list(official)
    for doc in documents:
        sidecar = json.loads(
            (tmp_path / doc.file_path).with_suffix(".json").read_text()
        )
        assert "restored_from" not in sidecar


@pytest.mark.parametrize("case", ["host", "redirect", "digest", "extra", "last_pdf"])
def test_tampered_archive_refuses_before_any_install_or_publisher_fallback(
    case, reviewed, monkeypatch, tmp_path
):
    documents, members = reviewed
    if case == "extra":
        members["../unexpected.pdf"] = b"extra"
    if case == "last_pdf":
        path = documents[-1].file_path
        members[path] = members[path].replace(b"County", b"county")
    payload = _pin(monkeypatch, members)
    if case == "digest":
        payload = bytes([payload[0] ^ 1]) + payload[1:]
    url = (
        SIGNED_URL.replace("r2.cloudflarestorage.com", "example.invalid")
        if case == "host"
        else SIGNED_URL
    )
    calls = []

    def request(req):
        assert str(req.url) == SIGNED_URL
        calls.append(req.method)
        if case == "redirect":
            return httpx.Response(302, headers={"location": "https://example.invalid/"})
        return httpx.Response(200, stream=ArchiveStream(payload))

    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(
            (county_archive.CountyArchiveRefused, source_cache.SourceCacheRefused)
        ):
            source_cache.prepare_sources(
                documents,
                root=tmp_path,
                fetch=True,
                client=client,
                county_archive_url=url,
            )
    assert calls == ([] if case == "host" else ["GET"])
    assert list(tmp_path.iterdir()) == []


def test_nightly_seed_restores_after_shared_cache_and_refuses_to_publish_private_bytes():
    path = Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml"
    jobs = yaml.safe_load(path.read_text())["jobs"]
    seed = {step.get("id"): step for step in jobs["seed"]["steps"]}
    validation = next(
        step
        for step in jobs["validate"]["steps"]
        if step.get("name") == "Prepare reviewed retained county-source bytes"
    )
    positions = list(seed)
    assert positions.index("database") < positions.index("restore_pdfs")
    assert positions.index("restore_pdfs") < positions.index("county_archive")
    assert positions.index("county_archive") < positions.index("cli")
    assert "--county-archive" in seed["county_archive"]["run"]
    assert "--fetch --county-archive" in validation["run"]
    assert seed["county_archive"]["env"][county_archive.ARCHIVE_URL_ENV] == (
        validation["env"][county_archive.ARCHIVE_URL_ENV]
    )
    assert (
        "steps.county_archive.outputs.shared_cache_safe == 'true'"
        in seed["save_pdfs"]["if"]
    )
    assert 'status in {"not_needed", "unavailable"}' in seed["county_archive"]["run"]


def test_writer_requires_archive_step_success_on_the_ordinary_audit_plan():
    from seeding.current_run import PRIOR_STEPS, prior_steps_success
    from seeding.source_plan import SourcePlan

    steps = {
        name: {"outcome": "success", "conclusion": "success", "outputs": {}}
        for name in PRIOR_STEPS
    }
    audit = SourcePlan(("audits",), False, False)
    assert prior_steps_success(steps, "success", audit)

    steps["county_archive"]["outcome"] = "failure"
    assert not prior_steps_success(steps, "success", audit)

    steps["county_archive"].update(outcome="skipped", conclusion="skipped")
    assert not prior_steps_success(steps, "success", audit)
    assert prior_steps_success(
        steps, "success", SourcePlan(("population",), False, False)
    )

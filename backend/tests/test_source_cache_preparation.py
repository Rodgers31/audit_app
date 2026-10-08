"""Offline HTTP artifacts; SHA checks and filesystem installation are real."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from seeding import pdf_artifact, source_cache as cache
from seeding.domains.audits import observation as obs
from seeding.domains.audits.scope import AuditSourceScopeError
from seeding.oag_discovery import OagDocument, OAG_ORIGIN


@pytest.fixture
def sources(monkeypatch):
    reviewed = cache.reviewed_sources()
    entry = next(iter(obs.accepted_editions().values()))
    url = entry["url"]
    body = b"%PDF-1.4\nexplicit offline artifact fixture\n%%EOF\n"
    entry = {
        **entry,
        "sha256": hashlib.sha256(body).hexdigest(),
        "md5": hashlib.md5(body).hexdigest(),
    }
    authority = {url: entry}
    monkeypatch.setattr(
        cache, "reviewed_sources", lambda profile="county": copy.deepcopy(authority)
    )
    name = hashlib.sha256(url.encode()).hexdigest() + ".pdf"
    doc = SimpleNamespace(
        id=17,
        url=url,
        md5=entry["md5"],
        publisher="Office of the Auditor-General",
        title="Retained fixture",
        doc_type="AUDIT",
        status="AVAILABLE",
        country_id=1,
        file_path="/".join((*cache.CACHE_PARTS, name)),
        meta={"extracted_md5": entry["md5"]},
    )
    return [doc], authority, body


def client_for(body, *, status=200, headers=None, calls=None):
    def request(req):
        if calls is not None:
            calls.append(str(req.url))
        return httpx.Response(
            status, content=body, headers=headers or {"content-type": "application/pdf"}
        )

    return httpx.Client(transport=httpx.MockTransport(request))


def test_empty_preview_reports_missing_without_files_or_network(sources, tmp_path):
    docs, _, _ = sources
    result = cache.prepare_sources(docs, root=tmp_path)
    assert result["ready"] is False and result["entries"][0]["state"] == "missing"
    assert list(tmp_path.iterdir()) == []


def test_restore_then_repeat_checks_exact_bytes_without_network_or_document_changes(
    sources, tmp_path
):
    docs, authority, body = sources
    original = copy.deepcopy(docs[0].__dict__)
    calls = []
    with client_for(body, calls=calls) as client:
        r = cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
        again = cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert r["ready"] and again["ready"] and calls == [docs[0].url]
    assert docs[0].__dict__ == original
    path = tmp_path / docs[0].file_path
    assert (
        pdf_artifact.file_identity(path)["sha256"] == authority[docs[0].url]["sha256"]
    )
    sidecar = json.loads(path.with_suffix(".json").read_text())
    assert (
        sidecar["url"] == docs[0].url
        and sidecar["sha256"] == authority[docs[0].url]["sha256"]
    )
    from seeding.pdf_download import _fresh_cache_hit

    assert _fresh_cache_hit(path, path.with_suffix(".json"), 3600) is not None
    assert not list(path.parent.glob(".retained-*"))


@pytest.mark.parametrize(
    "body,status,headers",
    [
        (b"<html>challenge</html>", 200, {"content-type": "text/html"}),
        (b"%PDF-1.4\ntruncated", 200, {"content-type": "application/pdf"}),
        (b"%PDF-1.4\nwrong edition\n%%EOF", 200, {"content-type": "application/pdf"}),
        (b"ignored", 302, {"location": "https://example.invalid/other.pdf"}),
        (b"error", 503, {"content-type": "text/plain"}),
    ],
)
def test_refused_response_never_installs_source_or_sidecar(
    sources, tmp_path, body, status, headers
):
    docs, _, _ = sources
    with client_for(body, status=status, headers=headers) as client:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not (tmp_path / docs[0].file_path).exists()
    assert not list(tmp_path.rglob(".retained-*"))
    assert docs[0].meta == {"extracted_md5": docs[0].md5}


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", True),
        ("publisher", "Other"),
        ("status", "ARCHIVED"),
        ("doc_type", "BUDGET"),
        ("md5", "0" * 32),
        ("file_path", "../outside.pdf"),
        ("file_path", "/app/data/seeding/cache/pdfs/a.pdf"),
        ("meta", None),
        ("title", ""),
        ("meta", {"extracted_md5": "0" * 32}),
    ],
)
def test_complete_identity_preflight_refuses_before_any_files_or_http(
    sources, tmp_path, field, value
):
    docs, _, body = sources
    setattr(docs[0], field, value)
    calls = []
    with client_for(body, calls=calls) as client:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_duplicate_or_missing_registered_document_refuses(sources, tmp_path):
    docs, _, _ = sources
    for values in [[], docs + docs]:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(values, root=tmp_path)


def test_valid_but_different_existing_bytes_are_preserved_and_refused(
    sources, tmp_path
):
    docs, _, body = sources
    path = tmp_path / docs[0].file_path
    path.parent.mkdir(parents=True)
    wrong = b"%PDF-1.4\nexisting wrong edition\n%%EOF"
    path.write_bytes(wrong)
    calls = []
    with client_for(body, calls=calls) as client:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert path.read_bytes() == wrong and calls == []


@pytest.mark.parametrize("component", ["data", "file"])
def test_symlink_path_cannot_escape_explicit_root(sources, tmp_path, component):
    docs, _, body = sources
    outside = tmp_path / "outside"
    outside.mkdir()
    path = tmp_path / docs[0].file_path
    if component == "data":
        (tmp_path / "data").symlink_to(outside, target_is_directory=True)
    else:
        path.parent.mkdir(parents=True)
        target = outside / "other.pdf"
        target.write_bytes(body)
        path.symlink_to(target)
    with client_for(body) as client:
        with pytest.raises((OSError, cache.SourceCacheRefused)):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert list(outside.iterdir()) == (
        [] if component == "data" else [outside / "other.pdf"]
    )


@pytest.mark.parametrize("value", [True, None, float("nan"), float("inf"), 0, 301])
def test_nonfinite_unbounded_or_untyped_deadline_refuses(sources, tmp_path, value):
    docs, _, _ = sources
    with pytest.raises(cache.SourceCacheRefused):
        cache.prepare_sources(docs, root=tmp_path, max_seconds=value)


def test_byte_cap_refuses_and_cleans_staging(sources, tmp_path, monkeypatch):
    docs, _, body = sources
    monkeypatch.setattr(cache, "MAX_BYTES", 10)
    with client_for(body) as client:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not (tmp_path / docs[0].file_path).exists() and not list(
        tmp_path.rglob(".retained-*")
    )


def test_transport_failure_is_visible_without_replacing_source(sources, tmp_path):
    docs, _, _ = sources

    def refuse(req):
        raise httpx.ReadTimeout("owned transport seam")

    with httpx.Client(transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(httpx.ReadTimeout):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not (tmp_path / docs[0].file_path).exists() and not list(
        tmp_path.rglob(".retained-*")
    )


def test_concurrent_correct_install_verified_without_overwrite(
    sources, tmp_path, monkeypatch
):
    docs, _, body = sources
    original = cache.os.link

    def win(src, dst, **kwargs):
        fd = cache.os.open(
            dst,
            cache.os.O_WRONLY | cache.os.O_CREAT | cache.os.O_EXCL,
            0o600,
            dir_fd=kwargs["dst_dir_fd"],
        )
        with cache.os.fdopen(fd, "wb") as f:
            f.write(body)
        return original(src, dst, **kwargs)

    monkeypatch.setattr(cache.os, "link", win)
    with client_for(body) as client:
        r = cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert r["ready"] and (tmp_path / docs[0].file_path).read_bytes() == body


def test_original_strict_verifier_missing_byte_failure_then_actual_byte_gate_passes(
    sources, tmp_path, monkeypatch
):
    docs, authority, body = sources
    doc = docs[0]
    entry = authority[doc.url]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(obs, "accepted_editions", lambda: authority)
    doc.meta.update(
        dataset_id="oag_county_audits",
        oag_discovery={
            "fiscal_year": entry["fiscal_year"],
            "kind": entry["institution"],
            "listed_at": f"{OAG_ORIGIN}/{entry['fiscal_year'].replace('/','-')}-county-government-audit-reports/",
        },
        last_extraction_attempt={"status": "complete"},
        extraction_stats={
            "extractor": "oag_county_volume",
            "fiscal_year": entry["fiscal_year"],
            "volume_kind": entry["institution"],
            "partial": False,
            "chapters_attributed": 47,
            "contents_entries": 47,
            "pages": entry["pages"],
            "findings": 47,
            "rejected_cid": 0,
            "refused": [],
            "chapters_with_no_finding": [],
            "unreadable_chapter_pages": [],
            "missing_counties": [],
        },
    )
    from models import DocumentStatus, DocumentType

    doc.status = DocumentStatus.AVAILABLE
    doc.doc_type = DocumentType.AUDIT
    session = SimpleNamespace(
        execute=lambda query: SimpleNamespace(scalar_one_or_none=lambda: doc),
        get=lambda model, id: SimpleNamespace(iso_code="KEN"),
    )
    volume = OagDocument(
        doc.url,
        entry["fiscal_year"],
        entry["institution"],
        "year_page",
        doc.meta["oag_discovery"]["listed_at"],
    )

    class NextStrictBoundary(Exception):
        pass

    def next_boundary(*args):
        raise NextStrictBoundary(
            "byte identity passed; extraction/cohort verification follows"
        )

    monkeypatch.setattr(obs, "verify_extraction_evidence", next_boundary)
    from seeding.http_client import PdfDownloadError

    with pytest.raises(PdfDownloadError, match="could not read downloaded file"):
        obs.verify_adopted_volume(session, volume)
    with client_for(body) as client:
        cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    with pytest.raises(NextStrictBoundary):
        obs.verify_adopted_volume(session, volume)


def test_packaged_authority_profiles_are_exact_and_do_not_approve_2391():
    county = cache.reviewed_sources("county")
    reviewed = cache.reviewed_sources("reviewed")
    assert len(county) == 8 and len(reviewed) == 11 and set(county) <= set(reviewed)
    assert not any("Homa-Bay-2021-2022" in url for url in reviewed)
    assert all(
        entry["sha256"] != hashlib.sha256(url.encode()).hexdigest()
        for url, entry in reviewed.items()
    )
    legacy = Path(cache.__file__).with_name("retained-audit-legacy-manifest.json")
    assert (
        hashlib.sha256(legacy.read_bytes()).hexdigest() == cache.LEGACY_MANIFEST_SHA256
    )


def test_backend_only_packaging_preserves_authority_and_executable(tmp_path):
    import shutil, subprocess, sys, os

    backend = Path(__file__).resolve().parents[1]
    packaged = tmp_path / "app"
    packaged.mkdir()
    # Backend deployment includes the shared receipt/publication services and
    # their models; a seeding-only copy no longer represents that package.
    for package in ("seeding", "services"):
        shutil.copytree(
            backend / package,
            packaged / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for module in ("models.py", "database.py", "db_url.py"):
        shutil.copy2(backend / module, packaged / module)
    env = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": "postgresql+psycopg2://fixture:fixture@127.0.0.1:65534/fixture",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'from pathlib import Path; import seeding.source_cache as cache; '
            'import services.receipt_store as receipts; '
            'assert Path(cache.__file__).resolve().is_relative_to(Path.cwd()); '
            'assert Path(receipts.__file__).resolve().is_relative_to(Path.cwd()); '
            'assert len(cache.reviewed_sources("county"))==8; '
            'assert len(cache.reviewed_sources("reviewed"))==11',
        ],
        cwd=packaged,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    help_result = subprocess.run(
        [sys.executable, "-m", "seeding.source_cache", "--help"],
        cwd=packaged,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert help_result.returncode == 0 and "--fetch" in help_result.stdout
    assert not (packaged / "docs").exists() and not (packaged / "tools").exists()


def test_validation_runner_restores_then_prepares_then_runs_full_gates():
    import yaml

    path = Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml"
    steps = yaml.safe_load(path.read_text())["jobs"]["validate"]["steps"]
    names = [step.get("name") for step in steps]
    assert (
        names.index("Restore retained source PDFs for validation")
        < names.index("Prepare reviewed retained county-source bytes")
        < names.index("Validate seeded data")
    )
    preparation = next(
        s
        for s in steps
        if s.get("name") == "Prepare reviewed retained county-source bytes"
    )
    assert "--profile county --fetch" in preparation["run"]
    assert (
        "continue-on-error" not in preparation and "|| true" not in preparation["run"]
    )
    restore = next(
        s
        for s in steps
        if s.get("name") == "Restore retained source PDFs for validation"
    )
    assert restore["with"]["path"] == "backend/data/seeding/cache/pdfs"


def test_deadline_expiring_during_transfer_cannot_install_verified_bytes(
    sources, tmp_path, monkeypatch
):
    docs, _, body = sources
    clock = iter([0, 0, 301])
    monkeypatch.setattr(cache.time, "monotonic", lambda: next(clock))
    with client_for(body) as client:
        with pytest.raises(cache.SourceCacheRefused, match="deadline"):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not (tmp_path / docs[0].file_path).exists() and not list(
        tmp_path.rglob(".retained-*")
    )


def artifact_for(doc, authority, body):
    return {
        "schema_version": 1,
        "sha256": authority[doc.url]["sha256"],
        "md5": doc.md5,
        "size_bytes": len(body),
        "source_document_id": doc.id,
        "source_url": doc.url,
        "report_title": doc.title,
        "publisher": doc.publisher,
        "validation": "pdf_magic_and_final_eof",
        "verification_time": None,
        "verification_time_reason": "download_time_not_available",
    }


def test_valid_existing_artifact_binding_is_checked_and_preserved(sources, tmp_path):
    docs, authority, body = sources
    docs[0].meta["pdf_artifact_v1"] = artifact_for(docs[0], authority, body)
    before = copy.deepcopy(docs[0].__dict__)
    with client_for(body) as client:
        r = cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert r["ready"] and docs[0].__dict__ == before


@pytest.mark.parametrize(
    "field,value",
    [("sha256", "0" * 64), ("source_document_id", True), ("report_title", "different")],
)
def test_changed_artifact_association_refuses_before_http(
    sources, tmp_path, field, value
):
    docs, authority, body = sources
    artifact = artifact_for(docs[0], authority, body)
    artifact[field] = value
    docs[0].meta["pdf_artifact_v1"] = artifact
    calls = []
    with client_for(body, calls=calls) as client:
        with pytest.raises(cache.SourceCacheRefused):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not calls and list(tmp_path.iterdir()) == []


def test_artifact_size_contradiction_cannot_install_matching_sha_bytes(
    sources, tmp_path
):
    docs, authority, body = sources
    artifact = artifact_for(docs[0], authority, body)
    artifact["size_bytes"] = 1
    docs[0].meta["pdf_artifact_v1"] = artifact
    with client_for(body) as client:
        with pytest.raises(cache.SourceCacheRefused, match="binding"):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not (tmp_path / docs[0].file_path).exists()


def test_detached_cache_directory_cannot_report_ready(sources, tmp_path):
    docs, _, body = sources
    path = tmp_path / docs[0].file_path

    def request(req):
        path.parent.rename(tmp_path / "detached")
        path.parent.mkdir()
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(cache.SourceCacheRefused, match="directory changed"):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not path.exists()


def test_earlier_verified_file_replaced_during_later_download_refuses(
    sources, tmp_path, monkeypatch
):
    docs, authority, body = sources
    second = copy.deepcopy(docs[0])
    second.id = 18
    second.url = "https://www.oagkenya.go.ke/wp-content/uploads/fixture-second.pdf"
    second.file_path = "/".join(
        (*cache.CACHE_PARTS, hashlib.sha256(second.url.encode()).hexdigest() + ".pdf")
    )
    authority[second.url] = {**authority[docs[0].url], "url": second.url}
    monkeypatch.setattr(cache, "reviewed_sources", lambda profile="county": authority)
    first = tmp_path / docs[0].file_path
    first.parent.mkdir(parents=True)
    first.write_bytes(body)
    wrong = b"%PDF-1.4\nconcurrent wrong edition\n%%EOF\n"

    def request(req):
        first.write_bytes(wrong)
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(cache.SourceCacheRefused, match="reviewed edition"):
            cache.prepare_sources(
                docs + [second], root=tmp_path, fetch=True, client=client
            )
    assert first.read_bytes() == wrong


def test_staging_locator_swapped_at_link_cannot_install_bad_file_or_sidecar(
    sources, tmp_path, monkeypatch
):
    docs, _, body = sources
    link = cache.os.link
    path = tmp_path / docs[0].file_path

    def raced_link(src, dst, **kwargs):
        staging = path.parent / src
        staging.unlink()
        staging.write_bytes(b"%PDF-1.4\nwrong staging replacement\n%%EOF\n")
        return link(src, dst, **kwargs)

    monkeypatch.setattr(cache.os, "link", raced_link)
    with client_for(body) as client:
        with pytest.raises(cache.SourceCacheRefused, match="reviewed edition"):
            cache.prepare_sources(docs, root=tmp_path, fetch=True, client=client)
    assert not path.exists() and not path.with_suffix(".json").exists()
    assert not list(path.parent.glob(".retained-*"))


def test_fifo_at_retained_locator_is_refused_without_blocking(tmp_path):
    import os
    import subprocess
    import sys

    os.mkfifo(tmp_path / "retained.pdf")
    script = """
import os, sys
from seeding.source_cache import _verify, SourceCacheRefused
fd = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
try:
    try:
        _verify(fd, "retained.pdf", {"sha256": "0" * 64, "md5": "0" * 32})
    except SourceCacheRefused as exc:
        assert "regular file" in str(exc)
    else:
        raise AssertionError("FIFO accepted as retained PDF")
finally:
    os.close(fd)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "retained.pdf").is_fifo()

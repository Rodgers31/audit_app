"""Actual artifact producer and source-bound historical county read path."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from models import Audit, DocumentType, Entity, EntityType, Extraction
from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.extractors import oag_county_volume as cv
from seeding.extractors.oag_blue_book import PageText, source_hash_of
from seeding.fetch_documents import fetch_document
from seeding.types import DomainRunContext

FX_PATH = Path(__file__).parent / "fixtures/oag_nyamira_historical.json"
CTX = DomainRunContext(since=None, dry_run=False)


@pytest.mark.parametrize("legacy", [True, False])
def test_cached_volume_check_avoids_full_finding_transfer(historical_world, legacy):
    """Cached checks need a scalar or bindings, never complete finding rows."""
    from types import SimpleNamespace
    from sqlalchemy import event
    from seeding.pdf_artifact import ARTIFACT_KEY

    session, doc, _ = historical_world
    metadata = dict(doc.meta, extracted_md5=doc.md5)
    if legacy:
        metadata.pop(ARTIFACT_KEY)
    doc.meta = metadata
    session.flush()
    snapshot = SimpleNamespace(id=doc.id, md5=doc.md5, meta=copy.deepcopy(metadata))
    session.expunge_all()
    loaded, columns = [], []

    def capture_row(current_session, row):
        if isinstance(row, Extraction):
            loaded.append(row)

    def capture_columns(conn, cursor, statement, parameters, context, executemany):
        columns.extend(item[0] for item in (cursor.description or []))

    event.listen(session, "loaded_as_persistent", capture_row)
    event.listen(session.bind, "after_cursor_execute", capture_columns)
    try:
        assert cv.already_extracted(session, snapshot) == 2
    finally:
        event.remove(session, "loaded_as_persistent", capture_row)
        event.remove(session.bind, "after_cursor_execute", capture_columns)
    assert not loaded, "skip check materialized full Extraction objects"
    assert "extractions_extracted_json" not in columns


@pytest.mark.parametrize("state", [
    "legacy_current", "legacy_stale", "bound_current", "bound_missing",
    "bound_invalid", "bound_artifact_mismatch", "bound_no_rows",
])
def test_cached_volume_projection_preserves_binding_decisions(historical_world, state):
    from types import SimpleNamespace
    from seeding.pdf_artifact import ARTIFACT_KEY, BINDING_KEY

    session, doc, _ = historical_world
    metadata = dict(doc.meta, extracted_md5=doc.md5)
    if state.startswith("legacy"):
        metadata.pop(ARTIFACT_KEY)
    if state == "legacy_stale":
        metadata["extracted_md5"] = "0" * 32
    doc.meta = metadata
    if state in ("bound_missing", "bound_invalid", "bound_artifact_mismatch"):
        row = session.query(Extraction).first()
        payload = copy.deepcopy(row.extracted_json)
        if state == "bound_missing":
            payload.pop(BINDING_KEY)
        elif state == "bound_invalid":
            payload[BINDING_KEY] = ["malformed"]
        else:
            payload[BINDING_KEY]["artifact"]["sha256"] = "1" * 64
        row.extracted_json = payload
    session.flush()
    snapshot = SimpleNamespace(
        id=99999 if state == "bound_no_rows" else doc.id,
        md5=doc.md5, meta=copy.deepcopy(metadata),
    )
    expected = 2 if state in ("legacy_current", "bound_current") else 0
    assert cv.already_extracted(session, snapshot) == expected


def fetch(session, country, settings, path, monkeypatch, url=None):
    fx = json.loads(FX_PATH.read_text())
    monkeypatch.setattr(
        "seeding.fetch_documents.get_or_download_pdf", lambda *a, **k: path
    )
    return fetch_document(
        session,
        None,
        settings,
        url=url or fx["source_url"],
        country_id=country.id,
        publisher="Office of the Auditor-General",
        title="County Assemblies 2023/2024",
        doc_type=DocumentType.AUDIT,
    )


def test_fetch_records_real_pdf_identity_not_url_or_json_hash(
    db_session, seed_country, tmp_path, monkeypatch
):
    from test_oag_county_volume import _hand_made_pdf

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    doc = fetch(db_session, seed_country, settings, path, monkeypatch)
    identity = doc.meta.get("pdf_artifact_v1")
    assert isinstance(
        identity, dict
    ), "successful validated fetch must retain PDF-byte identity"
    assert identity["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert identity["md5"] == doc.md5 == hashlib.md5(path.read_bytes()).hexdigest()
    assert identity["sha256"] != hashlib.sha256(doc.url.encode()).hexdigest()
    assert identity["verification_time"] is None
    doc.meta = dict(
        doc.meta, later={"preserve": True}, pdf_artifact_v2={"future": True}
    )
    again = fetch(db_session, seed_country, settings, path, monkeypatch)
    assert again.meta["pdf_artifact_v1"] == identity
    assert again.meta["later"] == {"preserve": True}
    assert again.meta["pdf_artifact_v2"] == {"future": True}
    path.write_bytes(
        path.read_bytes().replace(b"VISIBLE PAGE TEXT", b"REISSUED CONTENT")
    )
    changed = fetch(db_session, seed_country, settings, path, monkeypatch)
    assert changed.meta["pdf_artifact_v1"]["sha256"] != identity["sha256"]
    assert changed.meta["previous_pdf_artifacts_v1"] == [identity]


def test_normal_volume_extraction_binds_each_finding_at_the_read_boundary(
    db_session, seed_country, tmp_path, monkeypatch
):
    from test_oag_county_volume import TestExtractionRows, _hand_made_pdf

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    doc = fetch(
        db_session,
        seed_country,
        settings,
        path,
        monkeypatch,
        url="https://www.oagkenya.go.ke/COUNTY-EXECUTIVES-2024-2025.pdf",
    )
    pages = TestExtractionRows.PAGES
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: pages)
    known = {
        cv._letters(n): n
        for n in [
            "Mombasa",
            "Taita Taveta",
            "Atlantis",
            *__import__("test_oag_county_volume")._FILLER,
        ]
    }
    cv.extract_county_volume(db_session, doc, settings, known_counties=known)
    rows = db_session.query(Extraction).filter_by(source_document_id=doc.id).all()
    assert rows
    binding = rows[0].extracted_json.get("pdf_artifact_binding_v1")
    assert isinstance(
        binding, dict
    ), "a document-level current hash cannot bind an older extraction"
    assert binding["artifact"] == doc.meta["pdf_artifact_v1"]
    assert binding["text_visibility"] == "visible_only"
    assert binding["pdf_pages"] == len(pages)
    assert all(r.extracted_json["pdf_artifact_binding_v1"] == binding for r in rows)
    ids = [r.id for r in rows]
    assert (
        cv.extract_county_volume(db_session, doc, settings, known_counties=known)[
            "reason"
        ]
        == "already_extracted"
    )
    assert [r.id for r in db_session.query(Extraction).all()] == ids


@pytest.fixture
def historical_world(db_session, seed_country, monkeypatch, tmp_path):
    """Faithful retained extraction fixtures, not a claim of production ingestion."""
    from datetime import datetime, timezone
    from models import SourceDocument, DocumentStatus

    fx = json.loads(FX_PATH.read_text())
    doc = __import__("models").SourceDocument(
        country_id=seed_country.id,
        publisher="Office of the Auditor-General",
        title="County Assemblies 2023/2024",
        url=fx["source_url"],
        md5=fx["md5"],
        status=DocumentStatus.AVAILABLE,
        doc_type=DocumentType.AUDIT,
        fetch_date=datetime.now(timezone.utc),
        content_type="application/pdf",
        http_status=200,
        meta={"later": {"keep": True}},
    )
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nyamira County",
        slug="nyamira-county",
        meta={},
    )
    db_session.add_all([doc, county])
    db_session.flush()
    artifact = dict(
        schema_version=1,
        sha256=fx["sha256"],
        md5=fx["md5"],
        size_bytes=fx["size_bytes"],
        source_document_id=doc.id,
        source_url=doc.url,
        report_title=doc.title,
        publisher=doc.publisher,
        validation="pdf_magic_and_final_eof",
        verification_time=None,
        verification_time_reason="download_time_not_available",
    )
    doc.meta = dict(doc.meta, pdf_artifact_v1=artifact)
    for payload in fx["payloads"]:
        payload = copy.deepcopy(payload)
        payload["pdf_artifact_binding_v1"] = dict(
            schema_version=1,
            artifact=artifact,
            extractor=cv.EXTRACTOR_ID,
            text_visibility="visible_only",
            pdf_pages=fx["pages"],
        )
        db_session.add(
            Extraction(
                source_document_id=doc.id,
                page_number=payload["pdf_page"],
                extracted_json=payload,
                extractor=cv.EXTRACTOR_ID,
                confidence=0.9,
            )
        )
    db_session.flush()
    stats = load_blue_book_extractions(db_session, doc, SeedingSettings(), CTX)
    assert stats.created == 2 and not stats.errors
    from test_project_narratives import blocks

    county.meta = {"stalled_projects": blocks(monkeypatch, tmp_path)["Nyamira"]}
    db_session.commit()
    return db_session, doc, county


def test_actual_comprehensive_read_projects_qualified_historical_candidate(
    historical_world, client
):
    session, doc, county = historical_world
    response = client.get(f"/api/v1/counties/{county.id}/comprehensive")
    assert response.status_code == 200
    block = response.json()["stalled_projects"]
    n = block["narratives"]
    assert (
        len(n["historical_identity_candidates"]) == 1
    ), "ingested exact evidence must reach the real read path"
    assert (
        n["historical_identity_candidates"][0]["decision"]
        == "candidate_only_no_automatic_join"
    )
    historical = n["historical_observations"][0]
    assert historical["scalar_measures"]["paid"] == 24158208
    assert historical["scalar_measures"]["payable"] == 2457540
    assert historical["status"]["as_of"]["precision"] == "month"
    assert (
        historical["measures"]["payable"]["statements"][0]["as_of"]["precision"]
        == "unknown"
    )
    assert n["observations"][0]["scalar_measures"]["paid"] is None
    assert block["count"] is block["total_amount_paid"] is None
    assert doc.file_path is None
    audit = session.query(Audit).filter(Audit.page_ref == "p.207").one()
    assert audit.source_hash == source_hash_of(
        session.get(Extraction, audit.extraction_id).extracted_json
    )
    assert audit.source_hash != doc.meta["pdf_artifact_v1"]["sha256"]


@pytest.mark.parametrize(
    "damage",
    [
        "binding_absent",
        "binding_null",
        "binding_list",
        "version_bool",
        "invisible",
        "sha",
        "md5",
        "size_bool",
        "document_meta_absent",
        "document_meta_malformed",
        "doc_reissued",
        "doc_url",
        "doc_title",
        "doc_publisher",
        "doc_failed",
        "source_id",
        "extraction_source",
        "extractor",
        "county",
        "institution",
        "auditee",
        "period",
        "audit_year",
        "paragraph",
        "page_bool",
        "printed_page",
        "text",
        "title",
        "chapter",
        "chapter_heading",
        "json_hash",
        "audit_text",
        "audit_page",
        "provenance",
        "prov_binding",
        "prov_md5",
        "prov_page",
        "pages",
    ],
)
def test_missing_or_changed_historical_evidence_refuses_candidate_only(
    historical_world, client, damage
):
    session, doc, county = historical_world
    a = session.query(Audit).filter_by(page_ref="p.207").one()
    ext = session.get(Extraction, a.extraction_id)
    p = copy.deepcopy(ext.extracted_json)
    binding = p["pdf_artifact_binding_v1"]
    meta = copy.deepcopy(doc.meta)
    if damage == "binding_absent":
        p.pop("pdf_artifact_binding_v1")
    elif damage == "binding_null":
        p["pdf_artifact_binding_v1"] = None
    elif damage == "binding_list":
        p["pdf_artifact_binding_v1"] = []
    elif damage == "version_bool":
        binding["schema_version"] = True
    elif damage == "invisible":
        binding["text_visibility"] = "all_text"
    elif damage == "sha":
        binding["artifact"]["sha256"] = "0" * 64
    elif damage == "md5":
        binding["artifact"]["md5"] = "0" * 32
    elif damage == "size_bool":
        binding["artifact"]["size_bytes"] = True
    elif damage == "document_meta_absent":
        meta.pop("pdf_artifact_v1")
    elif damage == "document_meta_malformed":
        meta["pdf_artifact_v1"] = []
    elif damage == "doc_reissued":
        doc.md5 = "0" * 32
        meta["pdf_artifact_v1"]["md5"] = doc.md5
    elif damage == "doc_url":
        doc.url = "https://www.oagkenya.go.ke/another.pdf"
    elif damage == "doc_title":
        doc.title = "another edition"
    elif damage == "doc_publisher":
        doc.publisher = "Controller of Budget"
    elif damage == "doc_failed":
        doc.status = __import__("models").DocumentStatus.FAILED
    elif damage in ("source_id", "extraction_source"):
        from models import SourceDocument

        other = SourceDocument(
            country_id=doc.country_id,
            publisher=doc.publisher,
            title="Other",
            url="https://www.oagkenya.go.ke/other.pdf",
            fetch_date=doc.fetch_date,
            doc_type=doc.doc_type,
        )
        session.add(other)
        session.flush()
        if damage == "source_id":
            a.source_document_id = other.id
        else:
            ext.source_document_id = other.id
    elif damage == "extractor":
        ext.extractor = "oag_blue_book"
    elif damage == "county":
        p["county_name"] = "Siaya"
    elif damage == "institution":
        p["volume_kind"] = "executives"
        p["entity_name"] = "County Executive of Nyamira"
    elif damage == "auditee":
        p["auditee"] = "County Executive of Nyamira"
    elif damage == "period":
        p["fiscal_year"] = "2024/2025"
    elif damage == "audit_year":
        a.audit_year = 2025
    elif damage == "paragraph":
        p["paragraph_no"] = []
    elif damage == "page_bool":
        p["pdf_page"] = True
    elif damage == "printed_page":
        p["printed_page"] = 194
    elif damage == "text":
        p["finding_text"] = p["finding_text"].replace("24,158,208", "26,650,000")
        a.finding_text = p["finding_text"]
    elif damage == "title":
        p["title"] = "Delayed Construction of County Assembly Offices"
    elif damage == "chapter":
        p["chapter_no"] = 45
    elif damage == "chapter_heading":
        p["chapter_heading"] = "COUNTY EXECUTIVE OF NYAMIRA – NO.46"
    elif damage == "json_hash":
        a.source_hash = "a" * 64
    elif damage == "audit_text":
        a.finding_text = "changed public text"
    elif damage == "audit_page":
        a.page_ref = "p.208"
    elif damage == "provenance":
        a.provenance = {}
    elif damage.startswith("prov_"):
        prov = copy.deepcopy(a.provenance)
        if damage == "prov_binding":
            prov[0]["pdf_artifact_binding_v1"] = None
        if damage == "prov_md5":
            prov[0]["source_md5"] = "b" * 32
        if damage == "prov_page":
            prov[0]["pdf_page"] = True
        a.provenance = prov
    elif damage == "pages":
        binding["pdf_pages"] = True
    ext.extracted_json = p
    doc.meta = meta
    # Recompute the JSON digest except its direct hostile control: internal
    # self-consistency alone still cannot authorize a changed passage/context.
    if damage != "json_hash":
        a.source_hash = source_hash_of(p)
    session.commit()
    response = client.get(f"/api/v1/counties/{county.id}/comprehensive")
    assert response.status_code == 200
    n = response.json()["stalled_projects"]["narratives"]
    assert (
        n["status"] == "accepted"
        and n["observations"][0]["scalar_measures"]["paid"] is None
    )
    assert n["historical_identity_candidates"] == []
    assert n["historical_candidate_reason"]
    assert n["historical_observations"] == []


def test_absent_payable_is_not_zero_or_merged_and_duplicate_primary_is_ambiguous(
    historical_world,
):
    from services.oag_project_evidence import historical_projection

    session, doc, county = historical_world
    audits = session.query(Audit).all()
    rows = {r.id: r for r in session.query(Extraction).all()}
    primary = [a for a in audits if a.page_ref == "p.207"]
    out = historical_projection(primary, rows, {doc.id: doc}, county.canonical_name)
    assert out["status"] == "accepted"
    assert out["observations"][0]["scalar_measures"]["payable"] is None
    assert out["observations"][0]["measures"]["payable"]["state"] == "absent"
    assert (
        historical_projection(primary * 2, rows, {doc.id: doc}, county.canonical_name)[
            "observations"
        ]
        == []
    )
    assert (
        historical_projection(audits, rows, {doc.id: doc}, "Siaya County")[
            "observations"
        ]
        == []
    )


def test_old_extraction_remains_old_after_reissue_and_loader_replay(
    historical_world, client
):
    session, doc, county = historical_world
    a = session.query(Audit).filter_by(page_ref="p.207").one()
    old_md5 = a.provenance[0]["source_md5"]
    meta = copy.deepcopy(doc.meta)
    doc.md5 = "d" * 32
    meta["pdf_artifact_v1"]["md5"] = doc.md5
    meta["pdf_artifact_v1"]["sha256"] = "d" * 64
    doc.meta = meta
    stats = load_blue_book_extractions(session, doc, SeedingSettings(), CTX)
    assert not stats.errors and stats.created == 0
    assert a.provenance[0]["source_md5"] == old_md5
    session.commit()
    out = client.get(f"/api/v1/counties/{county.id}/comprehensive").json()[
        "stalled_projects"
    ]["narratives"]
    assert out["historical_identity_candidates"] == []
    assert out["historical_refusals"][0]["reason"] == "document_artifact_mismatch"


def test_same_byte_redownload_keeps_binding_identity_with_real_download_time(
    db_session, seed_country, tmp_path, monkeypatch
):
    import time
    from seeding.pdf_download import _cache_paths
    from test_oag_county_volume import _hand_made_pdf

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    fx = json.loads(FX_PATH.read_text())
    cache = settings.cache_path / "pdfs"
    cache.mkdir(parents=True)
    _, sidecar = _cache_paths(cache, fx["source_url"])
    original = time.time() - 7200
    sidecar.write_text(
        json.dumps(
            {
                "created_at": original,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )
    doc = fetch(db_session, seed_country, settings, path, monkeypatch)
    identity = copy.deepcopy(doc.meta["pdf_artifact_v1"])
    assert (
        identity["verification_time"] and identity["verification_time_reason"] is None
    )
    sidecar.write_text(
        json.dumps({"created_at": time.time() - 10, "sha256": identity["sha256"]})
    )
    doc = fetch(db_session, seed_country, settings, path, monkeypatch)
    assert doc.meta["pdf_artifact_v1"] == identity
    assert not doc.meta.get("previous_pdf_artifacts_v1")
    assert doc.last_verified_at.timestamp() > original


def test_unchecked_sidecar_digest_cannot_be_artifact_or_verification_context(
    db_session, seed_country, tmp_path, monkeypatch
):
    import time
    from seeding.pdf_download import _cache_paths
    from test_oag_county_volume import _hand_made_pdf

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    cache = settings.cache_path / "pdfs"
    cache.mkdir(parents=True)
    _, sidecar = _cache_paths(cache, json.loads(FX_PATH.read_text())["source_url"])
    sidecar.write_text(json.dumps({"created_at": time.time() - 10, "sha256": "a" * 64}))
    doc = fetch(db_session, seed_country, settings, path, monkeypatch)
    assert (
        doc.meta["pdf_artifact_v1"]["sha256"]
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert doc.meta["pdf_artifact_v1"]["verification_time"] is None


def test_changed_bytes_during_read_refuse_before_any_replacement(
    db_session, seed_country, tmp_path, monkeypatch
):
    from test_oag_county_volume import TestExtractionRows, _hand_made_pdf
    from seeding.extractors.reconciliation import IncompleteExtraction

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    doc = fetch(db_session, seed_country, settings, path, monkeypatch)

    def changed(*a, **kw):
        path.write_bytes(
            path.read_bytes().replace(b"VISIBLE PAGE TEXT", b"REISSUED CONTENT")
        )
        return TestExtractionRows.PAGES

    monkeypatch.setattr(cv, "read_pages", changed)
    with pytest.raises(IncompleteExtraction, match="bytes changed"):
        cv.extract_county_volume(
            db_session, doc, settings, known_counties=TestExtractionRows.KNOWN
        )
    assert db_session.query(Extraction).count() == 0


def test_hash_only_reextraction_keeps_ids_and_rollback_keeps_prior_bindings(
    db_session, seed_country, tmp_path, monkeypatch
):
    from test_oag_county_volume import TestExtractionRows, _hand_made_pdf, _FILLER
    from seeding.extractors.reconciliation import extract_and_load, IncompleteExtraction

    path = tmp_path / "actual.pdf"
    _hand_made_pdf(path)
    settings = SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )
    doc = fetch(
        db_session,
        seed_country,
        settings,
        path,
        monkeypatch,
        url="https://www.oagkenya.go.ke/COUNTY-EXECUTIVES-2024-2025.pdf",
    )
    known = {
        cv._letters(n): n for n in ["Mombasa", "Taita Taveta", "Atlantis", *_FILLER]
    }
    for name in known.values():
        db_session.add(
            Entity(
                country_id=seed_country.id,
                type=EntityType.COUNTY,
                canonical_name=name + " County",
                slug=__import__(
                    "seeding.utils", fromlist=["slugify_entity"]
                ).slugify_entity(name),
            )
        )
    db_session.flush()
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: TestExtractionRows.PAGES)

    def parser(s, d, settings):
        return cv.extract_county_volume(s, d, settings, known_counties=known)

    extract_and_load(db_session, doc, settings, CTX, parser, load_blue_book_extractions)
    db_session.commit()
    before = {
        r.id: copy.deepcopy(r.extracted_json)
        for r in db_session.query(Extraction).all()
    }
    audit_refs = {a.id: a.extraction_id for a in db_session.query(Audit).all()}
    # A legacy row can gain binding only from a real normal extraction, not a
    # loader replay. Remove fixture bindings, retaining canonical audit hashes.
    for r in db_session.query(Extraction).all():
        p = copy.deepcopy(r.extracted_json)
        p.pop("pdf_artifact_binding_v1")
        r.extracted_json = p
    db_session.commit()
    extract_and_load(db_session, doc, settings, CTX, parser, load_blue_book_extractions)
    assert {
        r.id: r.extracted_json for r in db_session.query(Extraction).all()
    } == before
    assert {a.id: a.extraction_id for a in db_session.query(Audit).all()} == audit_refs
    db_session.commit()
    # Actual reissued bytes with unchanged meanings needs no content review,
    # but a loader failure must roll back the replacement and completion stamp.
    path.write_bytes(
        path.read_bytes().replace(b"VISIBLE PAGE TEXT", b"REISSUED CONTENT")
    )
    fetch(
        db_session,
        seed_country,
        settings,
        path,
        monkeypatch,
        url="https://www.oagkenya.go.ke/COUNTY-EXECUTIVES-2024-2025.pdf",
    )
    db_session.commit()
    new_artifact = copy.deepcopy(doc.meta["pdf_artifact_v1"])

    def failed_loader(*a, **kw):
        return __import__("types").SimpleNamespace(errors=["forced loader failure"])

    with pytest.raises(IncompleteExtraction, match="forced loader failure"):
        extract_and_load(db_session, doc, settings, CTX, parser, failed_loader)
    db_session.expire_all()
    assert {
        r.id: r.extracted_json for r in db_session.query(Extraction).all()
    } == before
    assert doc.meta["pdf_artifact_v1"] == new_artifact
    assert doc.meta["extracted_md5"] != doc.md5
    # Partial replacement cannot rebind old findings to the new artifact.
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: TestExtractionRows.PAGES[:-1])
    with pytest.raises(IncompleteExtraction, match="incomplete county volume"):
        extract_and_load(
            db_session, doc, settings, CTX, parser, load_blue_book_extractions
        )
    assert {
        r.id: r.extracted_json for r in db_session.query(Extraction).all()
    } == before
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: TestExtractionRows.PAGES)
    extract_and_load(db_session, doc, settings, CTX, parser, load_blue_book_extractions)
    assert {a.id: a.extraction_id for a in db_session.query(Audit).all()} == audit_refs
    assert all(
        r.extracted_json["pdf_artifact_binding_v1"]["artifact"] == new_artifact
        for r in db_session.query(Extraction).all()
    )


def test_historical_candidate_keeps_populated_table_and_unsupported_county_separate(
    historical_world, client, monkeypatch, tmp_path
):
    from test_project_narratives import blocks, FX

    session, doc, county = historical_world
    stored = copy.deepcopy(county.meta["stalled_projects"])
    stored["rows"] = [
        dict(
            project_name="Unrelated table control",
            source_url=FX["source"]["url"],
            source_page=686,
            as_of="2026-06-30",
            reported_by="Nyamira County Treasury",
            estimated_value_kes=0,
            amount_paid_kes=7,
        )
    ]
    county.meta = {"stalled_projects": stored}
    session.commit()
    block = client.get(f"/api/v1/counties/{county.id}/comprehensive").json()[
        "stalled_projects"
    ]
    assert (
        block["count"] == 1
        and block["total_contracted_value"] == 0
        and block["total_amount_paid"] == 7
    )
    assert len(block["narratives"]["historical_identity_candidates"]) == 1
    # Coherent Siaya current observation remains institution-unknown even when
    # an actual different county's historical records are in the same database.
    siaya = Entity(
        country_id=doc.country_id,
        type=EntityType.COUNTY,
        canonical_name="Siaya County",
        slug="siaya-county",
        meta={"stalled_projects": blocks(monkeypatch, tmp_path)["Siaya"]},
    )
    session.add(siaya)
    session.commit()
    block = client.get(f"/api/v1/counties/{siaya.id}/comprehensive").json()[
        "stalled_projects"
    ]
    n = block["narratives"]
    assert (
        n["historical_identity_candidates"] == [] and n["historical_observations"] == []
    )
    assert n["observations"][0]["implementing_institution"]["state"] == "unknown"
    assert n["observations"][0]["scalar_measures"]["paid"] == 3720000
    assert n["observations"][0]["scalar_measures"]["estimated_value"] == 1880000


def test_no_annual_observation_does_not_make_historical_candidate_complete(
    historical_world,
):
    from services.stalled_projects import build_stalled_projects_block

    session, doc, county = historical_world
    out = build_stalled_projects_block(
        {"schema": 2, "rows": []},
        county_name=county.canonical_name,
        historical_audits=session.query(Audit).all(),
        historical_extractions={e.id: e for e in session.query(Extraction).all()},
        historical_documents={doc.id: doc},
    )
    assert out["narratives"]["status"] == "absent"
    assert out["narratives"]["historical_evidence_status"] == "accepted"
    assert out["narratives"]["historical_identity_candidates"] == []
    assert (
        out["narratives"]["historical_candidate_reason"]
        == "annual_narrative_unavailable"
    )


@pytest.mark.parametrize("title", [True, [], {}, 1, ["hostile"], {"hostile": True}])
def test_malformed_oag_heading_does_not_suppress_valid_current_narrative(
    historical_world, client, title
):
    session, doc, county = historical_world
    a = session.query(Audit).filter_by(page_ref="p.207").one()
    ext = session.get(Extraction, a.extraction_id)
    p = copy.deepcopy(ext.extracted_json)
    p["title"] = title
    ext.extracted_json = p
    a.source_hash = source_hash_of(p)
    session.commit()
    response = client.get(f"/api/v1/counties/{county.id}/comprehensive")
    assert response.status_code == 200
    n = response.json()["stalled_projects"]["narratives"]
    assert (
        n["status"] == "accepted"
        and n["observations"][0]["scalar_measures"]["paid"] is None
    )
    assert n["historical_identity_candidates"] == []

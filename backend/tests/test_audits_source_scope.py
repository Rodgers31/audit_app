"""Execution scope controls; PDF parsing has independent retained-byte coverage."""
import json
from pathlib import Path

import pytest

from seeding.domains import audits
from seeding import oag_discovery as od
from seeding.types import DomainRunContext
from seeding.config import SeedingSettings
from test_audits_domain_county_ingest import harness, NATIONAL

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/operations/2026-10-01-round11-oag-catchup/manifest.json"
)
RAW = MANIFEST.read_bytes()
SOURCES = json.loads(RAW)["deferred_sources"]
URLS = [r["source_url"] for r in SOURCES]


def context(raw=RAW, **kwargs):
    ctx = DomainRunContext(since=None, dry_run=False, **kwargs)
    # Deliberate dynamic assignment also executes on the original baseline:
    # it must fail because the handler ignores this restriction, not an import.
    ctx.audits_source_manifest = raw
    return ctx


def broad_discovery():
    data = json.loads(
        (
            MANIFEST.parents[2]
            / "verification/2026-09-27-oag-coverage/accepted-source-manifest.json"
        ).read_text()
    )
    return od.CountyAuditDiscovery(
        documents=[
            od.OagDocument(
                url=r["url"],
                fiscal_year=r["fiscal_year"],
                kind=r["institution"],
                found_on="year_page",
                listed_at=f"https://www.oagkenya.go.ke/{r['fiscal_year'].replace('/', '-')}-county-government-audit-reports/",
            )
            for r in data
        ]
    )


def allow_controlled_bytes(monkeypatch, harness):
    """The existing parser/IO harness is synthetic; identity is a named seam."""
    import seeding.pdf_artifact as artifact

    hashes = {r["source_url"]: r for r in SOURCES}
    real_fetch = __import__(
        "seeding.fetch_documents", fromlist=["fetch_document"]
    ).fetch_document

    def fetch(session, client, settings, *, url, **kwargs):
        doc = real_fetch(session, client, settings, url=url, **kwargs)
        if url in hashes:
            doc.md5 = hashes[url]["md5"]
        return doc

    monkeypatch.setattr("seeding.fetch_documents.fetch_document", fetch)

    def identity(path):
        entry = hashes[harness["fetched"][-1]]
        return {"sha256": entry["sha256"], "md5": entry["md5"], "size_bytes": 1}

    monkeypatch.setattr(artifact, "file_identity", identity)
    real_parser = __import__("seeding.extractors", fromlist=["get_parser"]).get_parser(
        "oag_county_audit"
    )

    def parser(session, doc, settings):
        stats = real_parser(session, doc, settings)
        from models import Extraction

        if doc.url in hashes:
            for row in session.query(Extraction).filter_by(source_document_id=doc.id):
                row.extracted_json = {
                    "schema": "oag_county_volume/v1",
                    "fiscal_year": hashes[doc.url]["fiscal_year"],
                    "volume_kind": hashes[doc.url]["institution"],
                }
            session.flush()
        return stats

    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: parser if pid == "oag_county_audit" else None,
    )


def test_manifest_restricts_real_handler_not_only_cli(harness, monkeypatch):
    from models import SourceDocument

    monkeypatch.setattr(
        od, "discover_county_audit_documents", lambda c: broad_discovery()
    )
    monkeypatch.setattr(
        audits.fetcher, "_discover_audit_pdfs_via_wp_api", lambda c, **kw: [NATIONAL]
    )
    allow_controlled_bytes(monkeypatch, harness)
    result = audits.run(
        harness["session"],
        SeedingSettings(audits_county_start_budget_seconds=1000),
        context(),
    )
    assert harness["fetched"] == URLS
    assert set(u for (u,) in harness["session"].query(SourceDocument.url)) - {
        __import__("test_audits_domain_county_ingest").STALE_SINGLE
    } == set(URLS)
    assert not result.errors


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"{broken",
        b'{"schema":true}',
        False,
        0,
        [],
        {},
        "bad",
        b"x" * 131073,
    ],
)
def test_bad_scope_refuses_direct_handler_before_any_db_or_io(raw):
    from seeding.domains.audits.scope import AuditSourceScopeError

    with pytest.raises(AuditSourceScopeError):
        audits.run(None, SeedingSettings(), context(raw))


@pytest.mark.parametrize(
    "mutation", ["empty", "duplicate", "unapproved", "edition", "hash", "schema"]
)
def test_modified_packet_is_not_reviewed(mutation):
    from seeding.domains.audits.scope import parse_manifest, AuditSourceScopeError

    packet = json.loads(RAW)
    if mutation == "empty":
        packet["deferred_sources"] = []
    elif mutation == "duplicate":
        packet["deferred_sources"][1] = packet["deferred_sources"][0]
    elif mutation == "unapproved":
        packet["deferred_sources"][0]["source_url"] = NATIONAL
    elif mutation == "edition":
        packet["deferred_sources"][0]["fiscal_year"] = "2024/2025"
    elif mutation == "hash":
        packet["deferred_sources"][0]["sha256"] = "0" * 64
    else:
        packet["schema"] = "unknown/v2"
    with pytest.raises(AuditSourceScopeError):
        parse_manifest(json.dumps(packet).encode())


def test_scoped_consumer_refuses_broader_registration(harness):
    from models import SourceDocument
    from seeding.source_registry import SOURCE_REGISTRY
    from seeding.domains.audits.scope import AuditSourceScopeError

    session = harness["session"]
    before = session.query(SourceDocument).count()
    with pytest.raises(AuditSourceScopeError, match="unlisted"):
        audits.register_discovered_documents(
            session,
            country_id=session.query(SourceDocument).first().country_id,
            dataset=SOURCE_REGISTRY["oag_county_audits"],
            discovery=broad_discovery(),
            source_manifest=RAW,
        )
    assert session.query(SourceDocument).count() == before
    assert not harness["fetched"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("publisher", "Other"),
        ("md5", "0" * 32),
        ("meta", []),
        (
            "meta",
            {
                "oag_discovery": {
                    "fiscal_year": "2024/2025",
                    "kind": "assemblies",
                    "listed_at": SOURCES[0]["listed_at"],
                }
            },
        ),
    ],
)
def test_registered_scope_drift_stops_before_registration_or_fetch(
    harness, field, value
):
    from models import SourceDocument, DocumentStatus, DocumentType
    from datetime import datetime
    from seeding.domains.audits.scope import AuditSourceScopeError

    session = harness["session"]
    doc = SourceDocument(
        country_id=session.query(SourceDocument).first().country_id,
        publisher="Office of the Auditor-General",
        title="original",
        url=URLS[0],
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.FAILED,
        fetch_date=datetime(2026, 1, 1),
    )
    setattr(doc, field, value)
    session.add(doc)
    session.commit()
    before = session.query(SourceDocument).count()
    with pytest.raises(AuditSourceScopeError, match="changed"):
        audits.run(session, SeedingSettings(), context())
    assert not harness["fetched"]
    assert session.query(SourceDocument).count() == before
    assert doc.title == "original"


def test_zero_budget_and_two_turn_resume_account_only_for_five(harness, monkeypatch):
    allow_controlled_bytes(monkeypatch, harness)
    session = harness["session"]
    zero = audits.run(
        session, SeedingSettings(audits_county_start_budget_seconds=0), context()
    )
    assert zero.metadata["audit_source_scope"]["deferred"] == URLS
    assert not harness["fetched"]
    first = audits.run(
        session, SeedingSettings(audits_county_start_budget_seconds=240), context()
    )
    assert first.metadata["audit_source_scope"]["processed"] == URLS[:3]
    assert first.metadata["audit_source_scope"]["deferred"] == URLS[3:]
    second = audits.run(
        session, SeedingSettings(audits_county_start_budget_seconds=240), context()
    )
    assert second.metadata["audit_source_scope"]["processed"] == URLS[3:]
    assert second.metadata["audit_source_scope"]["already_current"] == URLS[:3]
    assert second.metadata["audit_source_scope"]["deferred"] == []
    assert NATIONAL not in harness["fetched"]


@pytest.fixture()
def cli_harness(harness, monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base, Country
    import seeding.cli as cli

    engine = create_engine(f"sqlite:///{tmp_path}/committed.sqlite")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        Country(
            name="Kenya",
            iso_code="KEN",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en-KE",
        )
    )
    session.commit()
    harness["session"] = session
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    settings = SeedingSettings(
        audits_county_start_budget_seconds=1000, total_timeout_seconds=0
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    allow_controlled_bytes(monkeypatch, harness)
    yield harness, factory, settings
    session.close()
    engine.dispose()


def cli_args(path=MANIFEST):
    return ["seed", "--domain", "audits", "--audits-source-manifest", str(path)]


@pytest.mark.parametrize(
    "case", ["missing", "empty", "duplicate", "all", "wrong_domain", "no_domain"]
)
def test_cli_invalid_scope_has_no_job_source_or_fetch(cli_harness, tmp_path, case):
    from models import IngestionJob, SourceDocument
    import seeding.cli as cli

    harness, factory, settings = cli_harness
    path = tmp_path / "bad.json"
    args = cli_args(path)
    if case == "empty":
        path.write_text("{}")
    elif case == "duplicate":
        packet = json.loads(RAW)
        packet["deferred_sources"][1] = packet["deferred_sources"][0]
        path.write_text(json.dumps(packet))
    elif case in ("all", "wrong_domain", "no_domain"):
        args = cli_args()
        if case == "all":
            args.append("--all")
        elif case == "wrong_domain":
            args.extend(["--domain", "population"])
        else:
            args = ["seed", "--audits-source-manifest", str(MANIFEST)]
    assert cli.main(args) == 1
    with factory() as read:
        assert (
            read.query(IngestionJob).count() == read.query(SourceDocument).count() == 0
        )
    assert not harness["fetched"]


def test_cli_timeout_banks_first_volume_and_resumes_across_sessions(
    cli_harness, monkeypatch
):
    from models import Extraction, IngestionJob, IngestionStatus
    import seeding.cli as cli

    harness, factory, settings = cli_harness
    fetch = __import__(
        "seeding.fetch_documents", fromlist=["fetch_document"]
    ).fetch_document

    def interrupted(session, client, settings, *, url, **kwargs):
        if url == URLS[1]:
            raise cli.DomainTimeoutError("controlled interruption on second source")
        return fetch(session, client, settings, url=url, **kwargs)

    monkeypatch.setattr("seeding.fetch_documents.fetch_document", interrupted)
    assert cli.main(cli_args()) == 1
    with factory() as read:
        assert read.query(Extraction).count() == 1
        job = read.query(IngestionJob).one()
        assert job.status == IngestionStatus.FAILED
        assert job.meta["audit_source_scope"]["processed"] == URLS[:1]
        assert job.meta["audit_source_scope"]["attempted"] == URLS[:2]
    monkeypatch.setattr("seeding.fetch_documents.fetch_document", fetch)
    harness["fetched"].clear()
    assert cli.main(cli_args()) == 0
    with factory() as read:
        assert read.query(Extraction).count() == 5
        job = read.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        assert job.status == IngestionStatus.COMPLETED
        assert job.meta["audit_source_scope"]["processed"] == URLS[1:]
        assert job.meta["audit_source_scope"]["already_current"] == URLS[:1]
    assert harness["fetched"] == URLS


@pytest.mark.parametrize(
    "attack",
    ["bytes", "empty", "schema", "edition", "partial", "bool_count", "loader_skip"],
)
def test_scope_refusal_rolls_back_candidate_and_stops_next_fetch(
    cli_harness, monkeypatch, attack
):
    from models import Extraction, IngestionJob, SourceDocument
    import seeding.cli as cli

    harness, factory, settings = cli_harness
    import seeding.extractors as extractors

    parser = extractors.get_parser("oag_county_audit")

    def attacked(session, doc, settings):
        stats = parser(session, doc, settings)
        if attack == "empty":
            session.query(Extraction).filter_by(source_document_id=doc.id).delete()
        if attack in ("schema", "edition"):
            row = session.query(Extraction).filter_by(source_document_id=doc.id).one()
            payload = dict(row.extracted_json)
            payload["schema" if attack == "schema" else "fiscal_year"] = "changed"
            row.extracted_json = payload
        if attack == "partial":
            stats["partial"] = True
        if attack == "bool_count":
            stats["created"] = True
        return stats

    if attack == "bytes":
        monkeypatch.setattr(
            "seeding.pdf_artifact.file_identity",
            lambda p: {"sha256": "0" * 64, "md5": SOURCES[0]["md5"]},
        )
    else:
        monkeypatch.setattr(extractors, "get_parser", lambda pid: attacked)
    if attack == "loader_skip":
        from seeding.domains.audits.writer import PersistenceStats

        monkeypatch.setattr(
            "seeding.domains.audits.loader.load_blue_book_extractions",
            lambda *a, **kw: PersistenceStats(skipped=1),
        )
    assert cli.main(cli_args()) == 1
    with factory() as read:
        assert read.query(Extraction).count() == 0
        job = read.query(IngestionJob).one()
        assert job.meta["audit_source_scope"]["attempted"] == URLS[:1]
        assert len(job.meta["audit_source_scope"]["refused"]) == 1
        assert job.meta["audit_source_scope"]["processed"] == []
        if attack == "bytes":
            doc = read.query(SourceDocument).filter_by(url=URLS[0]).one()
            assert doc.md5 is None and doc.file_path is None
    assert harness["fetched"] == URLS[:1]


def test_scoped_success_does_not_certify_whole_listing(cli_harness):
    from models import IngestionJob
    from seeding.county_audit_coverage import _run_gaps
    import seeding.cli as cli

    harness, factory, settings = cli_harness
    assert cli.main(cli_args()) == 0
    with factory() as read:
        job = read.query(IngestionJob).one()
        assert "newest audits run has no valid county listing" in _run_gaps(job)
        assert job.meta["audit_source_scope"]["whole_world_coverage"] is False


from test_county_volume_loading import world


def test_scoped_loader_preserves_unlisted_publication_fields(
    world, monkeypatch, tmp_path
):
    from models import Audit, Extraction
    from test_county_volume_loading import _add
    from seeding.domains.audits.loader import load_blue_book_extractions

    session, docs = world
    _add(session, docs["executives"], "executives")
    load_blue_book_extractions(
        session,
        docs["executives"],
        SeedingSettings(),
        DomainRunContext(since=None, dry_run=False),
    )
    unlisted = session.query(Audit).one()
    unlisted.publishable = False
    unlisted.quarantine_reason = "synthetic_preservation_sentinel"
    session.flush()
    selected = docs["assemblies"]
    selected.url = URLS[0]
    selected.md5 = SOURCES[0]["md5"]
    selected.file_path = str(tmp_path / "controlled.pdf")
    selected.meta = {
        "oag_discovery": __import__(
            "seeding.domains.audits.scope", fromlist=["discovery_for"]
        )
        .discovery_for(SOURCES)
        .documents[0]
        .as_meta()
    }
    rows = _add(session, selected, "assemblies")
    for row in rows:
        payload = dict(row.extracted_json)
        payload["fiscal_year"] = SOURCES[0]["fiscal_year"]
        row.extracted_json = payload
    session.flush()
    monkeypatch.setattr(
        "seeding.pdf_artifact.file_identity",
        lambda p: {"sha256": SOURCES[0]["sha256"], "md5": SOURCES[0]["md5"]},
    )
    loaded = load_blue_book_extractions(session, selected, SeedingSettings(), context())
    assert loaded.created == 1 and not loaded.errors
    session.expire_all()
    assert unlisted.publishable is False
    assert unlisted.quarantine_reason == "synthetic_preservation_sentinel"
    scoped = session.query(Audit).filter_by(source_document_id=selected.id).one()
    assert scoped.publishable is True and scoped.quarantine_reason is None


def test_scoped_registration_refuses_wrong_dataset_owner(harness):
    from models import SourceDocument
    from seeding.domains.audits.scope import discovery_for, AuditSourceScopeError
    from seeding.source_registry import SOURCE_REGISTRY

    session = harness["session"]
    before = session.query(SourceDocument).count()
    with pytest.raises(AuditSourceScopeError):
        audits.register_discovered_documents(
            session,
            country_id=session.query(SourceDocument).first().country_id,
            dataset=SOURCE_REGISTRY["oag_national_audits"],
            discovery=discovery_for(SOURCES),
            source_manifest=RAW,
        )
    assert session.query(SourceDocument).count() == before


def test_scoped_loader_refuses_unlisted_direct_call(world):
    from seeding.domains.audits.scope import AuditSourceScopeError
    from seeding.domains.audits.loader import load_blue_book_extractions

    session, docs = world
    with pytest.raises(AuditSourceScopeError, match="unlisted"):
        load_blue_book_extractions(
            session, docs["executives"], SeedingSettings(), context()
        )


@pytest.mark.parametrize(
    "ids", [[], {}, "1", [True], [0], [-1], [1, 1], [None], [float("nan")]]
)
def test_publication_scope_requires_nonempty_positive_distinct_ids(ids):
    from services.publication_gate import backfill_publishable_audits

    with pytest.raises(ValueError):
        backfill_publishable_audits(None, source_document_ids=ids)


def test_corrupted_binding_cannot_reach_scoped_loader(cli_harness, monkeypatch):
    from models import Extraction, IngestionJob
    from seeding.pdf_artifact import BINDING_KEY
    import seeding.extractors as extractors
    import seeding.cli as cli

    harness, factory, settings = cli_harness
    parser = extractors.get_parser("oag_county_audit")

    def corrupt(session, doc, settings):
        stats = parser(session, doc, settings)
        row = session.query(Extraction).filter_by(source_document_id=doc.id).one()
        row.extracted_json = {
            **row.extracted_json,
            BINDING_KEY: {"schema_version": 999, "artifact": {"sha256": "0" * 64}},
        }
        session.flush()
        return stats

    monkeypatch.setattr(extractors, "get_parser", lambda pid: corrupt)
    assert cli.main(cli_args()) == 1
    with factory() as read:
        assert read.query(Extraction).count() == 0
        job = read.query(IngestionJob).one()
        assert job.meta["audit_source_scope"]["attempted"] == URLS[:1]
        assert "artifact evidence changed" in job.errors[0]


@pytest.mark.parametrize(
    "binding", [None, {"schema_version": 999, "artifact": {"sha256": "0" * 64}}]
)
def test_present_invalid_binding_is_refused_while_absence_is_retained(
    harness, monkeypatch, binding
):
    from models import Extraction, SourceDocument
    from seeding.domains.audits.scope import verify_extractions, AuditSourceScopeError
    from seeding.pdf_artifact import BINDING_KEY

    allow_controlled_bytes(monkeypatch, harness)
    session = harness["session"]
    audits.run(
        session, SeedingSettings(audits_county_start_budget_seconds=1000), context()
    )
    doc = session.query(SourceDocument).filter_by(url=URLS[0]).one()
    row = session.query(Extraction).filter_by(source_document_id=doc.id).one()
    assert BINDING_KEY not in row.extracted_json
    verify_extractions(session, doc, SOURCES[0], {"created": 0, "skipped": 1})
    row.extracted_json = {**row.extracted_json, BINDING_KEY: binding}
    session.flush()
    with pytest.raises(AuditSourceScopeError, match="artifact evidence changed"):
        verify_extractions(session, doc, SOURCES[0], {"created": 0, "skipped": 1})


def test_direct_scoped_loader_refuses_non_kenya_source(world, monkeypatch, tmp_path):
    from models import Country
    from tests.test_county_volume_loading import _add
    from seeding.domains.audits.loader import load_blue_book_extractions
    from seeding.domains.audits.scope import AuditSourceScopeError

    session, docs = world
    other = Country(
        name="Synthetic other country",
        iso_code="XYZ",
        currency="KES",
        timezone="UTC",
        default_locale="en",
    )
    session.add(other)
    session.flush()
    doc = docs["assemblies"]
    doc.country_id = other.id
    doc.url = URLS[0]
    doc.md5 = SOURCES[0]["md5"]
    doc.file_path = str(tmp_path / "controlled.pdf")
    rows = _add(session, doc, "assemblies")
    rows[0].extracted_json = {
        **rows[0].extracted_json,
        "fiscal_year": SOURCES[0]["fiscal_year"],
    }
    session.flush()
    monkeypatch.setattr(
        "seeding.pdf_artifact.file_identity",
        lambda p: {"sha256": SOURCES[0]["sha256"], "md5": SOURCES[0]["md5"]},
    )
    with pytest.raises(AuditSourceScopeError, match="Kenya country identity"):
        load_blue_book_extractions(session, doc, SeedingSettings(), context())

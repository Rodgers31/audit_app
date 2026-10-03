"""Actual coverage consumers, with explicit synthetic HTML/PDF identity seams."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from seeding import oag_discovery as od
from seeding.domains.audits import observation as obs
from seeding.domains.audits.scope import (
    receipt_for,
    parse_manifest,
    discovery_for,
    AuditSourceScopeError,
)
from seeding.county_audit_coverage import (
    county_audit_coverage_receipt,
    coverage_verdict,
    _run_gaps,
)
from seeding.staleness import check_county_audit_coverage
from test_county_audit_coverage_gate import db, _counties

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/operations/2026-10-01-round11-oag-catchup/manifest.json"
)
ENTRIES = parse_manifest(MANIFEST.read_bytes())
SELECTED = {e["source_url"] for e in ENTRIES}


def html_client(editions=None, *, year_extra=None, change=None):
    editions = editions or obs.accepted_editions()
    years = sorted({e["fiscal_year"] for e in editions.values()})
    if year_extra:
        years.append(year_extra)
    bodies = {
        od.LISTING_URL: "".join(
            f'<a href="/{fy.replace("/", "-")}-county-government-audit-reports/">year</a>'
            for fy in years
        )
    }
    for fy in years:
        bodies[
            f'{od.OAG_ORIGIN}/{fy.replace("/", "-")}-county-government-audit-reports/'
        ] = "".join(
            f'<a href="{e["url"]}">PDF</a>'
            for e in editions.values()
            if e["fiscal_year"] == fy
        )
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        result = httpx.Response(
            200,
            content=bodies[url].encode(),
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", url),
        )
        return change(result) if change else result

    return SimpleNamespace(get=get, calls=calls)


@pytest.fixture()
def adopted(db, monkeypatch, tmp_path):
    from models import (
        SourceDocument,
        DocumentType,
        DocumentStatus,
        FiscalPeriod,
        Extraction,
        Audit,
        Severity,
    )
    from seeding.extractors.oag_blue_book import source_hash_of
    from seeding import pdf_artifact

    editions = obs.accepted_editions()
    paths = {}
    for fy in sorted({e["fiscal_year"] for e in editions.values()}):
        period = FiscalPeriod(
            country_id=_counties(db)[0].country_id,
            label=f"FY{fy}",
            start_date=datetime(int(fy[:4]), 7, 1),
            end_date=datetime(int(fy[5:]), 6, 30),
        )
        db.add(period)
        db.flush()
        for e in editions.values():
            if e["fiscal_year"] != fy:
                continue
            path = tmp_path / f'{fy.replace("/", "-")}-{e["institution"]}.pdf'
            path.write_bytes(b"%PDF-1.4 synthetic byte seam\n%%EOF")
            paths[str(path)] = e
            doc = SourceDocument(
                country_id=period.country_id,
                publisher="Office of the Auditor-General",
                title=e["url"].rsplit("/", 1)[-1],
                url=e["url"],
                file_path=str(path),
                md5=e["md5"],
                doc_type=DocumentType.AUDIT,
                status=DocumentStatus.AVAILABLE,
                fetch_date=datetime(2026, 9, 27),
                meta={
                    "dataset_id": "oag_county_audits",
                    "oag_discovery": {
                        "fiscal_year": fy,
                        "kind": e["institution"],
                        "listed_at": f'{od.OAG_ORIGIN}/{fy.replace("/", "-")}-county-government-audit-reports/',
                    },
                    "extracted_md5": e["md5"],
                    "extraction_stats": {
                        "extractor": "oag_county_volume",
                        "fiscal_year": fy,
                        "volume_kind": e["institution"],
                        "findings": 47,
                        "contents_entries": 47,
                        "chapters_attributed": 47,
                        "pages": e["pages"],
                        "partial": False,
                        "refused": [],
                        "chapters_with_no_finding": [],
                        "unreadable_chapter_pages": [],
                        "missing_counties": [],
                        "rejected_cid": 0,
                    },
                },
            )
            db.add(doc)
            db.flush()
            for c in _counties(db):
                auditee = f'County {"Executive" if e["institution"] == "executives" else "Assembly"} of {c.canonical_name.removesuffix(" County")}'
                payload = {
                    "schema": "oag_county_volume/v1",
                    "fiscal_year": fy,
                    "volume_kind": e["institution"],
                    "entity_name": auditee,
                    "auditee": auditee,
                    "pdf_page": 1,
                    "finding_text": "Actual fixture text",
                }
                ext = Extraction(
                    source_document_id=doc.id,
                    page_number=1,
                    extractor="oag_county_volume",
                    confidence=0.9,
                    extracted_json=payload,
                )
                db.add(ext)
                db.flush()
                db.add(
                    Audit(
                        entity_id=c.id,
                        period_id=period.id,
                        source_document_id=doc.id,
                        extraction_id=ext.id,
                        audit_year=int(fy[5:]),
                        finding_text=payload["finding_text"],
                        source_hash=source_hash_of(payload),
                        page_ref="p.1",
                        severity=Severity.WARNING,
                        publishable=True,
                    )
                )
    db.commit()

    def identity(path):
        if not path.exists():
            raise FileNotFoundError("named PDF byte seam missing")
        e = paths[str(path)]
        return {
            "sha256": e["sha256"],
            "md5": e["md5"],
            "size_bytes": path.stat().st_size,
        }

    monkeypatch.setattr(pdf_artifact, "file_identity", identity)
    client = html_client()
    discovery, observation = obs.observe_listing(client)
    for d in discovery.volumes():
        if d.url not in SELECTED:
            observation["adopted"].append(obs.verify_adopted_volume(db, d))
    report = {
        "inventory_basis": "live_publisher_year_pages_plus_verified_adopted_state",
        "discovered": 8,
        "processed": [f'{e["fiscal_year"]} {e["institution"]}' for e in ENTRIES],
        "already_current": [
            f'{p["fiscal_year"]} {p["institution"]}: verified adopted retained edition'
            for p in observation["adopted"]
        ],
        "failed": [],
        "partial": [],
        "deferred": [],
    }
    scope = receipt_for(ENTRIES)
    scope["attempted"] = [e["source_url"] for e in ENTRIES]
    scope["processed"] = scope["attempted"].copy()
    return db, {
        "oag_county_discovery": discovery.as_meta(),
        "oag_county_observation": observation,
        "county_volumes": report,
        "audit_source_scope": scope,
        "source_mode": "live",
    }


def job(db, meta):
    from models import IngestionJob, IngestionStatus

    j = IngestionJob(
        domain="audits",
        dry_run=False,
        status=IngestionStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        meta=meta,
    )
    db.add(j)
    db.flush()
    return j


def test_full_current_listing_plus_verified_adoption_clears_real_coverage_warning(
    adopted,
):
    db, meta = adopted
    job(db, meta)
    r = county_audit_coverage_receipt(db)
    assert len(r["cells"]) == 376 and all(c["findings"] for c in r["cells"])
    assert r["run_gaps"] == []
    assert coverage_verdict(r)[0] == "OK"
    assert check_county_audit_coverage(db)[0].level == "OK"


def test_five_successes_without_observation_still_warn(adopted):
    db, meta = adopted
    meta.pop("oag_county_observation")
    job(db, meta)
    assert check_county_audit_coverage(db)[0].level == "WARN"


@pytest.mark.parametrize(
    "mutation",
    [
        "absent",
        "empty",
        "wrong_type",
        "manifest",
        "generator",
        "whole_world",
        "retained",
        "stale",
        "future",
        "naive",
        "missing_page",
        "bool_size",
        "empty_hash",
        "wrong_page",
        "wrong_discovery",
        "omit_adopted",
        "forged_adopted",
        "missing_scope",
    ],
)
def test_untrusted_observation_cannot_certify_coverage(adopted, mutation):
    db, meta = adopted
    r = meta["oag_county_observation"]
    if mutation == "absent":
        meta.pop("oag_county_observation")
    elif mutation == "empty":
        meta["oag_county_observation"] = {}
    elif mutation == "wrong_type":
        meta["oag_county_observation"] = []
    elif mutation == "manifest":
        r["accepted_manifest_sha256"] = "0" * 64
    elif mutation == "generator":
        r["generator_sha256"] = "0" * 64
    elif mutation == "whole_world":
        r["whole_world_coverage"] = True
    elif mutation == "retained":
        r["inventory_basis"] = "reviewed_retained_manifest"
    elif mutation in ("stale", "future", "naive"):
        r["observed_at"] = (
            (datetime.now(timezone.utc) - timedelta(days=2))
            if mutation == "stale"
            else (datetime.now(timezone.utc) + timedelta(days=2))
            if mutation == "future"
            else datetime.now()
        ).isoformat()
    elif mutation == "missing_page":
        r["pages"].pop()
    elif mutation == "bool_size":
        r["pages"][0]["size_bytes"] = True
    elif mutation == "empty_hash":
        r["pages"][0]["sha256"] = ""
    elif mutation == "wrong_page":
        r["pages"][0]["url"] = "https://example.com"
    elif mutation == "wrong_discovery":
        r["discovery"]["listing_url"] = "https://example.com"
    elif mutation == "omit_adopted":
        r["adopted"].pop()
    elif mutation == "forged_adopted":
        r["adopted"][0]["findings"] = 9999
    elif mutation == "missing_scope":
        meta.pop("audit_source_scope")
    job(db, meta)
    assert check_county_audit_coverage(db)[0].level != "OK"


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_country",
        "wrong_edition",
        "wrong_md5",
        "missing_bytes",
        "partial",
        "missing_stats",
        "boolean_chapters",
        "bad_attempt",
        "missing_row",
        "changed_text",
        "changed_hash",
        "changed_locator",
        "withheld",
    ],
)
def test_unselected_adoption_is_rechecked_against_actual_state(adopted, mutation):
    from models import SourceDocument, Country, Audit

    db, meta = adopted
    proof = meta["oag_county_observation"]["adopted"][0]
    doc = db.get(SourceDocument, proof["source_document_id"])
    audit = db.query(Audit).filter_by(source_document_id=doc.id).first()
    if mutation == "wrong_country":
        other = Country(
            name="Other",
            iso_code="OTH",
            currency="OTH",
            timezone="UTC",
            default_locale="en",
        )
        db.add(other)
        db.flush()
        doc.country_id = other.id
    elif mutation == "wrong_edition":
        doc.meta = {
            **doc.meta,
            "oag_discovery": {**doc.meta["oag_discovery"], "fiscal_year": "2023/2024"},
        }
    elif mutation == "wrong_md5":
        doc.md5 = "0" * 32
    elif mutation == "missing_bytes":
        Path(doc.file_path).unlink()
    elif mutation == "partial":
        doc.meta = {
            **doc.meta,
            "extraction_stats": {**doc.meta["extraction_stats"], "partial": True},
        }
    elif mutation == "missing_stats":
        doc.meta = {}
    elif mutation == "boolean_chapters":
        doc.meta = {
            **doc.meta,
            "extraction_stats": {
                **doc.meta["extraction_stats"],
                "chapters_attributed": True,
            },
        }
    elif mutation == "bad_attempt":
        doc.meta = {**doc.meta, "last_extraction_attempt": {"status": "failed"}}
    elif mutation == "missing_row":
        db.delete(audit)
    elif mutation == "changed_text":
        audit.finding_text = "wrong"
    elif mutation == "changed_hash":
        audit.source_hash = "0" * 64
    elif mutation == "changed_locator":
        audit.page_ref = "p.2"
    elif mutation == "withheld":
        audit.publishable = False
    db.flush()
    job(db, meta)
    assert check_county_audit_coverage(db)[0].level != "OK"


def test_new_listed_year_remains_failed_even_with_old_complete_cells(adopted):
    db, meta = adopted
    discovery, receipt = obs.observe_listing(html_client(year_extra="2025/2026"))
    meta["oag_county_discovery"] = discovery.as_meta()
    meta["oag_county_observation"] = receipt
    job(db, meta)
    assert check_county_audit_coverage(db)[0].level == "FAIL"


def test_missing_selected_institution_cell_remains_visible(adopted):
    from models import SourceDocument, Audit

    db, meta = adopted
    doc = db.query(SourceDocument).filter_by(url=ENTRIES[0]["source_url"]).one()
    db.delete(db.query(Audit).filter_by(source_document_id=doc.id).first())
    db.flush()
    job(db, meta)
    result = check_county_audit_coverage(db)[0]
    assert result.level == "WARN" and "46/47" in result.message


def test_observation_reads_only_five_qualified_html_pages():
    client = html_client()
    discovery, receipt = obs.observe_listing(client)
    assert len(client.calls) == 5 and all(not u.endswith(".pdf") for u in client.calls)
    assert len(discovery.volumes()) == 8 and not discovery.errors
    assert receipt["whole_world_coverage"] is False


@pytest.mark.parametrize(
    "change",
    [
        lambda r: httpx.Response(
            200, text="WAF", headers={"content-type": "text/html"}, request=r.request
        ),
        lambda r: httpx.Response(
            200,
            content=r.content,
            headers={"content-type": "application/pdf"},
            request=r.request,
        ),
        lambda r: httpx.Response(
            200,
            content=r.content,
            headers=r.headers,
            request=httpx.Request("GET", "https://example.com/"),
        ),
    ],
)
def test_empty_challenge_type_or_redirect_cannot_be_a_listing(change):
    discovery, receipt = obs.observe_listing(html_client(change=change))
    assert discovery.errors


def test_opt_in_is_enforced_at_direct_handler_before_io():
    from seeding.domains import audits
    from seeding.types import DomainRunContext
    from seeding.config import SeedingSettings

    for raw, dry, value in [
        (None, False, True),
        (MANIFEST.read_bytes(), True, True),
        (MANIFEST.read_bytes(), False, 1),
    ]:
        with pytest.raises(AuditSourceScopeError):
            audits.run(
                None,
                SeedingSettings(),
                DomainRunContext(
                    None, dry, audits_source_manifest=raw, audits_observe_listing=value
                ),
            )


from test_audits_source_scope import harness, allow_controlled_bytes, context, URLS


def test_opt_in_real_handler_observes_eight_but_only_writes_five(harness, monkeypatch):
    from seeding.domains import audits
    from seeding.config import SeedingSettings
    from models import SourceDocument

    allow_controlled_bytes(monkeypatch, harness)
    observed = []
    real_observe = obs.observe_listing

    def observe(client):
        observed.append(True)
        return real_observe(html_client())

    monkeypatch.setattr(obs, "observe_listing", observe)
    # This orchestration control names the adopted-source verifier seam;
    # adopted fixture tests above execute the actual verifier/coverage consumer.
    monkeypatch.setattr(
        obs,
        "verify_adopted_volume",
        lambda s, d: {"fiscal_year": d.fiscal_year, "institution": d.kind},
    )
    before = {
        d.id: copy.deepcopy(d.meta)
        for d in harness["session"].query(SourceDocument).all()
    }
    ctx = context()
    ctx.audits_observe_listing = True
    result = audits.run(
        harness["session"],
        SeedingSettings(audits_county_start_budget_seconds=1000),
        ctx,
    )
    assert observed == [True]
    assert harness["fetched"] == URLS and not result.errors
    assert result.metadata["oag_county_discovery"]["listing_fiscal_years"] == [
        "2021/2022",
        "2022/2023",
        "2023/2024",
        "2024/2025",
    ]
    assert result.metadata["county_volumes"]["discovered"] == 8
    assert len(result.metadata["county_volumes"]["processed"]) == 5
    assert len(result.metadata["county_volumes"]["already_current"]) == 3
    assert _run_gaps(SimpleNamespace(meta=result.metadata, status="completed")) == []
    for row in harness["session"].query(SourceDocument).all():
        if row.id in before:
            assert row.meta == before[row.id]


def test_unverified_unselected_volume_refuses_before_selected_writes(
    harness, monkeypatch
):
    from seeding.domains import audits
    from seeding.config import SeedingSettings
    from models import SourceDocument

    real_observe = obs.observe_listing
    monkeypatch.setattr(
        obs, "observe_listing", lambda client: real_observe(html_client())
    )
    ctx = context()
    ctx.audits_observe_listing = True
    before = harness["session"].query(SourceDocument).count()
    with pytest.raises(AuditSourceScopeError, match="identity/status"):
        audits.run(harness["session"], SeedingSettings(), ctx)
    assert (
        not harness["fetched"]
        and harness["session"].query(SourceDocument).count() == before
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "remove_newest_year",
        "remove_context",
        "false_integer",
        "missing_processed",
        "extra_attempt",
    ],
)
def test_independent_review_inventory_scope_regressions(adopted, mutation):
    db, meta = adopted
    r = meta["oag_county_observation"]
    if mutation == "remove_newest_year":
        meta["oag_county_discovery"]["listing_fiscal_years"].remove("2024/2025")
        r["discovery"] = copy.deepcopy(meta["oag_county_discovery"])
        r["pages"] = [p for p in r["pages"] if "2024-2025" not in p["url"]]
    elif mutation == "remove_context":
        meta.pop("audit_source_scope")
        meta.pop("oag_county_observation")
    elif mutation == "false_integer":
        meta["audit_source_scope"]["whole_world_coverage"] = 0
    elif mutation == "missing_processed":
        meta["audit_source_scope"]["processed"] = []
    else:
        meta["audit_source_scope"]["attempted"].append("https://example.com/extra.pdf")
    job(db, meta)
    assert check_county_audit_coverage(db)[0].level != "OK"


from test_audits_source_scope import cli_harness, cli_args


@pytest.mark.parametrize("case", ["no_manifest", "dry_run", "mixed_domain"])
def test_cli_observation_bad_opt_in_refuses_before_job_write(cli_harness, case):
    from seeding import cli
    from models import IngestionJob, SourceDocument

    harness, factory, settings = cli_harness
    args = cli_args() + ["--audits-observe-listing", "--no-dry-run"]
    if case == "no_manifest":
        args = [
            "seed",
            "--domain",
            "audits",
            "--audits-observe-listing",
            "--no-dry-run",
        ]
    elif case == "dry_run":
        args = cli_args() + ["--audits-observe-listing", "--dry-run"]
    else:
        args += ["--domain", "population"]
    assert cli.main(args) == 1
    with factory() as read:
        assert (
            read.query(IngestionJob).count() == read.query(SourceDocument).count() == 0
        )
    assert not harness["fetched"]


def test_backend_packaged_authority_matches_bounded_manifest(monkeypatch, tmp_path):
    import shutil

    source = Path(obs.__file__)
    packaged = tmp_path / "app" / "seeding" / "domains" / "audits" / "observation.py"
    packaged.parent.mkdir(parents=True)
    shutil.copyfile(source, packaged)
    shutil.copyfile(
        source.with_name("accepted-source-manifest.json"),
        packaged.with_name("accepted-source-manifest.json"),
    )
    monkeypatch.setattr(obs, "__file__", str(packaged))
    actual = list(obs.accepted_editions().values())
    assert len(actual) == 8
    assert receipt_for(actual[3:]) == receipt_for(ENTRIES)

"""County-volume extractions reach ``audits``, attributed and uniquely keyed.

Three defects this pins, each seen on the path:

* ``loader.py`` loaded ``oag_blue_book`` extractions only, so anything another
  extractor wrote stayed in ``extractions`` and never became a finding.
  Document 2391's 11 ``oag_county_audit`` rows are still in that state on
  production.
* The executives and assemblies volumes both number chapters 1..47, so the
  reference ``OAG-BB-{fy}-V{n}-P{para}`` names two auditees. 28 FY2020/21
  references are shared that way on production (1,498 rows, 1,470 distinct).
* A first load of a volume confirmed each new row with its own SELECT: 6,609
  round trips for the four years' backlog, at ~0.1s each against production.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.extractors import oag_county_volume as cv
from seeding.types import DomainRunContext
from tests.test_audits_loader_roundtrips import _AuditSelectCounter


@pytest.fixture()
def world(db_session):
    from models import (
        Country,
        DocumentStatus,
        DocumentType,
        Entity,
        EntityType,
        SourceDocument,
    )

    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    for name in ("Mombasa", "Nairobi"):
        db_session.add(
            Entity(
                country_id=country.id,
                type=EntityType.COUNTY,
                canonical_name=f"{name} County",
                slug=f"{name.lower()}-county",
            )
        )
    docs = {}
    for kind in ("executives", "assemblies"):
        d = SourceDocument(
            country_id=country.id,
            publisher="Office of the Auditor-General",
            title=f"{kind}.pdf",
            url=(
                "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-"
                f"GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-{kind.upper()}-2024-2025-1.pdf"
            ),
            md5=("e" if kind == "executives" else "a") * 32,
            fetch_date=datetime(2026, 9, 26, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add(d)
        docs[kind] = d
    db_session.commit()
    return db_session, docs


def _payload(kind: str, county: str, para: int) -> dict:
    role = "Executive" if kind == "executives" else "Assembly"
    return {
        "schema": cv.SCHEMA,
        "volume_kind": kind,
        "chapter_no": 1,
        "auditee": f"County {role} of {county}",
        "chapter_heading": f"COUNTY {role.upper()} OF {county.upper()} – NO.1",
        "entity_name": f"County {role} of {county}",
        "county_name": county,
        "fiscal_year": "2024/2025",
        "fiscal_year_sources": ["oag_year_page", "title_page"],
        "paragraph_no": para,
        "title": "Stalled Construction of the County Headquarters",
        "finding_text": "Stalled Construction of the County Headquarters Kshs.12,345,678.",
        "pdf_page": 14,
        "printed_page": 1,
        "subreport": "REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE OF PUBLIC RESOURCES",
        "opinion": None,
        "heading": "Basis for Conclusion",
        "sub_section": None,
        "severity": "WARNING",
        "amounts": [12345678.0],
        "extraction_method": "pdfplumber",
    }


def _add(session, doc, kind, county="Mombasa", n=1):
    from models import Extraction

    rows = []
    for i in range(n):
        row = Extraction(
            source_document_id=doc.id,
            page_number=14,
            extractor=cv.EXTRACTOR_ID,
            confidence=0.9,
            extracted_json=_payload(kind, county, i + 1),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


CTX = DomainRunContext(since=None, dry_run=False)


class TestCountyVolumeRowsLoad:
    def test_they_become_findings_on_the_existing_county(self, world):
        from models import Audit, Entity

        session, docs = world
        entities_before = session.query(Entity).count()
        _add(session, docs["executives"], "executives", county="Nairobi")
        stats = load_blue_book_extractions(session, docs["executives"], SeedingSettings(), CTX)
        assert stats.created == 1
        audit = session.query(Audit).one()
        assert audit.entity.slug == "nairobi-county"
        assert session.query(Entity).count() == entities_before  # nothing invented
        assert audit.audit_year == 2025
        assert audit.page_ref == "p.14"
        assert audit.source_hash and audit.extraction_id
        prov = audit.provenance[0]
        assert prov["source"] == cv.EXTRACTOR_ID
        assert prov["source_url"] == docs["executives"].url
        assert prov["title"] == "Stalled Construction of the County Headquarters"
        assert (prov["volume_kind"], prov["chapter_no"]) == ("executives", 1)

    def test_executive_and_assembly_chapter_1_do_not_share_a_reference(self, world):
        from models import Audit

        session, docs = world
        for kind in ("executives", "assemblies"):
            _add(session, docs[kind], kind)
            load_blue_book_extractions(session, docs[kind], SeedingSettings(), CTX)
        refs = sorted(a.external_reference for a in session.query(Audit).all())
        assert refs == ["OAG-CV-2024/2025-A1-P1", "OAG-CV-2024/2025-E1-P1"]


class TestFreshExtractionsSkipTheConfirm:
    def test_rows_created_in_this_transaction_cost_no_per_row_select(self, world):
        session, docs = world
        rows = _add(session, docs["executives"], "executives", n=25)
        with _AuditSelectCounter(session) as counted:
            stats = load_blue_book_extractions(
                session, docs["executives"], SeedingSettings(), CTX,
                fresh_extraction_ids=[r.id for r in rows],
            )
        assert stats.created == 25
        assert counted.single == [], f"{len(counted.single)} per-row SELECTs"

    def test_rows_not_declared_fresh_are_still_confirmed_one_each(self, world):
        """The existing guard, unchanged for everything else."""
        session, docs = world
        _add(session, docs["executives"], "executives", n=25)
        with _AuditSelectCounter(session) as counted:
            stats = load_blue_book_extractions(
                session, docs["executives"], SeedingSettings(), CTX
            )
        assert len(counted.single) == stats.created == 25


class TestDispatch:
    """``oag_county_audits`` has one parser_id. A combined volume must reach
    the splitter, not the single-entity path, which refused FY2024/25's
    volumes with ``auditee_not_found`` (their title is "AUDITOR-GENERAL'S
    REPORT ON THE COUNTY GOVERNMENTS", which neither shape matched)."""

    def test_a_combined_volume_is_split_per_county(self, world, monkeypatch, tmp_path):
        from seeding.extractors import oag_county_audit as ca
        from tests.test_oag_county_volume import BODY, _volume

        session, docs = world
        doc = docs["executives"]
        f = tmp_path / "v.pdf"
        f.write_bytes(b"%PDF-1.4")
        doc.file_path = str(f)
        doc.meta = {"oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}}
        # Volume-shaped: a contents list long enough to be one (a real volume
        # has 47). Only Mombasa is a county this test's database holds.
        names = ["Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Garissa",
                 "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru", "Embu"]
        pages = _volume(
            [
                (i + 1, f"County Executive of {n}", f"COUNTY EXECUTIVE OF {n.upper()} - NO.{i + 1}",
                 BODY.format(a=2 * i + 1, b=2 * i + 2))
                for i, n in enumerate(names)
            ]
        )
        monkeypatch.setattr(cv, "read_head", lambda *_a, **_k: pages[:12])
        monkeypatch.setattr(cv, "read_pages", lambda *_a, **_k: pages)
        monkeypatch.setattr(ca, "read_pages", lambda *_a, **_k: [(p.page_number, p.text) for p in pages])

        stats = ca.extract_county_audit(session, doc, SeedingSettings())
        assert stats["shape"] == "county_volume"
        assert stats["created"] == 2  # Mombasa's two findings
        assert len(stats["refused"]) == 11  # the counties this DB does not hold

    def test_a_discovered_volume_is_not_opened_twice(self, world, monkeypatch, tmp_path):
        """Opening a 34MB volume costs 12-19s of CPU however few pages are
        read. When discovery already says it is a volume, the head read is
        skipped and the full read checks the shape."""
        from seeding.extractors import oag_county_audit as ca

        session, docs = world
        doc = docs["executives"]
        f = tmp_path / "v.pdf"
        f.write_bytes(b"%PDF-1.4")
        doc.file_path = str(f)
        doc.meta = {"oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}}
        monkeypatch.setattr(cv, "read_head", lambda *_a, **_k: pytest.fail("head read"))
        seen = []
        monkeypatch.setattr(
            cv, "extract_county_volume", lambda *a, **k: seen.append(1) or {"shape": "county_volume"}
        )
        assert ca.extract_county_audit(session, doc, SeedingSettings())["shape"] == "county_volume"
        assert seen == [1]

    def test_a_short_contents_list_is_not_a_volume(self):
        from tests.test_oag_county_volume import BODY, _volume

        pages = _volume(
            [(1, "County Executive of Mombasa", "COUNTY EXECUTIVE OF MOMBASA - NO.1", BODY.format(a=1, b=2))]
        )
        assert not cv.looks_like_county_volume(pages)

    def test_a_volume_the_blue_book_walk_owns_stays_with_it(self, world, monkeypatch, tmp_path):
        """Documents 2395/2396 (FY2020/21, 1,498 published findings) were
        extracted by the Blue Book walk. Re-extracting them under a second
        extractor id would put a second set of rows beside the ones those
        findings point at."""
        from models import Extraction
        from seeding.extractors import oag_county_audit as ca

        session, docs = world
        doc = docs["assemblies"]
        f = tmp_path / "v.pdf"
        f.write_bytes(b"%PDF-1.4")
        doc.file_path = str(f)
        from seeding.extractors import oag_blue_book as bb

        doc.meta = {"extracted_md5": doc.md5, "extractor_version": bb.EXTRACTOR_VERSION}
        session.add(
            Extraction(
                source_document_id=doc.id, page_number=1, extractor="oag_blue_book",
                confidence=0.9, extracted_json={"schema": "oag_blue_book/v1"},
            )
        )
        session.flush()
        monkeypatch.setattr(
            cv, "read_head", lambda *_a, **_k: pytest.fail("read the head of a delegated volume")
        )
        stats = ca.extract_county_audit(session, doc, SeedingSettings())
        assert stats["reason"] == "already_extracted_by_delegate"

"""stalled_projects end to end: fetch, write, API, OAG corroboration (#230).

The parser has its own file (test_cob_stalled_projects_parser.py). This one
drives what sits around it (the download and the gate have their own
files too), with the parse output built from the same
verbatim COB extracts.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from decimal import Decimal

import pytest

from seeding.config import SeedingSettings
from seeding.domains.stalled_projects import cob_parser as cp
from seeding.http_client import PdfDownloadIncomplete

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cob_cbirr"
ANNUAL = json.loads((FIXTURES / "fy2025_26_annual.json").read_text(encoding="utf-8"))
LISTING = (FIXTURES / "listing_2026-09-26.html").read_text(encoding="utf-8")
EDITION_URL = ANNUAL["source_url"]

_PDF_A = b"%PDF-1.7\n" + b"edition A\n" * 64 + b"%%EOF\n"


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        rate_limit="1000/sec",
    )
    s.ensure_directories()
    return s


# --------------------------------------------------------------------------
# Fetch: refuse, never fall back
# --------------------------------------------------------------------------


def _county_from_fixture(county: str) -> dict:
    c = ANNUAL["counties"][county]
    parsed = cp.parse_table(c["header"], [(p, r) for p, r in c["rows"]])
    text = cp.clean(c["previous_page_text"] + " " + c["caption_page_text"])
    m = cp.SUMMARY_RE.search(text)
    summary = cp.parse_summary_sentence(text[m.start():]) if m else None
    t26 = cp.parse_table_2_6([(p, r) for p, r in ANNUAL["table_2_6"]["rows"]])["counties"].get(county)
    caption = cp.find_captions(cp.Document([c["caption_page_text"]]))[0]
    return {
        "kind": "county",
        "county": county,
        "slug": cp.county_slug(county),
        "summary": summary,
        "table_2_6": t26,
        "tables": [dict(parsed, caption=caption["caption"], caption_page=c["caption_page"],
                        table_no=caption["table_no"], as_of=caption["as_of"],
                        county_as_printed=caption["county_printed"], reported_by=None, notes=c["notes"])],
        "reconciliation": cp.reconcile(parsed["rows"], parsed["total"], summary, t26),
    }


def _vihiga() -> dict:
    text = cp.clean(ANNUAL["vihiga_statement_page"]["text"])
    m = next(m for m in cp.STATEMENT_RE.finditer(text) if "stalled" in m.group(0).lower())
    return {
        "kind": "county", "county": "Vihiga", "slug": "vihiga-county",
        "statement": {"text": cp.clean(m.group(0)), "source_page": 876},
        "table_2_6": cp.parse_table_2_6([(p, r) for p, r in ANNUAL["table_2_6"]["rows"]])["counties"]["Vihiga"],
        "reconciliation": cp.reconcile([], None, None, None),
    }


EDITION = {
    "kind": "edition", "title": "County Governments Budget Implementation Review Report",
    "fiscal_year": "FY2025/26", "period": "annual", "published": "August 2026",
    "captions_found": 20,
}


def _records():
    return [dict(EDITION)] + [
        _county_from_fixture(c) for c in ("Kericho", "Kakamega", "Trans Nzoia")
    ] + [_vihiga()]


class TestFetch:
    @pytest.fixture()
    def stubs(self, monkeypatch, settings, tmp_path):
        from seeding import cob_cbirr
        from seeding.domains.stalled_projects import fetcher

        pdf = tmp_path / "e.pdf"
        pdf.write_bytes(_PDF_A)
        state = {"records": _records(), "download": None}
        monkeypatch.setattr(
            cob_cbirr, "list_cbirr_editions",
            lambda client, s: ("https://cob.go.ke/listing", cob_cbirr.parse_listing(LISTING)),
        )

        def _download(client, url, s):
            if state["download"]:
                raise state["download"]
            return cob_cbirr.CbirrPdf(url=url, path=pdf, sha256="abc", fingerprint="Final 5")

        monkeypatch.setattr(cob_cbirr, "download_cbirr", _download)
        monkeypatch.setattr(fetcher, "parse_edition", lambda path, s: state["records"])
        return state

    def _fetch(self, settings):
        from seeding import freshness
        from seeding.domains.stalled_projects import fetcher

        freshness.reset("stalled_projects")
        return fetcher.fetch(settings, client=None), freshness.get("stalled_projects")

    def test_live_run_names_the_edition(self, settings, stubs):
        result, mode = self._fetch(settings)
        assert result.ok and mode["mode"] == "live"
        assert result.edition["wpdmdl"] == 16482 and result.edition["as_of"] == "2026-06-30"
        assert "wpdmdl=16482" in mode["detail"] and "as of 2026-06-30" in mode["detail"]

    def test_captions_without_rows_refuses(self, settings, stubs):
        stubs["records"] = [dict(EDITION)] + [
            dict(c, reconciliation=dict(c["reconciliation"], rows=0)) for c in _records()[1:]
        ]
        result, mode = self._fetch(settings)
        assert not result.ok and mode == {
            "mode": "refused", "reason": "captions_without_rows",
            "detail": mode["detail"],
        }

    def test_incomplete_download_refuses_and_names_the_edition(self, settings, stubs):
        stubs["download"] = PdfDownloadIncomplete("slow", bytes_downloaded=27_751_154)
        result, mode = self._fetch(settings)
        assert (result.ok, mode["reason"]) == (False, "download_incomplete")
        assert result.listing_newest["wpdmdl"] == 16482


# --------------------------------------------------------------------------
# Writer + API
# --------------------------------------------------------------------------

LEGACY_NAIROBI = [
    {"project_name": "Eastlands Urban Renewal Phase II", "oag_reference": "OAG/NRB/2023/INF-012",
     "contracted_amount": 3200000000, "amount_paid": 1920000000},
]


@pytest.fixture()
def counties(db_session, seed_country):
    from models import Entity, EntityType

    made = {}
    for i, name in enumerate(["Kericho", "Kakamega", "Trans Nzoia", "Vihiga", "Nairobi"], start=501):
        e = Entity(id=i, country_id=seed_country.id, type=EntityType.COUNTY,
                   canonical_name=f"{name} County", slug=cp.county_slug(name),
                   meta={"stalled_projects": LEGACY_NAIROBI, "stalled_projects_count": 1}
                   if name == "Nairobi" else {"governor": "x"})
        db_session.add(e)
        made[name] = e
    db_session.commit()
    return made


def _write(db_session):
    from seeding.domains.stalled_projects import writer

    recs = _records()
    edition = dict(recs[0], url=EDITION_URL, wpdmdl=16482, sha256="abc", as_of="2026-06-30")
    return writer.write(recs[1:], edition, db_session)


def _block(client, entity_id):
    return client.get(f"/api/v1/counties/{entity_id}/comprehensive").json()["stalled_projects"]


class TestWriteAndServe:
    def test_rows_carry_their_evidence(self, client, db_session, counties):
        _write(db_session)
        block = _block(client, counties["Kericho"].id)
        assert block["count"] == 6
        row = block["projects"][0]
        assert row["project_name"] == "Kiboybei Water Supply"
        assert row["source_url"] == EDITION_URL
        assert row["source_page"] == 268
        assert row["as_of"] == "2026-06-30"
        assert row["reported_by"] == cp.REPORTED_BY
        assert row["cells"]["Estimated Value of the Project (Kshs.)"] == "36,731,977.51"
        assert block["source"]["wpdmdl"] == 16482
        assert block["reconciliation"]["status"] == "agrees"

    def test_mismatch_is_published_not_hidden(self, client, db_session, counties):
        _write(db_session)
        block = _block(client, counties["Kakamega"].id)
        assert block["count"] == 10
        assert block["reconciliation"]["status"] == "disagrees"
        assert block["cob_statements"]["summary"]["count"] == 26
        assert block["cob_statements"]["table_2_6"]["printed"]["count"] == "26"

    def test_unit_conflict_withholds_the_money_but_keeps_the_row(self, client, db_session, counties):
        _write(db_session)
        block = _block(client, counties["Trans Nzoia"].id)
        row = block["projects"][0]
        assert row["estimated_value_kes"] is None and row["amount_paid_kes"] is None
        assert "estimated_value:withheld" in row["flags"]
        assert row["cells"]["Estimated Value (Kshs.)"] == "874"  # still shown as printed
        assert block["total_contracted_value"] is None

    def test_county_that_reported_nothing_is_cobs_words_not_zero(self, client, db_session, counties):
        _write(db_session)
        block = _block(client, counties["Vihiga"].id)
        assert block["count"] is None
        assert block["reason"] == "no_table_in_edition"
        assert "did not report on stalled projects as of 30 June,2026" in block["cob_statements"]["statement"]["text"]
        assert block["cob_statements"]["table_2_6"]["printed"]["count"] == "-"

    def test_a_freshly_bootstrapped_slug_still_matches(self, client, db_session, counties):
        """bootstrap.py names a new county entity "kericho-035", not
        "kericho-county" as production does."""
        counties["Kericho"].slug = "kericho-035"
        db_session.commit()
        stats = _write(db_session)
        assert "Kericho" not in stats["unmatched"]
        assert _block(client, counties["Kericho"].id)["count"] == 6

    def test_invented_records_do_not_survive_a_live_write(self, client, db_session, counties):
        _write(db_session)
        db_session.refresh(counties["Nairobi"])
        assert [k for k in counties["Nairobi"].meta if k.startswith("stalled_projects")] == []
        assert _block(client, counties["Nairobi"].id)["reason"] == "no_evidence_backed_source"


class TestRefusedRunKeepsTheLastEdition:
    def test_refusal_keeps_cob_rows_and_drops_legacy(self, db_session, counties, monkeypatch):
        from seeding import freshness
        from seeding.domains import stalled_projects
        from seeding.domains.stalled_projects import fetcher
        from seeding.types import DomainRunContext

        _write(db_session)
        # Legacy keys reappear (a stale deploy writing the old shape).
        n = counties["Nairobi"]
        n.meta = dict(n.meta, stalled_projects_count=1)
        db_session.commit()
        monkeypatch.setattr(
            fetcher, "fetch",
            lambda s, c=None: fetcher._refuse("download_incomplete", "stub",
                                              listing_newest={"wpdmdl": 16500}),
        )
        freshness.reset("stalled_projects")
        result = stalled_projects.run(db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        db_session.refresh(counties["Kericho"])
        db_session.refresh(n)
        assert counties["Kericho"].meta["stalled_projects"]["source"]["wpdmdl"] == 16482
        assert "stalled_projects_count" not in n.meta
        assert result.metadata["cbirr_published"]["wpdmdl"] == 16482
        assert result.metadata["cbirr_listing_newest"]["wpdmdl"] == 16500


class TestOagCorroboration:
    """The Auditor-General's FY2024/25 county-executives volume, para 939
    (PDF p.459), heading verbatim: "Stalled Construction and Equipping of
    Theater at Ainamoi Health Centre". COB's Kericho row, verbatim:
    "Construction and equipping of the theatre at Ainamoi Health Centre"."""

    HEADING = "Stalled Construction and Equipping of Theater at Ainamoi Health Centre"

    @pytest.fixture()
    def findings(self, db_session, counties, seed_source_doc):
        from models import Audit, Extraction, FiscalPeriod, Severity

        fp = FiscalPeriod(id=931, country_id=seed_source_doc.country_id, label="FY2024/25",
                          start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30))
        db_session.add(fp)
        db_session.flush()
        rows = []
        for n, (heading, para, entity) in enumerate([
            (self.HEADING, 939, counties["Kericho"]),
            # Real FY2020/21 heading published in production for Kericho
            # (OAG-BB-2020/2021-V35-P397); names no project in COB's table.
            ("Delayed Completion of Construction of Speaker’s Residence", 397, counties["Kericho"]),
        ]):
            ext = Extraction(source_document_id=seed_source_doc.id, page_number=459,
                             extracted_json={"title": heading, "paragraph_no": para},
                             extractor="test")
            db_session.add(ext)
            db_session.flush()
            rows.append(Audit(entity_id=entity.id, period_id=fp.id,
                              finding_text=heading + ". The project had not been completed as at the time of audit.",
                              severity=Severity.WARNING, source_document_id=seed_source_doc.id,
                              query_type="Other Matter", page_ref="p.459", extraction_id=ext.id,
                              provenance=[{"title": heading}], amount=Decimal(0)))
        db_session.add_all(rows)
        db_session.commit()

    def test_matching_finding_is_attached_to_the_cob_row(self, client, db_session, counties, findings, monkeypatch):
        import main

        monkeypatch.setattr(main, "_audit_is_display_grade", lambda a: True)
        _write(db_session)
        block = _block(client, counties["Kericho"].id)
        theatre = next(p for p in block["projects"] if "Ainamoi" in (p["project_name"] or ""))
        (oag,) = theatre["oag_corroboration"]
        assert oag["speaker"] == "Auditor-General"
        assert oag["heading"] == self.HEADING
        assert oag["paragraph"] == 939 and oag["page"] == "p.459"
        assert oag["source_url"].startswith("https://")
        assert set(oag["match"]["shared_terms"]) == {"ainamoi", "health", "centre"}
        # The speaker's residence names nothing in COB's table: shown alone.
        assert [f["paragraph"] for f in block["oag_findings"]] == [397]


class TestLinkingIsConservative:
    """Verbatim names. COB rows from the FY2025/26 annual; OAG headings from
    the Auditor-General's FY2024/25 county-executives volume."""

    def _linked(self, cob_name, oag_heading):
        from services.stalled_projects import _link

        linked, _ = _link([{"project_name": cob_name}], [{"heading": oag_heading, "text": ""}])
        return bool(linked)

    def test_same_project_different_spelling_links(self):
        # Kericho; OAG para 939 ("Theater" vs COB's "theatre").
        assert self._linked(
            "Construction and equipping of the theatre at Ainamoi Health Centre",
            "Stalled Construction and Equipping of Theater at Ainamoi Health Centre",
        )

    def test_shared_facility_words_alone_do_not_link(self):
        # Uasin Gishu; OAG para 30. Different projects that share only
        # "training" and "centre" — linked by the first version of this rule.
        assert not self._linked(
            "Phase 1 Special Needs Assessment, Training and Reha- bilitation Centre, Chebolol",
            "Stalled Construction of Chebororwa Agricultural Training Centre",
        )

    def test_one_shared_place_word_is_not_enough(self):
        # Nandi: COB's boda boda shed at Chepterwai vs OAG para 768's
        # Chepterwai Sub-County Hospital.
        assert not self._linked(
            "Construction of Chept- erwai boda boda shed",
            "Delayed Completion Works at Chepterwai Sub-County Hospital",
        )


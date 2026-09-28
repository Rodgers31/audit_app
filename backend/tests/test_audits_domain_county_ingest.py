"""The audits domain's county pass: register, order, budget, resume.

What the nightly did before this: "oag_county_audits: 5 known + 0 newly
discovered document(s)" every night for months, green, while OAG published
FY2021/22 to FY2024/25. What it must do now, with the network and the PDFs
replaced by fakes:

* register every discovered document before downloading any of them;
* process combined volumes newest fiscal year first;
* stop STARTING volumes past the start budget, and say which ones it left;
* bank each volume with a commit, so a later timeout does not lose it;
* not re-fetch a per-county report its year's volumes already cover.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

import seeding.domains.audits as audits_domain
from seeding import oag_discovery as od
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext

UP = "https://www.oagkenya.go.ke/wp-content/uploads"


def _vol(fy, kind, name):
    return od.OagDocument(
        url=f"{UP}/{name}", fiscal_year=fy, kind=kind, found_on="year_page",
        listed_at=f"https://www.oagkenya.go.ke/{fy.replace('/', '-')}-county-government-audit-reports/",
    )


DISCOVERY = od.CountyAuditDiscovery(
    listing_fiscal_years=["2020/2021", "2021/2022", "2023/2024", "2024/2025"],
    documents=[
        _vol("2021/2022", "executives", "AUDITOR-GENERAL-S-REPORT-ON-THE-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2021-2022-VOLUME-1.pdf"),
        _vol("2024/2025", "assemblies", "AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf"),
        _vol("2023/2024", "executives", "GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf"),
        _vol("2024/2025", "executives", "AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf"),
        od.OagDocument(
            url=f"{UP}/2023/11/County-Assembly-of-Homa-Bay-2021-2022-1.pdf",
            fiscal_year="2021/2022", kind="single_entity", found_on="year_page",
            listed_at="p", entity="Homa Bay",
        ),
    ],
)

#: Registered before discovery existed, and no longer linked by OAG under
#: this name (document 2391). Its year is covered by the combined volumes.
STALE_SINGLE = f"{UP}/2023/11/County-Assembly-of-Homa-Bay-2021-2022.pdf"


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


@pytest.fixture()
def harness(db_session, monkeypatch, tmp_path):
    from models import (
        Country, DocumentStatus, DocumentType, Extraction, SourceDocument,
    )

    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    db_session.add(
        SourceDocument(
            country_id=country.id, publisher="Office of the Auditor-General",
            title="stale.pdf", url=STALE_SINGLE, fetch_date=datetime(2026, 1, 1),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        )
    )
    db_session.commit()

    clock = Clock()
    fetched, commits = [], []
    # Registration must precede every download: snapshot the registered URLs
    # at the moment of the first fetch.
    registered_at_first_fetch = []

    def fake_fetch(session, client, settings, *, url, **kw):
        if not registered_at_first_fetch:
            registered_at_first_fetch.append(
                {u for (u,) in session.query(SourceDocument.url).all()}
            )
        fetched.append(url)
        doc = session.query(SourceDocument).filter_by(url=url).one()
        f = tmp_path / f"{len(fetched)}.pdf"
        f.write_bytes(b"%PDF-1.4")
        # Same URL, same bytes, same md5, run after run.
        md5 = hashlib.md5(url.encode()).hexdigest()
        doc.file_path, doc.md5, doc.status = str(f), md5, DocumentStatus.AVAILABLE
        session.flush()
        return doc

    def fake_parser(session, doc, settings):
        from seeding.extractors.oag_county_volume import already_extracted

        done = already_extracted(session, doc)
        if done:  # what the real dispatch returns for a current volume
            return {"created": 0, "skipped": done, "reason": "already_extracted"}
        # Each volume costs 100s of the budget.
        clock.now += 100
        row = Extraction(
            source_document_id=doc.id, page_number=1, extractor="oag_county_volume",
            confidence=0.9, extracted_json={"schema": "test"},
        )
        session.add(row)
        session.flush()
        doc.meta = {**(doc.meta or {}), "extracted_md5": doc.md5}
        return {"created": 1, "shape": "county_volume", "fresh_extraction_ids": [row.id]}

    loads = []

    def fake_load(session, doc, settings, context, *, fresh_extraction_ids=()):
        from seeding.domains.audits.writer import PersistenceStats

        loads.append((doc.url, list(fresh_extraction_ids)))
        return PersistenceStats()

    @contextmanager
    def fake_client(_settings):
        yield object()

    real_commit = db_session.commit

    def counting_commit():
        commits.append(len(fetched))
        real_commit()

    monkeypatch.setattr(audits_domain, "create_http_client", fake_client)
    monkeypatch.setattr(audits_domain, "time", clock)
    monkeypatch.setattr(audits_domain.fetcher, "_discover_audit_pdfs_via_wp_api", lambda c: [])
    monkeypatch.setattr(od, "discover_county_audit_documents", lambda client, **k: DISCOVERY)
    monkeypatch.setattr("seeding.fetch_documents.fetch_document", fake_fetch)
    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: fake_parser if pid == "oag_county_audit" else None,
    )
    monkeypatch.setattr("seeding.domains.audits.loader.load_blue_book_extractions", fake_load)
    monkeypatch.setattr(db_session, "commit", counting_commit)
    return {
        "session": db_session, "fetched": fetched, "commits": commits, "loads": loads,
        "registered_at_first_fetch": registered_at_first_fetch, "clock": clock,
    }


def _run(session, budget):
    settings = SeedingSettings(audits_county_start_budget_seconds=budget)
    return audits_domain.run(
        session=session, settings=settings,
        context=DomainRunContext(since=None, dry_run=False),
    )


class TestCountyIngest:
    def test_registered_before_fetched_newest_first_and_deferral_recorded(self, harness):
        from models import SourceDocument

        result = _run(harness["session"], budget=150)
        # 0s: FY24/25 executives starts; 100s: FY24/25 assemblies starts;
        # 200s: past the 150s start budget, so the rest are deferred.
        assert harness["fetched"] == [d.url for d in DISCOVERY.volumes()[:2]]
        report = result.metadata["county_volumes"]
        assert report["discovered"] == 4
        assert report["processed"] == [
            "2024/2025 executives: 1 finding(s)",
            "2024/2025 assemblies: 1 finding(s)",
        ]
        assert report["deferred"] == ["2023/2024 executives", "2021/2022 executives"]

        registered = harness["registered_at_first_fetch"][0]
        assert {d.url for d in DISCOVERY.documents} <= registered
        homa = harness["session"].query(SourceDocument).filter_by(
            url=f"{UP}/2023/11/County-Assembly-of-Homa-Bay-2021-2022-1.pdf"
        ).one()
        assert homa.meta["registration"] == "discovered_not_fetched"
        assert homa.meta["oag_discovery"]["kind"] == "single_entity"
        assert homa.file_path is None  # registered, never downloaded

        # The listing the freshness gate reads.
        assert result.metadata["oag_county_discovery"]["listing_fiscal_years"][-1] == "2024/2025"

    def test_each_volume_is_committed_as_it_completes(self, harness):
        _run(harness["session"], budget=150)
        # A commit after the first volume and after the second: a timeout in
        # the third keeps both.
        assert harness["commits"][:2] == [1, 2]

    def test_the_loader_is_told_which_rows_are_fresh(self, harness):
        _run(harness["session"], budget=150)
        assert all(ids for _url, ids in harness["loads"])

    def test_the_next_run_resumes_with_what_was_left(self, harness):
        _run(harness["session"], budget=150)
        harness["fetched"].clear()
        result = _run(harness["session"], budget=150)
        report = result.metadata["county_volumes"]
        assert report["already_current"] == ["2024/2025 executives", "2024/2025 assemblies"]
        assert [p.split(":")[0] for p in report["processed"]] == [
            "2023/2024 executives", "2021/2022 executives",
        ]
        assert report["deferred"] == []

    def test_start_cutoff_does_not_recheck_current_volumes(self, harness):
        _run(harness["session"], budget=10_000)
        harness["fetched"].clear()
        result = _run(harness["session"], budget=0)
        report = result.metadata["county_volumes"]
        assert report["already_current"] == []
        assert report["deferred"] == [
            "2024/2025 executives", "2024/2025 assemblies",
            "2023/2024 executives", "2021/2022 executives",
        ]
        assert harness["fetched"] == []

    def test_a_covered_per_county_report_is_not_re_fetched(self, harness):
        _run(harness["session"], budget=10_000)
        assert STALE_SINGLE not in harness["fetched"]
        assert all("Homa-Bay" not in u for u in harness["fetched"])

    def test_a_discovery_error_makes_the_run_say_so(self, harness, monkeypatch):
        broken = od.CountyAuditDiscovery(errors=["listing unreachable: ConnectError"])
        monkeypatch.setattr(od, "discover_county_audit_documents", lambda client, **k: broken)
        result = _run(harness["session"], budget=150)
        assert any("OAG county discovery: listing unreachable" in e for e in result.errors)

    def test_a_listing_outage_still_resumes_known_volumes(self, harness, monkeypatch):
        """Volumes registered by an earlier run stay in the queue on a night
        OAG's listing is unreachable."""
        _run(harness["session"], budget=150)
        harness["fetched"].clear()
        broken = od.CountyAuditDiscovery(errors=["listing unreachable"])
        monkeypatch.setattr(od, "discover_county_audit_documents", lambda client, **k: broken)
        result = _run(harness["session"], budget=10_000)
        assert [p.split(":")[0] for p in result.metadata["county_volumes"]["processed"]] == [
            "2023/2024 executives", "2021/2022 executives",
        ]


class TestNationalCandidates:
    def test_the_popular_report_is_not_offered_to_the_blue_book_walk(self):
        """Document 2393 logged 'Blue Book structure not recognised (toc=4
        entries, offset=None)' every night."""
        from seeding.domains.audits.candidates import split_national_audit_candidates

        keep, rejected = split_national_audit_candidates(
            [
                f"{UP}/2025/06/Auditor-Generals-Popular-Report-on-National-Government-2023-2024.pdf",
                f"{UP}/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf",
            ]
        )
        assert keep == [f"{UP}/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"]
        assert [why for _u, why in rejected] == ["popular_report"]

    def test_new_national_candidate_is_still_discovered_and_attempted(
        self, harness, monkeypatch
    ):
        from models import DocumentStatus, DocumentType, SourceDocument
        from seeding import fetch_documents
        from seeding.extractors import get_parser

        session = harness["session"]
        _run(session, budget=10_000)
        harness["fetched"].clear()
        country_id = session.query(SourceDocument).first().country_id
        original_fetch = fetch_documents.fetch_document
        county_parser = get_parser("oag_county_audit")

        def fetch_new(session, client, settings, *, url, **kwargs):
            if url == NATIONAL:
                session.add(SourceDocument(
                    country_id=country_id, publisher="Office of the Auditor-General",
                    title=url.rsplit("/", 1)[-1], url=url,
                    fetch_date=datetime(2026, 1, 1), doc_type=DocumentType.AUDIT,
                    status=DocumentStatus.FAILED,
                ))
                session.flush()
            return original_fetch(session, client, settings, url=url, **kwargs)

        monkeypatch.setattr(audits_domain.fetcher, "_discover_audit_pdfs_via_wp_api", lambda c: [NATIONAL])
        monkeypatch.setattr(fetch_documents, "fetch_document", fetch_new)
        monkeypatch.setattr(
            "seeding.extractors.get_parser",
            lambda pid: county_parser if pid == "oag_county_audit"
            else (lambda s, d, st: {"created": 0, "skipped_unchanged": True}),
        )
        result = _run(session, budget=150)
        assert harness["fetched"][-1] == NATIONAL
        assert result.metadata["deferred_discovery"] == []
        assert result.metadata["deferred_documents"] == []

    def test_malformed_national_metadata_is_not_replaced_by_retry_stamp(self, harness):
        from models import DocumentStatus, DocumentType, SourceDocument

        session = harness["session"]
        doc = SourceDocument(
            country_id=session.query(SourceDocument).first().country_id,
            publisher="Office of the Auditor-General", title="national.pdf",
            url=NATIONAL, fetch_date=datetime(2026, 1, 1),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
            meta=["unreviewed source metadata"],
        )
        session.add(doc)
        session.commit()
        with pytest.raises(ValueError, match="malformed metadata"):
            audits_domain._record_scheduled_attempt(session, doc)
        session.expire(doc)
        assert doc.meta == ["unreviewed source metadata"]


NATIONAL = f"{UP}/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
LEGACY_EXECUTIVES = f"{UP}/2023/02/REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-I-COUNTY-EXECUTIVES.pdf"
LEGACY_ASSEMBLIES = f"{UP}/2023/02/REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-II-COUNTY-ASSEMBLIES.pdf"


def test_slow_refused_national_and_legacy_books_cannot_starve_current_volumes(
    harness, monkeypatch
):
    """Force the nightly's timing: a 100s national refusal and two 90s
    legacy refusals exhausted the 150s start budget before any new volume.
    The later queue still has to identify which work it deferred.
    """
    from models import DocumentStatus, DocumentType, SourceDocument
    from seeding.extractors.reconciliation import IncompleteExtraction

    session = harness["session"]
    country_id = session.query(SourceDocument).first().country_id
    for url in (NATIONAL, LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES):
        session.add(SourceDocument(
            country_id=country_id, publisher="Office of the Auditor-General",
            title=url.rsplit("/", 1)[-1], url=url, fetch_date=datetime(2026, 1, 1),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        ))
    session.commit()
    harness["commits"].clear()
    county_parser = __import__("seeding.extractors", fromlist=["get_parser"]).get_parser("oag_county_audit")

    def slow_county(session, doc, settings):
        if doc.url in (LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES):
            harness["clock"].now += 90
            raise IncompleteExtraction("unreadable source text; rows kept")
        return county_parser(session, doc, settings)

    def slow_national(session, doc, settings):
        harness["clock"].now += 100
        raise IncompleteExtraction("reconciliation review required; rows kept")

    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: slow_national if pid == "oag_blue_book" else slow_county,
    )

    result = _run(session, budget=150)
    report = result.metadata["county_volumes"]
    assert [p.split(":")[0] for p in report["processed"]] == [
        "2024/2025 executives", "2024/2025 assemblies",
    ]
    assert report["deferred"] == ["2023/2024 executives", "2021/2022 executives"]
    assert harness["fetched"] == [d.url for d in DISCOVERY.volumes()[:2]]
    assert {d["url"] for d in result.metadata["deferred_documents"]} == {
        NATIONAL, LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES,
    }
    assert result.metadata["deferred_discovery"] == ["oag_national_audits"]
    assert harness["clock"].now == 200

    harness["fetched"].clear()
    result = _run(session, budget=150)
    assert result.metadata["county_volumes"]["already_current"] == [
        "2024/2025 executives", "2024/2025 assemblies",
    ]
    assert [p.split(":")[0] for p in result.metadata["county_volumes"]["processed"]] == [
        "2023/2024 executives", "2021/2022 executives",
    ]

    harness["fetched"].clear()
    result = _run(session, budget=150)
    assert result.metadata["county_volumes"]["processed"] == []
    assert len(result.metadata["county_volumes"]["already_current"]) == 4
    assert [d["url"] for d in result.metadata["deferred_documents"]] == [LEGACY_ASSEMBLIES]
    assert result.metadata["deferred_discovery"] == []
    assert harness["fetched"][-2:] == [NATIONAL, LEGACY_EXECUTIVES]
    assert any("unreadable source text" in error for error in result.errors)
    assert any("reconciliation review required" in error for error in result.errors)

    harness["fetched"].clear()
    result = _run(session, budget=150)
    assert harness["fetched"][-2:] == [LEGACY_ASSEMBLIES, NATIONAL]
    assert [d["url"] for d in result.metadata["deferred_documents"]] == [LEGACY_EXECUTIVES]


@pytest.mark.parametrize("national_refused", [True, False])
def test_repeated_slow_national_retry_cannot_starve_older_county_reports(
    harness, monkeypatch, national_refused
):
    from models import DocumentStatus, DocumentType, SourceDocument
    from seeding.extractors.reconciliation import IncompleteExtraction

    session = harness["session"]
    _run(session, budget=10_000)  # All current volumes have been banked.
    country_id = session.query(SourceDocument).first().country_id
    for url in (NATIONAL, LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES):
        session.add(SourceDocument(
            country_id=country_id, publisher="Office of the Auditor-General",
            title=url.rsplit("/", 1)[-1], url=url, fetch_date=datetime(2026, 1, 1),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        ))
    session.commit()
    county_parser = __import__("seeding.extractors", fromlist=["get_parser"]).get_parser("oag_county_audit")

    def slow_county(session, doc, settings):
        if doc.url in (LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES):
            harness["clock"].now += 90
            raise IncompleteExtraction("unreadable source text; rows kept")
        return county_parser(session, doc, settings)

    def slow_national(session, doc, settings):
        harness["clock"].now += 200
        if national_refused:
            raise IncompleteExtraction("reconciliation review required; rows kept")
        return {"created": 0, "skipped_unchanged": True}

    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: slow_national if pid == "oag_blue_book" else slow_county,
    )
    older = {NATIONAL, LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES}
    attempts, deferred = [], []
    for _ in range(3):
        harness["fetched"].clear()
        result = _run(session, budget=150)
        attempts.append([url for url in harness["fetched"] if url in older])
        deferred.append([item["url"] for item in result.metadata["deferred_documents"]])
        assert len(result.metadata["county_volumes"]["already_current"]) == 4

    assert attempts == [
        [NATIONAL],
        [LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES],
        [NATIONAL],
    ]
    assert deferred == [
        [LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES],
        [NATIONAL],
        [LEGACY_EXECUTIVES, LEGACY_ASSEMBLIES],
    ]


class TestNationalReExtractionIsBanked:
    """When the backlog permits national work, re-extraction is banked.

    The CLI commits once at the end and rolls the whole domain back on a
    timeout. A national re-read must be committed after it completes.
    """

    @pytest.fixture()
    def national(self, harness, monkeypatch):
        from models import DocumentStatus, DocumentType, SourceDocument

        session = harness["session"]
        session.add(
            SourceDocument(
                country_id=session.query(SourceDocument).first().country_id,
                publisher="Office of the Auditor-General",
                title="blue-book.pdf", url=NATIONAL, fetch_date=datetime(2026, 5, 1),
                doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
            )
        )
        session.commit()
        harness["commits"].clear()

        def national_parser(session, doc, settings):
            return {"created": 1398, "updated": 2, "removed": 329,
                    "skipped_unchanged": False, "fresh_extraction_ids": []}

        county = __import__("seeding.extractors", fromlist=["get_parser"]).get_parser

        monkeypatch.setattr(
            "seeding.extractors.get_parser",
            lambda pid: national_parser if pid == "oag_blue_book" else county(pid),
        )
        return harness

    def test_a_re_extracted_national_book_is_committed_after_the_county_pass(
        self, national
    ):
        _run(national["session"], budget=10_000)
        assert national["fetched"][-1] == NATIONAL
        assert national["commits"][-1] == len(national["fetched"])

    def test_an_unchanged_national_book_is_not_a_reason_to_commit(
        self, national, monkeypatch
    ):
        """POSITIVE CONTROL: a skip did no work, so there is nothing to bank."""
        county = __import__("seeding.extractors", fromlist=["get_parser"]).get_parser("oag_county_audit")
        monkeypatch.setattr(
            "seeding.extractors.get_parser",
            lambda pid: (lambda s, d, st: {"created": 0, "skipped_unchanged": True})
            if pid == "oag_blue_book" else county,
        )
        _run(national["session"], budget=10_000)
        assert national["fetched"][-1] == NATIONAL
        assert len(national["fetched"]) not in national["commits"]

"""The audits loader must not ask the database once per extraction.

WHAT WAS WRONG
--------------
``load_blue_book_extractions`` memoised its entity and period lookups —
deliberately, with a comment saying why: "Measured at 221 ms per round-trip
to the production database". It left the third lookup, ``existing``, as a
SELECT per extraction. That one is the one that runs on EVERY row, because
the other two are answered from cache after the first hit.

OBSERVED on three nightlies, from the gap between the extractor's "Document
NNNN already extracted at md5 … (N rows) — skipping" and the "publishable
backfill" line that follows it, with NOTHING logged in between:

    run 35048000013   813 →  84.0s   986 →  99.2s   512 → 54.0s
    run 35174426953   813 → 123.6s   986 → 140.8s   512 → 76.9s
    run 35299414702   813 →  85.7s   986 → 100.6s   512 → 54.8s

Least squares within each run: 96, 137 and 97 ms per extraction, intercepts
of 5.2-8.2s, R² of 0.999, 0.989 and 0.998. Cost linear in the row COUNT is
the signature of one round trip per row; the backfill is the intercept, and
at ~6s x 3 calls it is not what makes this domain 434s long.

2,311 extractions across the three documents. ``0 created, 0 updated`` on
every one of those nights. 222-317s a night spent asking 2,311 separate
questions whose answer had not changed since the night before.

WHAT THIS TEST PINS
-------------------
The number of SELECT statements against ``audits``, which is the thing that
costs a round trip. Seconds are not assertable here — this runs on local
SQLite, where a round trip is microseconds and the defect is invisible in
wall-clock. The COUNT is the honest local measure, and the log regression
above is what converts it into seconds on production.

*Seen to fail against the pre-fix loader: 40 extractions issued 41 SELECTs
against audits, against the 2 this asserts.*
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Extraction,
    Severity,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.extractors.oag_blue_book import EXTRACTOR_ID
from seeding.types import DomainRunContext
from sqlalchemy import event
from unittest.mock import patch

#: Big enough that one-per-row is unmistakable, small enough to stay quick.
#: Production's three documents carry 813, 986 and 512.
_N = 40


@pytest.fixture()
def doc(db_session, seed_country):
    d = SourceDocument(
        id=2392,
        country_id=seed_country.id,
        publisher="Office of the Auditor-General",
        title="AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf",
        url=(
            "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
            "AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
        ),
        md5="7e6a6850102a3cadcba38e1f7af9cae3",
        fetch_date=datetime(2026, 8, 29, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(d)
    db_session.commit()
    return d


def _extractions(db_session, doc, n=_N):
    for i in range(n):
        db_session.add(
            Extraction(
                source_document_id=doc.id,
                page_number=14 + i,
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                extracted_json={
                    "schema": "oag_blue_book/v1",
                    "vote": 1071,
                    "entity_name": "The National Treasury",
                    "fiscal_year": "2024/2025",
                    "paragraph_no": i,
                    "finding_text": f"Finding {i}: Kshs.20,811,926,257.",
                    "pdf_page": 14 + i,
                    "subreport": "REPORT ON THE FINANCIAL STATEMENTS",
                    "severity": "INFO",
                    "amounts": [20_811_926_257.0],
                    "extraction_method": "pdfplumber",
                },
            )
        )
    db_session.commit()


class _AuditSelectCounter:
    """Counts SELECTs against ``audits`` — one network round trip each.

    Two buckets, because they are two different costs:

    * ``batched`` — the chunked ``extraction_id IN (...)`` snapshot. One per
      500 extractions.
    * ``single`` — a per-row ``extraction_id = ?``. Before the fix, one per
      extraction unconditionally. After it, one only where the snapshot says
      no audit exists, which confirms the absence before inserting: zero on
      the steady-state nightly (everything is a hit), one per genuinely-new
      finding on a night that is writing anyway.
    * ``other`` — everything else the loader triggers against ``audits``,
      which today is the publication gate's four ``count()`` statements.
      Fixed per call, not per row: the intercept in the log regression, not
      the slope.
    """

    def __init__(self, session):
        self.bind = session.get_bind()
        self.batched: list[str] = []
        self.single: list[str] = []
        self.other: list[str] = []

    def _on_exec(self, conn, cursor, statement, params, ctx, many):
        flat = " ".join(statement.split()).lower()
        if not (flat.startswith("select") and "from audits" in flat):
            return
        if "audits.extraction_id in (" in flat:
            self.batched.append(flat)
        elif "audits.extraction_id" in flat:
            self.single.append(flat)
        else:
            self.other.append(flat)

    @property
    def lookups(self) -> list:
        return self.batched + self.single

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on_exec)
        return self

    def __exit__(self, *exc):
        event.remove(self.bind, "before_cursor_execute", self._on_exec)
        return False

    @property
    def count(self) -> int:
        return len(self.lookups)

    @property
    def total(self) -> int:
        return len(self.lookups) + len(self.other)


@pytest.fixture()
def settings():
    return SeedingSettings()


@pytest.fixture()
def context():
    return DomainRunContext(since=None, dry_run=False)


class TestTheLoaderBatchesItsExistenceCheck:
    def test_a_first_load_pays_only_for_rows_it_actually_creates(
        self, db_session, doc, settings, context
    ):
        """A night that writes still confirms each absence before inserting.

        That is the deliberate half of the trade. The snapshot is taken once
        and the loop runs for 55-141s per document, so an insert cannot rest
        on a read that old — see
        test_a_row_landing_after_the_snapshot_is_not_duplicated. What this
        pins is that the confirming SELECT is per NEW row, not per row: one
        batched statement plus one per creation, never one per extraction
        regardless.
        """
        _extractions(db_session, doc)

        with _AuditSelectCounter(db_session) as counted:
            stats = load_blue_book_extractions(db_session, doc, settings, context)

        assert stats.created == _N, "the fixture must actually load rows"
        assert len(counted.batched) == 1, "the snapshot should be one statement"
        assert len(counted.single) == stats.created, (
            f"{len(counted.single)} confirming SELECTs for {stats.created} "
            "created rows — it should be exactly one each"
        )

    def test_the_steady_state_rerun_is_the_expensive_one(
        self, db_session, doc, settings, context
    ):
        """The shape the nightly is actually in: everything already loaded.

        ``0 created, 0 updated`` was the result on every night in the log,
        and it still cost 222-317s.
        """
        _extractions(db_session, doc)
        load_blue_book_extractions(db_session, doc, settings, context)
        db_session.commit()

        with _AuditSelectCounter(db_session) as counted:
            stats = load_blue_book_extractions(db_session, doc, settings, context)

        assert stats.created == 0 and stats.updated == 0, (
            "a re-run over unchanged extractions must be a no-op"
        )
        assert counted.count <= 2, (
            f"a no-op re-run over {_N} extractions issued {counted.count} "
            "existence-check SELECTs against audits"
        )

    def test_the_fixed_cost_per_call_is_small_and_bounded(
        self, db_session, doc, settings, context
    ):
        """The other SELECTs are per CALL, not per row — the intercept.

        Pins the claim this change rests on: the publication gate's
        statements do not grow with the extraction count, so the three
        backfills a night are not what makes the audits domain 434s long.
        """
        _extractions(db_session, doc, n=4)
        with _AuditSelectCounter(db_session) as small:
            load_blue_book_extractions(db_session, doc, settings, context)
        db_session.commit()

        _extractions(db_session, doc, n=_N)
        with _AuditSelectCounter(db_session) as large:
            load_blue_book_extractions(db_session, doc, settings, context)

        assert len(small.other) == len(large.other), (
            f"the per-call cost moved with the row count: {len(small.other)} "
            f"statements for 4 extractions, {len(large.other)} for {_N + 4}"
        )

    def test_the_batch_scales_by_chunk_not_by_row(
        self, db_session, doc, settings, context
    ):
        """Chunking is bounded by _LOOKUP_CHUNK, not by extraction count."""
        from seeding.domains.audits import loader

        _extractions(db_session, doc)
        with _AuditSelectCounter(db_session) as counted:
            load_blue_book_extractions(db_session, doc, settings, context)

        expected = -(-_N // loader._LOOKUP_CHUNK)  # ceil
        assert len(counted.batched) == expected, (
            f"expected {expected} chunked SELECT(s) for {_N} extractions at "
            f"chunk {loader._LOOKUP_CHUNK}, got {len(counted.batched)}"
        )

    def test_the_chunk_stays_under_sqlite_parameter_ceiling(self):
        """SQLite's default SQLITE_MAX_VARIABLE_NUMBER is 999.

        The tests run on SQLite; production runs on Postgres, which would
        take all 2,311 in one statement. A chunk above the SQLite ceiling
        would pass on Postgres and fail only here — or, worse, only under an
        older SQLite than the one on this machine.
        """
        from seeding.domains.audits import loader

        assert 0 < loader._LOOKUP_CHUNK <= 999


class TestTheBatchStillFindsWhatTheRowLookupFound:
    """A faster wrong answer is not the goal."""

    def test_an_existing_row_is_updated_not_duplicated(
        self, db_session, doc, settings, context
    ):
        _extractions(db_session, doc, n=3)
        load_blue_book_extractions(db_session, doc, settings, context)
        db_session.commit()
        assert db_session.query(Audit).count() == 3

        # Change one extraction's text; the loader must UPDATE that audit row.
        ext = db_session.query(Extraction).order_by(Extraction.id).first()
        payload = dict(ext.extracted_json)
        payload["finding_text"] = "Revised finding text for Kshs.1,000."
        ext.extracted_json = payload
        db_session.commit()

        stats = load_blue_book_extractions(db_session, doc, settings, context)
        assert db_session.query(Audit).count() == 3, "no duplicate rows"
        assert stats.created == 0 and stats.updated == 1
        audit = (
            db_session.query(Audit).filter(Audit.extraction_id == ext.id).one()
        )
        assert audit.finding_text == "Revised finding text for Kshs.1,000."

    def test_a_row_landing_after_the_snapshot_is_not_duplicated(
        self, db_session, doc, settings, context
    ):
        """The snapshot is taken once; the loop then runs for 55-141s per
        document on production. A row landing inside that window is invisible
        to the snapshot, and a plain dict read would insert a SECOND audit
        for the same extraction — silent tonight, and a hard failure the next
        night when _audits_by_extraction_id raises on the pair.

        ``audits.extraction_id`` is indexed but not unique, so nothing at the
        schema level stops it.
        """
        from seeding.domains.audits import loader as loader_mod

        # One real load first, so an entity and a period exist for the
        # "other process" to attach its row to (audits.entity_id is NOT NULL).
        _extractions(db_session, doc, n=2)
        load_blue_book_extractions(db_session, doc, settings, context)
        db_session.commit()
        template = db_session.query(Audit).first()

        # Now a genuinely new extraction, which the loop will want to insert.
        _extractions(db_session, doc, n=1)
        newest = db_session.query(Extraction).order_by(Extraction.id.desc()).first()

        real_batch = loader_mod._audits_by_extraction_id

        def batch_then_write(session, extraction_ids):
            snapshot = real_batch(session, extraction_ids)
            # Another writer lands an audit for that extraction after the
            # snapshot was taken and before the loop reaches it.
            session.add(
                Audit(
                    entity_id=template.entity_id,
                    period_id=template.period_id,
                    finding_text="written by another process mid-loop",
                    severity=Severity.INFO,
                    source_document_id=doc.id,
                    extraction_id=newest.id,
                    page_ref="p.1",
                    status="published_report",
                )
            )
            session.flush()
            return snapshot

        with patch.object(
            loader_mod, "_audits_by_extraction_id", batch_then_write
        ):
            load_blue_book_extractions(db_session, doc, settings, context)

        per_extraction = {}
        for audit in db_session.query(Audit).all():
            per_extraction.setdefault(audit.extraction_id, []).append(audit.id)
        dupes = {k: v for k, v in per_extraction.items() if len(v) > 1}
        assert not dupes, (
            f"a row that landed after the snapshot was duplicated: {dupes}"
        )

    def test_a_duplicate_audit_for_one_extraction_still_raises(
        self, db_session, doc, settings, context
    ):
        """``audits.extraction_id`` is indexed but NOT unique, so the
        one-extraction-one-row invariant is upheld by this code path alone.

        The per-row lookup used ``scalar_one_or_none()`` and raised
        ``MultipleResultsFound``. A plain dict build would have kept
        whichever row came back last and carried on — trading a loud failure
        for a silent arbitrary choice, which is not a speed-up.
        """
        from sqlalchemy.exc import MultipleResultsFound

        _extractions(db_session, doc, n=2)
        load_blue_book_extractions(db_session, doc, settings, context)
        db_session.commit()

        original = db_session.query(Audit).order_by(Audit.id).first()
        db_session.add(
            Audit(
                entity_id=original.entity_id,
                period_id=original.period_id,
                finding_text="a second row claiming the same extraction",
                severity=original.severity,
                source_document_id=original.source_document_id,
                extraction_id=original.extraction_id,
                page_ref=original.page_ref,
                status="published_report",
            )
        )
        db_session.commit()

        with pytest.raises(MultipleResultsFound):
            load_blue_book_extractions(db_session, doc, settings, context)

    def test_rows_belonging_to_another_document_are_not_picked_up(
        self, db_session, doc, seed_country, settings, context
    ):
        """The batch is keyed on THIS document's extraction ids."""
        other = SourceDocument(
            id=2395,
            country_id=seed_country.id,
            publisher="Office of the Auditor-General",
            title="COUNTY-EXECUTIVES-2020-2021.pdf",
            url="https://www.oagkenya.go.ke/wp-content/uploads/2023/02/ce.pdf",
            md5="f82bd20b45bb54ca6857ddd93a6a16ec",
            fetch_date=datetime(2026, 8, 29, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add(other)
        db_session.commit()

        _extractions(db_session, doc, n=2)
        _extractions(db_session, other, n=2)
        load_blue_book_extractions(db_session, doc, settings, context)
        load_blue_book_extractions(db_session, other, settings, context)
        db_session.commit()

        assert db_session.query(Audit).count() == 4
        ids = {a.extraction_id for a in db_session.query(Audit).all()}
        assert len(ids) == 4, "each audit row keys off its own extraction"


class TestTheBackfillSaysHowLongItTook:
    def test_the_log_line_carries_a_duration(
        self, db_session, doc, settings, context, caplog
    ):
        """It is emitted three times a night and carried no timing at all,
        which is why establishing its real cost needed a regression over log
        gaps instead of a number anyone could read."""
        _extractions(db_session, doc, n=2)
        with caplog.at_level("INFO", logger="services.publication_gate"):
            load_blue_book_extractions(db_session, doc, settings, context)

        lines = [
            r.getMessage()
            for r in caplog.records
            if "publishable backfill" in r.getMessage()
        ]
        assert lines, "the backfill must still announce itself"
        assert any(
            line.rstrip().endswith("s") and " in " in line for line in lines
        ), f"no duration on the backfill log line: {lines}"

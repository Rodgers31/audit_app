"""The publishable backfill must not rewrite rows that already hold the verdict.

``backfill_publishable_audits`` is called once per loaded document by
``seeding/domains/audits/loader.py``. Each call issued three UNCONDITIONAL
``UPDATE``s over the whole ``audits`` table, so every call rewrote every row to
the value it already had.

Measured on production (2026-09-06):

* 2338 audit rows, 2312 matching the criterion, and **0** of them needing any
  change — every write was a no-op;
* the ``EXPLAIN (ANALYZE)`` for the UPDATE's own WHERE clause runs in **9 ms**,
  so the cost was not the scan;
* ``audits`` is a 16 MB table with **9 indexes**, so each pointless row rewrite
  also rewrote nine index entries;
* the nightly's audits domain therefore spent **120s + 146s + 80s = 346s** in
  three backfills that each logged the identical result, out of a 1320s global
  seed budget. The run ran out of budget in ``pending_bills`` and dropped four
  domains.

The verdict written must not change — only the number of rows written to.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from datetime import datetime, timezone

from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)
from services.publication_gate import backfill_publishable_audits


@contextmanager
def _rows_written(session):
    """Count rows actually touched by UPDATE statements on this connection."""
    written = []

    def _after(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE"):
            written.append(max(cursor.rowcount, 0))

    bind = session.get_bind()
    event.listen(bind, "after_cursor_execute", _after)
    try:
        yield written
    finally:
        event.remove(bind, "after_cursor_execute", _after)


@pytest.fixture()
def populated(db_session, seed_country):
    """One publishable row, one withheld for no URL, one for (cid: junk."""

    def _doc(title, url):
        return SourceDocument(
            country_id=seed_country.id,
            publisher="Office of the Auditor General",
            title=title,
            url=url,
            fetch_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )

    entity = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Health",
        slug="ministry-of-health-backfill-test",
    )
    with_url = _doc("Readable", "https://example.org/a.pdf")
    without_url = _doc("No URL", None)
    db_session.add_all([entity, with_url, without_url])
    db_session.flush()

    period = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add(period)
    db_session.flush()

    def _audit(text, sev, doc):
        return Audit(
            entity_id=entity.id,
            period_id=period.id,
            finding_text=text,
            severity=sev,
            source_document_id=doc.id,
        )

    db_session.add_all(
        [
            _audit("A clean finding", Severity.WARNING, with_url),
            _audit("Orphaned finding", Severity.WARNING, without_url),
            _audit("(cid:31)(cid:30) glyph junk", Severity.CRITICAL, with_url),
        ]
    )
    db_session.commit()
    return db_session


class TestASettledTableIsNotRewritten:
    def test_the_second_backfill_writes_nothing(self, populated):
        """The bug: every call rewrote every row to the value it already held."""
        backfill_publishable_audits(populated)
        populated.commit()

        with _rows_written(populated) as written:
            backfill_publishable_audits(populated)

        assert sum(written) == 0, (
            "nothing changed between the two calls, so the second must write "
            f"no rows; it wrote {sum(written)} across {len(written)} UPDATE(s)"
        )

    def test_a_genuine_change_is_still_written(self, populated):
        """The guard must not make the backfill stop converging."""
        backfill_publishable_audits(populated)
        populated.commit()

        clean = (
            populated.query(Audit)
            .filter(Audit.finding_text == "A clean finding")
            .one()
        )
        clean.publishable = False
        clean.quarantine_reason = "wrong"
        populated.commit()

        with _rows_written(populated) as written:
            backfill_publishable_audits(populated)
        assert sum(written) == 1, written

        populated.expire_all()
        assert clean.publishable is True
        assert clean.quarantine_reason is None


class TestTheVerdictIsUnchanged:
    """Same answer as before, on every row and in the returned stats."""

    def test_stats_and_columns_match_the_old_contract(self, populated):
        stats = backfill_publishable_audits(populated)
        assert stats == {"published": 1, "withheld": 2}

        rows = {
            a.finding_text[:6]: (a.publishable, a.quarantine_reason)
            for a in populated.query(Audit).all()
        }
        assert rows["A clea"] == (True, None)
        assert rows["Orphan"] == (False, "source_document_has_no_url")
        assert rows["(cid:3"] == (False, "finding_text_unreadable_cid")

    def test_stats_are_totals_not_deltas(self, populated):
        """Repeat calls report the table's state, not what this call wrote."""
        first = backfill_publishable_audits(populated)
        populated.commit()
        assert backfill_publishable_audits(populated) == first

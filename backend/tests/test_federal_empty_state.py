"""/audits/federal must explain an empty panel, not just render one.

Stage 2 Task 1b: when the publication gate withholds every federal finding,
the homepage panel showed four em-dashes, an empty ministries list and a
donut reading "1 findings" over a 0/0/0 severity breakdown. The API side of
the fix: an empty findings list carries a machine-readable reason and the
next expected publication window (from the Layer-1 source registry), so the
frontend can say what it is waiting for instead of rendering a blank.

The window comes from seeding.source_registry.PUBLICATION_SCHEDULE — the
OAG cadence (annual, 6-9 months after FY end, reports Dec-Apr) — never a
hand-written string in the component.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
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


@pytest.fixture()
def withheld_federal_fixture(db_session, seed_country):
    """A ministry finding whose source document has no URL → withheld."""
    unopenable = SourceDocument(
        id=1836,
        country_id=seed_country.id,
        publisher="Office of the Auditor General",
        title="Report of the Auditor-General on the National Government",
        url=None,
        fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    ministry = Entity(
        id=400,
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Health",
        slug="ministry-of-health-empty-state",
    )
    period = FiscalPeriod(
        id=400,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([unopenable, ministry, period])
    db_session.flush()
    audit = Audit(
        entity_id=ministry.id,
        period_id=period.id,
        finding_text="Irregular procurement of KES 12.3 billion",
        severity=Severity.WARNING,
        source_document_id=unopenable.id,
    )
    db_session.add(audit)
    db_session.commit()
    return audit


class TestFederalEmptyStateContract:
    def test_empty_findings_carry_reason_and_next_expected(
        self, client, withheld_federal_fixture
    ):
        data = client.get("/api/v1/audits/federal").json()

        assert data["total_findings"] == 0
        assert data["by_severity"] == {}
        assert data["withheld_findings"] == 1

        # The machine-readable why.
        assert data["findings_reason"] == "awaiting_sourced_data"

        # The machine-readable when: OAG cadence from the source registry.
        nxt = data["next_expected"]
        assert nxt is not None
        assert nxt["dataset"] == "oag_national_audits"
        assert nxt["cadence"] == "annual"
        assert nxt["lag"] == "6-9"
        assert nxt["window_start"] is not None
        assert nxt["window_end"] is not None

    def test_no_findings_at_all_reason(self, client, seed_country):
        data = client.get("/api/v1/audits/federal").json()
        assert data["total_findings"] == 0
        assert data["findings_reason"] == "no_findings_recorded"
        assert data["next_expected"] is not None

    def test_published_findings_have_no_reason(self, client, db_session, seed_country):
        openable = SourceDocument(
            id=2392,
            country_id=seed_country.id,
            publisher="Office of the Auditor-General",
            title="Auditor-General's report on national government 2024/25",
            url=(
                "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
                "AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
            ),
            fetch_date=datetime(2026, 7, 19, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        ministry = Entity(
            id=401,
            country_id=seed_country.id,
            type=EntityType.MINISTRY,
            canonical_name="The National Treasury",
            slug="the-national-treasury-empty-state",
        )
        period = FiscalPeriod(
            id=401,
            country_id=seed_country.id,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
        db_session.add_all([openable, ministry, period])
        db_session.flush()
        db_session.add(
            Audit(
                entity_id=ministry.id,
                period_id=period.id,
                finding_text="Pending accounts payable of Kshs.20,811,926,257",
                severity=Severity.WARNING,
                source_document_id=openable.id,
            )
        )
        db_session.commit()

        data = client.get("/api/v1/audits/federal").json()
        assert data["total_findings"] == 1
        assert data["by_severity"] == {"WARNING": 1}
        assert data["findings_reason"] is None
        assert data["next_expected"] is None


class TestNextExpectedWindow:
    """The registry's window arithmetic, pinned at concrete dates."""

    def test_outside_window_points_at_december(self):
        from seeding.source_registry import next_expected_window

        nxt = next_expected_window("oag_national_audits", date(2026, 8, 29))
        assert nxt["window_start"] == "2026-12-01"
        assert nxt["window_end"] == "2027-04-30"
        assert nxt["in_window"] is False

    def test_inside_window_tail_spans_year_boundary(self):
        from seeding.source_registry import next_expected_window

        nxt = next_expected_window("oag_national_audits", date(2026, 2, 1))
        assert nxt["window_start"] == "2025-12-01"
        assert nxt["window_end"] == "2026-04-30"
        assert nxt["in_window"] is True

    def test_window_head_in_december(self):
        from seeding.source_registry import next_expected_window

        nxt = next_expected_window("oag_national_audits", date(2026, 12, 15))
        assert nxt["window_start"] == "2026-12-01"
        assert nxt["window_end"] == "2027-04-30"
        assert nxt["in_window"] is True

    def test_quarterly_check_dates(self):
        from seeding.source_registry import next_expected_window

        nxt = next_expected_window("cob_qbirr", date(2026, 8, 29))
        assert nxt["window_start"] == "2026-11-15"
        assert nxt["cadence"] == "quarterly"

    def test_unknown_dataset_is_none(self):
        from seeding.source_registry import next_expected_window

        assert next_expected_window("no_such_dataset", date(2026, 1, 1)) is None

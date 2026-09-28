"""Issue #347: a count decrease needs row-level supersession evidence."""

from datetime import datetime, timedelta, timezone

from models import EconomicIndicator, IngestionJob, IngestionStatus
from seeding import staleness
from seeding.domains.economic_indicators import fetcher, writer


NOW = datetime(2026, 9, 28, 3, tzinfo=timezone.utc)
LABEL = "Inflation Rate records"


def _row(day, value=4.0, *, meta=None):
    return EconomicIndicator(
        indicator_type="inflation_rate",
        indicator_date=datetime.fromisoformat(day),
        value=value,
        unit="percent",
        meta=meta or {},
    )


def _finding(db_session, count):
    return next(
        f for f in staleness.check_row_count_drop(db_session, {LABEL: count}, NOW)
        if f.label == LABEL
    )


def test_missing_official_year_is_not_a_supersession(db_session, seed_country):
    official = _row(
        "2023-12-31",
        meta={"publisher": "World Bank", "measure": "CPI inflation, annual average"},
    )
    db_session.add(official)
    db_session.flush()

    removed, errors = writer.remove_superseded_rows(
        db_session,
        {"inflation_rate": {"2022-12-31", "2024-12-31"}},
    )

    assert removed == []
    assert errors == []
    db_session.flush()
    assert db_session.get(EconomicIndicator, official.id) is not None


def test_fixture_year_end_cannot_overwrite_existing_source_on_partial_coverage():
    fixture = {"indicator_type": "inflation_rate", "date": "2023-12-31", "value": 5.0}
    live = [
        {"indicator_type": "inflation_rate", "date": "2022-12-31", "value": 6.0},
        {"indicator_type": "inflation_rate", "date": "2024-12-31", "value": 4.0},
    ]

    merged = fetcher._merge_indicators([fixture], live)

    # The writer retains an existing sourced 2023 row; the merge must not
    # pass a fixture 2023 row that could overwrite it on the same key.
    assert fixture not in merged


def test_missing_cbk_month_end_is_not_a_supersession(db_session, seed_country):
    row = EconomicIndicator(
        indicator_type="inflation_rate_12m",
        indicator_date=datetime(2026, 6, 30),
        value=6.0,
        unit="percent",
        meta={"publisher": "Central Bank of Kenya"},
    )
    db_session.add(row)
    db_session.flush()

    removed, errors = writer.remove_superseded_rows(
        db_session, {"inflation_rate_12m": {"2026-05-31", "2026-07-31"}}
    )

    assert (removed, errors) == ([], [])
    db_session.flush()
    assert db_session.get(EconomicIndicator, row.id) is not None


def test_malformed_coverage_refuses_the_whole_sweep(db_session, seed_country):
    db_session.add(_row("2024-06-30"))
    db_session.flush()

    removed, errors = writer.remove_superseded_rows(
        db_session,
        {"inflation_rate": {"2023-12-31", "2025-12-31", "not-a-date"}},
    )

    assert removed == []
    assert errors and "malformed" in errors[0]
    db_session.flush()
    assert db_session.query(EconomicIndicator).count() == 1


def _seed_baseline(db_session):
    rows = [_row(f"{year}-12-31") for year in range(2015, 2026)]
    rows += [
        _row("2022-06-30", 4.6, meta={"bootstrap": True}),
        _row("2023-01-31", 3.3),
        _row("2024-06-30", 4.6, meta={"bootstrap": True}),
        _row("2025-01-31", 3.3),
    ]
    db_session.add_all(rows)
    db_session.flush()
    staleness.record_row_census(db_session, {LABEL: 15}, NOW - timedelta(days=1))
    return rows


def _receipts(rows):
    return [
        {
            "id": row.id,
            "indicator_type": row.indicator_type,
            "date": row.indicator_date.date().isoformat(),
            "value": float(row.value),
            "stored_value": str(row.value),
            "entity_id": row.entity_id,
            "source_document_id": row.source_document_id,
        }
        for row in rows
    ]


def _job(db_session, receipts):
    db_session.add(
        IngestionJob(
            domain="economic_indicators",
            status=IngestionStatus.COMPLETED,
            started_at=(NOW - timedelta(hours=1)).replace(tzinfo=None),
            dry_run=False,
            errors=[],
            meta={
                "superseded_rows_removed": receipts,
                "supersession_coverage": {
                    "inflation_rate": [f"{year}-12-31" for year in range(2015, 2026)]
                },
            },
        )
    )
    db_session.flush()


def test_exact_authorized_supersession_explains_count_drop(db_session, seed_country):
    rows = _seed_baseline(db_session)
    receipts = _receipts(rows[-4:])
    removed, errors = writer.remove_superseded_rows(
        db_session, {"inflation_rate": {f"{year}-12-31" for year in range(2015, 2026)}}
    )
    assert len(removed) == 4 and errors == []
    db_session.flush()
    _job(db_session, receipts)

    finding = _finding(db_session, 11)
    assert finding.level == staleness.OK
    assert "4" in finding.message and "supersession" in finding.message


def test_unexplained_loss_still_fails_with_some_valid_receipts(db_session, seed_country):
    rows = _seed_baseline(db_session)
    receipts = _receipts(rows[-2:])
    for row in rows[-4:]:
        db_session.delete(row)
    db_session.flush()
    _job(db_session, receipts)

    finding = _finding(db_session, 11)
    assert finding.level == staleness.FAIL


def test_wrong_source_identity_cannot_authorize_a_loss(db_session, seed_country):
    rows = _seed_baseline(db_session)
    receipts = _receipts(rows[-4:])
    receipts[0]["source_document_id"] = 9999
    for row in rows[-4:]:
        db_session.delete(row)
    db_session.flush()
    _job(db_session, receipts)

    assert _finding(db_session, 11).level == staleness.FAIL


def test_legacy_count_only_baseline_does_not_get_automatic_exemption(
    db_session, seed_country
):
    rows = _seed_baseline(db_session)
    baseline = (
        db_session.query(IngestionJob)
        .filter(IngestionJob.domain == staleness.ROW_CENSUS_DOMAIN)
        .one()
    )
    baseline.meta = {"row_counts": {LABEL: 15}}
    db_session.flush()
    receipts = _receipts(rows[-4:])
    for row in rows[-4:]:
        db_session.delete(row)
    db_session.flush()
    _job(db_session, receipts)

    assert _finding(db_session, 11).level == staleness.FAIL

"""The data-health panel must be able to go red (credibility audit F17).

/sources renders GET /provenance/health under the caption "Green means the
table is fully populated from its source". Every status behind it was a bare
row-count floor with no time term:

    status="healthy" if poverty_count >= 1 else "empty"      # one row = green
    status="healthy" if debt_tl_count >= 5 ...               # five rows = green

So a table frozen for a year read exactly like one updated last night, and all
ten datasets reported "Healthy" while /sources showed sources last fetched
"6 months ago" and "1 years ago" beside them. A check that cannot fail is not a
check.

These pin the time term in both directions: a table that has stopped moving
goes stale, and a table that is moving stays current. The second matters as
much as the first — a staleness rule that fires on everything is just as
useless as one that fires on nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from models import PovertyIndex
from routers.data_provenance import _STALE_AFTER_DAYS, _apply_freshness, TableHealth


def _health(status="healthy", table="poverty_indices"):
    return TableHealth(
        table=table, label="Poverty Data", row_count=1, source="World Bank", status=status
    )


@pytest.fixture()
def poverty_row(db_session):
    def _make(age_days: int):
        db_session.query(PovertyIndex).delete()
        row = PovertyIndex(year=2022, poverty_headcount_rate=39.8)
        db_session.add(row)
        db_session.commit()
        stamp = datetime.now(timezone.utc) - timedelta(days=age_days)
        for col in ("updated_at", "created_at"):
            if hasattr(row, col):
                setattr(row, col, stamp.replace(tzinfo=None))
        db_session.commit()
        return row

    return _make


def test_a_table_that_has_stopped_moving_goes_stale(db_session, poverty_row):
    limit = _STALE_AFTER_DAYS["poverty_indices"]
    poverty_row(limit + 30)
    result = _apply_freshness(_health(), db_session, PovertyIndex)
    assert result.status == "stale"
    assert result.age_days is not None and result.age_days > limit
    assert result.stale_after_days == limit
    assert "no row has changed" in (result.notes or "")


def test_a_table_that_is_moving_stays_current(db_session, poverty_row):
    poverty_row(1)
    result = _apply_freshness(_health(), db_session, PovertyIndex)
    assert result.status == "healthy", (
        "a freshness rule that fires on a table updated yesterday is as useless "
        "as one that never fires"
    )
    assert result.age_days == 1


def test_staleness_never_upgrades_a_failing_row(db_session, poverty_row):
    """A young empty table is still empty — freshness only downgrades."""
    poverty_row(1)
    result = _apply_freshness(_health(status="empty"), db_session, PovertyIndex)
    assert result.status == "empty"


def test_the_one_row_that_used_to_be_enough(db_session, poverty_row):
    """`poverty_count >= 1` was the whole check. One stale row now shows stale
    rather than green, which is the specific case the audit named."""
    poverty_row(_STALE_AFTER_DAYS["poverty_indices"] + 1)
    result = _apply_freshness(_health(), db_session, PovertyIndex)
    assert result.row_count == 1
    assert result.status == "stale"


def test_every_health_table_declares_a_staleness_budget(client):
    """A table with no entry in _STALE_AFTER_DAYS silently keeps the old
    can't-fail behaviour, so the omission has to be caught here."""
    resp = client.get("/api/v1/provenance/health")
    assert resp.status_code == 200, resp.text
    for row in resp.json()["tables"]:
        assert row["table"] in _STALE_AFTER_DAYS, (
            f"{row['table']} has no staleness budget — its status can only ever "
            "report emptiness"
        )

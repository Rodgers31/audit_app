"""Behavioral controls for source-scoped aging, never invented exact-day bands."""
import pytest


def test_summary_explains_unsupported_populations_without_inventing_bands(db_session):
    from main import _pending_bills_summary_from_loans

    result = _pending_bills_summary_from_loans(db_session)
    assert result["aging_buckets"] is None
    assert (
        result["aging_observations"]["national"]["absent_reason"]
        == "no_source_bound_aging_observation"
    )
    assert result["aging_observations"]["county_assembly"]["buckets"] is None
    assert result["aging_observations"]["combined"]["buckets"] is None

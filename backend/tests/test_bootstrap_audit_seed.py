"""Tests for the audit seed-layer fixes in bootstrap.py (audit §2.6).

The DB seeder previously (a) parsed trillions to 0 — ``_parse_kes_amount``
had no ``T`` branch, so "KES 1.2T" fell through to 0 and undercounted the
audit DB; and (b) promoted OAG "high" findings to CRITICAL, inflating the
"critical findings" count. These tests pin the fixes.
"""

from __future__ import annotations

import pytest

from bootstrap import _map_severity, _parse_kes_amount
from models import Severity


@pytest.mark.parametrize(
    "value,expected",
    [
        ("KES 1.2T", 1_200_000_000_000.0),
        ("1.2T", 1_200_000_000_000.0),
        ("KES 2.5B", 2_500_000_000.0),
        ("500M", 500_000_000.0),
        ("5K", 5_000.0),
        ("1,234.5B", 1_234_500_000_000.0),
        (0, 0.0),
        (None, 0.0),
        ("garbage", 0.0),
    ],
)
def test_parse_kes_amount_handles_T(value, expected):
    assert _parse_kes_amount(value) == expected


def test_high_severity_not_promoted_to_critical():
    # OAG "high" must NOT become CRITICAL (that inflated the critical-findings
    # count). The coarse enum buckets it as WARNING; the original wording is
    # preserved per-finding in provenance (severity_label).
    assert _map_severity("high") == Severity.WARNING
    assert _map_severity("HIGH") == Severity.WARNING


def test_real_critical_still_critical():
    assert _map_severity("critical") == Severity.CRITICAL


def test_severity_other_levels():
    assert _map_severity("low") == Severity.INFO
    assert _map_severity("medium") == Severity.WARNING
    assert _map_severity("") == Severity.WARNING
    assert _map_severity(None) == Severity.WARNING

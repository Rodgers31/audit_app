"""Tests for the Amount-Questioned fix (audit §3.4 — Critical).

The /audits/federal headline summed every finding's amount (incl.
debt-service stock + asset valuations) into "Amount Questioned" = ~3.3T.
The fix uses the OAG report's own authoritative questioned total instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from main import _parse_kes_amount_str

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "value,expected",
    [
        ("KES 981.3B", 981_300_000_000.0),
        ("981.3B", 981_300_000_000.0),
        ("1.2T", 1_200_000_000_000.0),
        ("500M", 500_000_000.0),
        ("5K", 5_000.0),
        ("1,234.5B", 1_234_500_000_000.0),
        ("KES 0", 0.0),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_kes_amount_str(value, expected):
    assert _parse_kes_amount_str(value) == expected


def test_federal_headline_uses_authoritative_not_naive_sum():
    src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    # Headline parses the OAG report's own questioned total...
    assert (
        '"total_amount_questioned": _parse_kes_amount_str(' in src
    ), "headline should use the authoritative parsed figure"
    # ...the naive sum is no longer the questioned headline...
    assert '"total_amount_questioned": total_amount,' not in src
    # ...and is exposed honestly for transparency instead.
    assert '"total_amount_in_findings": total_amount,' in src

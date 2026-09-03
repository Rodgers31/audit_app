"""The raw-KES DB-boundary guards must fail closed on hostile numbers.

Found by an adversarial pass: ``isinstance(True, int)`` is True in Python,
so a boolean leaking out of a parser sailed through the ``v < 1e6`` scale
test and became KES 1,000,000,000; NaN passed straight through to the
table. Both now raise at the boundary.
"""

from __future__ import annotations

import pytest
from seeding.domains.debt_timeline.writer import _raw_kes as debt_raw_kes
from seeding.domains.fiscal_summary.writer import _raw_kes as fiscal_raw_kes


@pytest.mark.parametrize("fn", [debt_raw_kes, fiscal_raw_kes])
class TestRawKesBoundary:
    def test_billions_convert(self, fn):
        assert fn(12_500) == 12_500e9

    def test_raw_passes_through(self, fn):
        assert fn(12_500e9) == 12_500e9

    def test_none_stays_none(self, fn):
        assert fn(None) is None

    def test_boolean_rejected(self, fn):
        with pytest.raises(ValueError, match="boolean"):
            fn(True)

    def test_nan_rejected(self, fn):
        with pytest.raises(ValueError, match="non-finite"):
            fn(float("nan"))

    def test_inf_rejected(self, fn):
        with pytest.raises(ValueError, match="non-finite"):
            fn(float("inf"))


def test_negative_debt_rejected():
    with pytest.raises(ValueError, match="negative"):
        debt_raw_kes(-500)

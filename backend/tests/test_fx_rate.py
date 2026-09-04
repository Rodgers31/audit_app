"""Gates on the USD/KES rate used to convert World Bank debt into shillings.

This rate multiplies every external creditor, so a wrong one is wrong on the
whole external book at once and looks like a number somebody checked. It was
a frozen constant (130.0) until 2026-09-04; the official 2024 rate is 134.82,
so the conversion was 3.7% low — about KSh 240bn on a 6.5T external book.

The independent evidence that the live rate is better: coverage against CBK's
separately published external-debt total moved from 91% to 95%. Nothing was
tuned to make that happen — CBK is a different publisher.
"""

from decimal import Decimal

import pytest

from seeding.domains.national_debt import fx
from seeding.domains.national_debt.wb_ids_creditors import Creditor, IdsCreditorError


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class _Client:
    def __init__(self, payload=None, exc=None):
        self._payload, self._exc = payload, exc
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        if self._exc:
            raise self._exc
        return _Resp(self._payload)


def _wb(year, value):
    return [{"page": 1}, [{"date": str(year), "value": value}]]


class TestRateResolution:
    def test_returns_the_rate_for_the_requested_year(self):
        assert fx.usd_kes_rate_for_year(_Client(_wb(2024, 134.822483279332)), 2024) == Decimal(
            "134.822483279332"
        )

    def test_asks_for_that_year_specifically(self):
        """Vintage-matching is the point — a 2024 stock needs the 2024 rate."""
        c = _Client(_wb(2024, 134.8))
        fx.usd_kes_rate_for_year(c, 2024)
        assert "date=2024:2024" in c.calls[0]
        assert fx.FX_SERIES in c.calls[0]


class TestGatesFire:
    def test_returns_none_when_the_year_is_absent(self):
        assert fx.usd_kes_rate_for_year(_Client(_wb(2023, 139.8)), 2024) is None

    def test_returns_none_when_the_value_is_null(self):
        assert fx.usd_kes_rate_for_year(_Client(_wb(2024, None)), 2024) is None

    def test_returns_none_when_the_api_is_unreachable(self):
        assert fx.usd_kes_rate_for_year(_Client(exc=RuntimeError("boom")), 2024) is None

    def test_returns_none_on_a_malformed_payload(self):
        assert fx.usd_kes_rate_for_year(_Client({"unexpected": True}), 2024) is None

    @pytest.mark.parametrize("bad", [Decimal("0.0134"), Decimal("13482"), Decimal("-134")])
    def test_returns_none_on_an_implausible_rate(self, bad):
        """A units error (or a decimal slip) is not a devaluation."""
        assert fx.usd_kes_rate_for_year(_Client(_wb(2024, str(bad))), 2024) is None

    def test_never_falls_back_to_a_constant(self):
        """The defect this replaced. Absence must propagate, not default."""
        for client in (_Client(_wb(2024, None)), _Client(exc=RuntimeError("x"))):
            assert fx.usd_kes_rate_for_year(client, 2024) is None


class TestConversionRefusesWithoutARate:
    def test_creditor_kes_raises_rather_than_guessing(self):
        c = Creditor(
            name="IDA", counterpart_id="907", series="DT.DOD.MLAT.CD",
            debt_category="external_multilateral", usd=1_000_000_000.0,
        )
        with pytest.raises(IdsCreditorError, match="no_usd_kes_rate"):
            _ = c.kes

    def test_creditor_converts_at_the_rate_it_was_given(self):
        c = Creditor(
            name="IDA", counterpart_id="907", series="DT.DOD.MLAT.CD",
            debt_category="external_multilateral", usd=1_000_000_000.0,
            usd_kes_rate=Decimal("134.822483279332"),
        )
        assert c.kes == Decimal("134822483279.332")

    def test_the_old_frozen_rate_is_gone(self):
        import seeding.domains.national_debt.wb_ids as wb_ids
        import seeding.domains.national_debt.wb_ids_creditors as wic

        assert not hasattr(wic, "USD_KES_RATE")
        assert not hasattr(wb_ids, "_USD_KES_RATE")


class TestProvenance:
    def test_names_the_rate_its_year_and_its_basis(self):
        line = fx.rate_provenance(2024, Decimal("134.82"))
        assert "134.82" in line
        assert "2024" in line
        assert "period average" in line  # the basis caveat travels with it

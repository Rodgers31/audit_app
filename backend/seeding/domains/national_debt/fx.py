"""The USD/KES rate used to convert World Bank debt figures into shillings.

WHY THIS EXISTS
---------------
IDS reports Kenya's external debt in USD. Publishing it in shillings needs a
rate, and until now that rate was a constant::

    USD_KES_RATE = Decimal("130.0")   # "conservative average for 2018-2025"

A frozen rate is a stored literal in the most load-bearing place there is: it
multiplies every external creditor. Against the 2024 IDS pull it is out by
3.7% — the official 2024 rate is 134.82 — which is roughly KSh 240 billion on
a 6.5T external book, and it drifts further every year while looking like a
number somebody checked.

WHICH RATE
----------
The World Bank's own ``PA.NUS.FCRF`` (official exchange rate, LCU per US$),
fetched for THE SAME YEAR as the IDS pull it converts. Vintage-matching is the
point: a 2024 debt stock converted at today's spot is not the 2024 stock in
shillings, it is two unrelated observations multiplied together.

    2022  117.87    2023  139.85    2024  134.82    2025  129.30

It is a period AVERAGE, not the 31-December rate a stock strictly wants. That
is stated in the provenance rather than papered over: the end-period rate is
not published in this series, and an average of the right year is much closer
than a constant from no year at all. The coverage gate downstream (IDS total
against CBK's published KES external debt, band 0.60-1.15) is what catches a
rate wrong enough to matter.

NO FALLBACK
-----------
If the rate cannot be resolved this returns ``None`` and the caller
quarantines the pull. It does NOT fall back to a constant. A conversion is a
claim about how many shillings the country owes; making one up is the failure
this module was written to remove, and reintroducing it as a fallback would
put it back exactly where it is hardest to see.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger("seeding.national_debt.fx")

#: World Bank: Official exchange rate (LCU per US$, period average).
FX_SERIES = "PA.NUS.FCRF"

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"

#: KES per USD. Anything outside this is a units error or a bad parse, not a
#: devaluation: the shilling has traded roughly 60-165 to the dollar across
#: the entire period this project covers.
PLAUSIBLE_USD_KES = (Decimal("50"), Decimal("400"))


def _parse(payload: Any, year: int) -> Optional[Decimal]:
    """Pull the value for ``year`` out of a World Bank v2 response."""
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    for row in payload[1] or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("date")) != str(year):
            continue
        value = row.get("value")
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
    return None


def usd_kes_rate_for_year(client, year: int) -> Optional[Decimal]:
    """The official USD/KES rate for ``year``, or ``None`` to quarantine.

    ``None`` on every failure path — unreachable, absent for that year, or
    implausible — because a wrong rate is silently wrong across every row it
    touches.
    """
    url = f"{_WB_BASE}/{FX_SERIES}?format=json&date={year}:{year}&per_page=10"
    try:
        response = client.get(url, raise_for_status=True)
        payload = response.json()
    except Exception as exc:
        logger.warning("USD/KES rate for %s unavailable: %s", year, exc)
        return None

    rate = _parse(payload, year)
    if rate is None:
        logger.warning(
            "World Bank %s publishes no USD/KES rate for %s", FX_SERIES, year
        )
        return None

    lo, hi = PLAUSIBLE_USD_KES
    if not (lo <= rate <= hi):
        logger.warning(
            "USD/KES rate %s for %s is outside the plausible band [%s, %s]",
            rate, year, lo, hi,
        )
        return None

    logger.info("USD/KES rate for %s: %s (World Bank %s)", year, rate, FX_SERIES)
    return rate


def rate_provenance(year: int, rate: Decimal) -> str:
    """One line naming the rate, its year and its basis, for the row's notes."""
    return (
        f"converted at {rate} KES/USD — World Bank {FX_SERIES} "
        f"(official exchange rate, period average) for {year}, the same year "
        f"as the debt stock"
    )

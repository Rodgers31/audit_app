"""Fetch IMF World Economic Outlook data via the DataMapper REST API.

The DataMapper API only exposes a subset of WEO indicators, and for
Kenya specifically the following four are available:

  - GGXWDG_NGDP  — General-government gross debt, % of GDP
  - GGXCNL_NGDP  — Fiscal balance (net lending/borrowing), % of GDP
  - NGDPD        — Nominal GDP, current prices (USD billions)
  - NGDP_RPCH    — Real GDP growth rate, annual %

Years are 2018–2030 (historical + current + IMF's forward projections).

Note on User-Agent: IMF's edge filters out non-canonical UAs (tested
empirically — ``Mozilla/5.0`` and ``KenyaAuditApp/1.0`` both return
403). The first token must be a recognised HTTP-client identifier.
We use ``python-httpx/0.27`` as the first token and append our own
app identifier + a GitHub URL so site operators can reach us.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.imf_weo.fetcher")

_BASE_URL = "https://www.imf.org/external/datamapper/api/v1"

# ── Indicators ────────────────────────────────────────────────────
INDICATORS: tuple[str, ...] = (
    "GGXWDG_NGDP",  # Gross debt % GDP — headline for the dashboard card
    "GGXCNL_NGDP",  # Fiscal balance % GDP — stored for later use
    "NGDPD",        # Nominal GDP (USD B) — used to compute debt-in-KES
    "NGDP_RPCH",    # Real GDP growth % — contextual
)

# Start with Kenya only. Easy to widen later for peer comparisons.
COUNTRIES: tuple[str, ...] = ("KEN",)

# Year window we care about for the dashboard (past + current + near
# projections). IMF covers wider ranges but we don't need that now.
_PERIODS = ",".join(str(y) for y in range(2018, 2031))

# Must start with a known HTTP-client token so the IMF edge does not
# 403 us. See module docstring.
_IMF_UA = (
    "python-httpx/0.27 KenyaAuditApp-Seeder/1.0 "
    "(+https://github.com/Rodgers31/audit_app)"
)


def fetch_imf_weo(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[str, Dict[str, Any]]:
    """Return a dict keyed by indicator → IMF response payload.

    Shape:
        {
          "GGXWDG_NGDP": {"values": {"GGXWDG_NGDP": {"KEN": {"2024": 67.3, ...}}}},
          "NGDPD": {...},
          ...
        }

    Raises on network failure; caller logs and skips.
    """
    results: Dict[str, Dict[str, Any]] = {}
    countries = "/".join(COUNTRIES)
    for indicator in INDICATORS:
        url = f"{_BASE_URL}/{indicator}/{countries}?periods={_PERIODS}"
        logger.info("Fetching IMF WEO %s for %s", indicator, countries)
        # Override the seeder's default UA only for this call — other
        # sources might have their own constraints.
        response = client.get(url, headers={"User-Agent": _IMF_UA})
        response.raise_for_status()
        results[indicator] = response.json()
    return results

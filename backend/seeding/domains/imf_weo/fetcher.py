"""Fetch IMF World Economic Outlook data via the DataMapper REST API.

The DataMapper API only exposes a subset of WEO indicators, and for
Kenya specifically the following four are available:

  - GGXWDG_NGDP  — General-government gross debt, % of GDP
  - GGXCNL_NGDP  — Fiscal balance (net lending/borrowing), % of GDP
  - NGDPD        — Nominal GDP, current prices (USD billions)
  - NGDP_RPCH    — Real GDP growth rate, annual %

Request the full available time series, including historical observations and
projections. A bounded dashboard window would omit previously retained years.

Note on User-Agent: IMF's edge filters out non-canonical UAs (tested
empirically — ``Mozilla/5.0`` and ``KenyaAuditApp/1.0`` both return
403). The first token must be a recognised HTTP-client identifier.
We use ``python-httpx/0.27`` as the first token and append our own
app identifier + a GitHub URL so site operators can reach us.
"""

from __future__ import annotations

import logging
from html.parser import HTMLParser
import re
from typing import Any, Dict
from urllib.parse import urljoin, urlsplit

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from .workbook import WORKBOOK_BYTES, parse_workbook

logger = logging.getLogger("seeding.imf_weo.fetcher")

_BASE_URL = "https://www.imf.org/external/datamapper/api/v1"
WEO_CATALOGUE_URL = "https://data.imf.org/datasets/WEO"
WEO_WORKBOOK_URL = (
    "https://data.imf.org/-/media/iData/External-Storage/Documents/"
    "0FA3DC49A04D446E9D69DBEB29979E1C/en/WEOOct2026all.xlsx"
)

# ── Indicators ────────────────────────────────────────────────────
INDICATORS: tuple[str, ...] = (
    "GGXWDG_NGDP",  # Gross debt % GDP — headline for the dashboard card
    "GGXCNL_NGDP",  # Fiscal balance % GDP — stored for later use
    "NGDPD",        # Nominal GDP (USD B) — used to compute debt-in-KES
    "NGDP_RPCH",    # Real GDP growth % — contextual
)

# Start with Kenya only. Easy to widen later for peer comparisons.
COUNTRIES: tuple[str, ...] = ("KEN",)

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

    The caller handles a failed acquisition and selects the workbook when eligible.
    """
    from ...freshness import mark_live

    results: Dict[str, Dict[str, Any]] = {}
    countries = "/".join(COUNTRIES)
    for indicator in INDICATORS:
        url = f"{_BASE_URL}/{indicator}/{countries}"
        logger.info("Fetching IMF WEO %s for %s", indicator, countries)
        response = client.get(url, headers={"User-Agent": _IMF_UA})
        response.raise_for_status()
        results[indicator] = response.json()
    mark_live(
        "imf_weo",
        detail=(
            f"IMF DataMapper: {len(results)}/{len(INDICATORS)} indicator(s) "
            f"for {countries}"
        ),
    )
    return results


def fetch_reviewed_workbook(client: SeedingHttpClient) -> Dict[str, Dict[str, Any]]:
    """Only use the reviewed workbook while the publisher lists it as current."""
    class CurrentWorkbooks(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = set()

        def handle_starttag(self, tag, attrs):
            if tag != 'a':
                return
            href = dict(attrs).get('href')
            if href:
                url = urljoin(WEO_CATALOGUE_URL, href)
                if re.search(r'/WEO[A-Za-z]{3}\d{4}all\.xlsx$', urlsplit(url).path):
                    self.links.add(url)

    catalogue = client.get(WEO_CATALOGUE_URL, max_seconds=16, max_bytes=2 * 1024**2,
                           allowed_hosts={'data.imf.org'})
    parser = CurrentWorkbooks()
    parser.feed(catalogue.text)
    if parser.links != {WEO_WORKBOOK_URL}:
        raise ValueError('IMF WEO catalogue no longer identifies the reviewed workbook as current')
    workbook = client.get(WEO_WORKBOOK_URL, max_seconds=45, max_bytes=WORKBOOK_BYTES,
                          allowed_hosts={'data.imf.org'})
    return parse_workbook(workbook.content)

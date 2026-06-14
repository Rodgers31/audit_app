"""Tests for the shared COB WPDM PDF-discovery helper.

These pin the behaviour the three caller domains (counties_budget,
national_budget, pending_bills) depend on:

* WPDM ``?wpdmdl=NNN`` anchors are preferred and sorted by ID
  descending so the latest upload wins.
* Direct ``.pdf`` hrefs still work as a fallback (legacy pages /
  test fixtures predating the WPDM migration).
* Keyword filtering is permissive — it falls back to the unfiltered
  pool when no candidate matches, instead of returning ``None``.

The motivating bug: COB migrated all PDF distribution to WPDM, the
direct-``.pdf`` regex matched zero links, three domains silently
shipped fixture data on every nightly run.
"""

from __future__ import annotations

import pytest
from seeding.cob_discovery import discover_latest_cob_pdf_url


# A trimmed, real-shape page snippet covering both anchor styles
# COB has used. WPDM IDs are intentionally non-monotonic in source
# order so the test verifies sort-by-ID, not sort-by-position.
_WPDM_HTML = """
<html><body>
<a href="https://cob.go.ke/download/county-governments-birr-fy-2024-25/?wpdmdl=16263">FY 2024/25</a>
<a href="https://cob.go.ke/download/county-governments-birr-first-half-of-fy-2025-26/?wpdmdl=16349">H1 FY 2025/26</a>
<a href="https://cob.go.ke/download/county-governments-birr-first-quarter-of-fy-2025-26/?wpdmdl=16323">Q1 FY 2025/26</a>
<a href="https://cob.go.ke/download/some-other-publication/?wpdmdl=16400">Unrelated newer doc</a>
</body></html>
"""


class TestWpdmStrategy:
    def test_picks_highest_wpdmdl_id_among_keyword_matches(self):
        """Highest ``wpdmdl`` ID = newest WPDM upload. Among
        county-keyword matches, 16349 wins over 16263 / 16323."""
        chosen = discover_latest_cob_pdf_url(
            _WPDM_HTML,
            base_url="https://cob.go.ke/publications/foo/",
            keywords=["county", "c-birr"],
        )
        assert chosen == (
            "https://cob.go.ke/download/county-governments-birr-"
            "first-half-of-fy-2025-26/?wpdmdl=16349"
        )

    def test_keyword_filter_is_case_insensitive(self):
        """Caller keywords might be canonical-cased; the helper
        lowers both sides so an upper-case slug fragment still
        matches."""
        chosen = discover_latest_cob_pdf_url(
            _WPDM_HTML,
            base_url="https://cob.go.ke/",
            keywords=["COUNTY"],
        )
        assert chosen is not None and "county-governments" in chosen

    def test_falls_back_to_unfiltered_pool_when_no_keyword_match(self):
        """If filtering eliminates every candidate (e.g. caller's
        keyword list drifted away from current slugs), still return
        the latest WPDM hit rather than None — better than silently
        failing back to fixture for a slug-text typo."""
        chosen = discover_latest_cob_pdf_url(
            _WPDM_HTML,
            base_url="https://cob.go.ke/",
            keywords=["kazakhstan"],  # matches nothing
        )
        # Highest ID across ALL wpdm matches is 16400.
        assert chosen.endswith("?wpdmdl=16400")

    def test_handles_location_href_form(self):
        """Some legacy COB pages used the JS onclick handler:
        ``onclick="location.href='...'"`` rather than ``href=``."""
        html = """
        <a onclick="location.href='https://cob.go.ke/download/foo/?wpdmdl=999';return false;">x</a>
        """
        chosen = discover_latest_cob_pdf_url(
            html, base_url="https://cob.go.ke/", keywords=["foo"]
        )
        assert chosen == "https://cob.go.ke/download/foo/?wpdmdl=999"


class TestLegacyPdfFallback:
    def test_picks_first_pdf_when_no_wpdm(self):
        """Pages that still use direct ``.pdf`` hrefs (or test
        fixtures predating WPDM) fall through to the legacy pattern.
        First match wins — preserves the prior behaviour callers
        relied on."""
        html = """
        <a href="https://cob.go.ke/files/national-government-birr-q1.pdf">Q1</a>
        <a href="https://cob.go.ke/files/national-government-birr-q2.pdf">Q2</a>
        """
        chosen = discover_latest_cob_pdf_url(
            html,
            base_url="https://cob.go.ke/",
            keywords=["national-government", "birr"],
        )
        assert chosen.endswith("national-government-birr-q1.pdf")

    def test_resolves_relative_pdf_urls_against_base(self):
        """Relative hrefs in the legacy fallback get absolutised
        with ``urljoin`` against the page URL — WPDM URLs are always
        absolute so this only matters for the ``.pdf`` path."""
        html = '<a href="/files/birr-q1.pdf">x</a>'
        chosen = discover_latest_cob_pdf_url(
            html,
            base_url="https://cob.go.ke/publications/",
            keywords=["birr"],
        )
        assert chosen == "https://cob.go.ke/files/birr-q1.pdf"


class TestEmptyResults:
    def test_returns_none_when_no_pdf_links(self):
        """A page with neither WPDM nor ``.pdf`` anchors should
        return None — the caller treats that as 'live discovery
        failed, fall back to fixture'."""
        html = "<html><body>nothing useful here</body></html>"
        assert (
            discover_latest_cob_pdf_url(
                html, base_url="https://cob.go.ke/", keywords=["birr"]
            )
            is None
        )

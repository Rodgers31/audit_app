"""Annual Public Debt Report links come from Treasury's listing, not literals.

Issue #235. The budget page carried four literal links; on 2026-09-26 every one
returned 404, because Treasury moved from WordPress to Drupal and every
``/wp-content/uploads/...`` path died at once. The list also stopped at
FY2025/26, and its last entry ended in a literal ``...pdf``.

The fixture is an excerpt of https://www.treasury.go.ke/annual-debt-management-reports-0
captured 2026-09-26: 19 reports, FY 2005/06 to FY 2024/25, plus a form link that
must not be mistaken for one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import treasury_debt_reports as tdr

LISTING = (
    Path(__file__).parent / "fixtures" / "treasury"
    / "annual_debt_management_reports_2026-09-26.html"
).read_text(encoding="utf-8")


def test_every_report_on_the_listing_is_found_newest_first():
    reports = tdr.parse_listing(LISTING)
    years = [r["fiscal_year"] for r in reports]
    assert len(reports) == 19
    assert years[0] == "FY 2024/25" and years[-1] == "FY 2005/06"
    assert years == sorted(years, reverse=True)


def test_links_are_absolute_on_the_drupal_paths():
    by_fy = {r["fiscal_year"]: r for r in tdr.parse_listing(LISTING)}
    assert by_fy["FY 2024/25"]["url"] == (
        "https://www.treasury.go.ke/sites/default/files/Annual-Public-Debt-Report-2024-2025.pdf"
    )
    # The 2023/24 file's name does not carry its year; only the anchor text does.
    assert by_fy["FY 2023/24"]["url"].endswith("Annual-Public-Debt-Management-Report-.pdf")
    assert not any("/wp-content/uploads/2024/" in r["url"] for r in by_fy.values())


def test_a_form_on_the_same_page_is_not_a_report():
    urls = [r["url"] for r in tdr.parse_listing(LISTING)]
    assert not any("Expenditure" in u for u in urls)


def test_a_page_with_no_reports_is_an_error_not_an_empty_list():
    with pytest.raises(tdr.ListingError):
        tdr.parse_listing("<html><a href='/x.pdf'>Budget Circular</a></html>")


def test_an_unreachable_listing_is_unavailable_with_the_listing_url(monkeypatch):
    """conftest refuses outbound network, which is exactly an unreachable host."""
    monkeypatch.setattr(tdr, "_cache", {"at": 0.0, "ttl": 0, "value": None})
    out = asyncio.run(tdr.fetch_annual_debt_reports(timeout=1))
    assert out["status"] == "unavailable"
    assert out["reports"] == []
    assert out["listing_url"] == tdr.LISTING_URL


def test_a_failure_is_not_cached_for_twelve_hours(monkeypatch):
    monkeypatch.setattr(tdr, "_cache", {"at": 0.0, "ttl": 0, "value": None})
    asyncio.run(tdr.fetch_annual_debt_reports(timeout=1))
    assert tdr._cache["ttl"] == tdr.FAILURE_TTL_S < tdr.SUCCESS_TTL_S


def test_the_endpoint_serves_the_discovered_list(client, monkeypatch):
    async def _fake(timeout=20.0):
        return {"status": "success", "publisher": "The National Treasury",
                "listing_url": tdr.LISTING_URL, "reports": tdr.parse_listing(LISTING)}

    monkeypatch.setattr(tdr, "fetch_annual_debt_reports", _fake)
    body = client.get("/api/v1/debt/annual-reports").json()
    assert body["status"] == "success"
    assert body["reports"][0]["fiscal_year"] == "FY 2024/25"

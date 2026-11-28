"""Historical document coverage is proved by exact official downloads."""
from copy import deepcopy
import hashlib

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fetcher
from seeding.domains.fiscal_summary import reviewed_budget_editions as reviewed
from seeding.domains.fiscal_summary.fiscal_framework import FiscalFrameworkError
from seeding.http_client import SeedingHttpClient

PDF = b"%PDF-1.7\nOwned fiscal-edition test\n%%EOF\n"


def _profile():
    original, profile = next(iter(reviewed.load_reviewed_budget_editions().items()))
    return original, {**profile, "size_bytes": len(PDF), "sha256": hashlib.sha256(PDF).hexdigest()}


def test_actual_fiscal_listing_verifies_the_pdf_without_promoting_historical_budget_figures(monkeypatch):
    original, profile = _profile()
    listing = "https://www.treasury.go.ke/budget-summary-revenue-expenditure"
    replacement = "https://www.parliament.go.ke/owned-budget-summary.pdf"
    profile["pdf_url"] = replacement
    monkeypatch.setattr(reviewed, "load_reviewed_budget_editions", lambda: {original: profile})
    requested = []

    def get(request):
        url = str(request.url)
        requested.append(url)
        if url == listing:
            return httpx.Response(200, text=f'<a href="{original}">Budget Summary</a>')
        assert url == replacement
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=PDF)

    settings = SeedingSettings(_env_file=None)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(get))) as client:
        editions, facts = fetcher._fetch_budget_summary_editions(client, settings)
    assert requested == [listing, replacement]
    assert editions == []
    assert facts["budget_summary_editions"][original] == {
        "status": "verified_printed_edition", "fiscal_year": "FY 2022/23",
        "pdf_url": replacement, "sha256": profile["sha256"], "annex_page": 58,
        "column": "2022/23 Budget",
    }


def test_a_changed_document_does_not_receive_the_reviewed_edition_status():
    _, profile = _profile()
    modified = PDF.replace(b"Owned", b"Other")

    def response(request):
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=modified)

    settings = SeedingSettings(_env_file=None)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(response))) as client:
        with pytest.raises(FiscalFrameworkError, match="reviewed_budget_edition_identity_refused"):
            reviewed.verify_reviewed_budget_edition(client, settings, profile)


def test_reviewed_column_must_still_reconcile_before_an_acquisition():
    _, profile = _profile()
    profile = deepcopy(profile)
    profile["budget_column_kes_billions"]["net_domestic_financing"] = "0.0"
    # None would fail at the first attempt at acquisition; expected refusal
    # is the same arithmetic gate applied to all Treasury annexes.
    with pytest.raises(FiscalFrameworkError, match="does_not_reconcile"):
        reviewed.verify_reviewed_budget_edition(None, SeedingSettings(_env_file=None), profile)

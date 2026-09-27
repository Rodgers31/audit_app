"""National pending bills from the 2026 BROP, which the pipeline could not see.

The Treasury published the FINAL 2026 Budget Review and Outlook Paper in
September 2026. The nightly kept publishing the 2025 paper's 525.9B at 30 June
2025, reported LIVE, for two independent reasons, either of them enough:

1. Discovery matched ``budget-review-and-outlook-paper`` against the URL, and
   the 2026 paper's URL spells it ``2026%20Budget%20Review%20and%20Outlook``.
   The newest link that matched was the 2025 paper.
2. The parser anchored on the 2025 wording, "for the State Corporations and
   MDAs, respectively". The 2026 paper's para 20 (it was para 18 in 2025, para
   19 in the draft) says "for the State Corporations (SCs) and Ministries/State
   Departments/other government entities respectively", so it found nothing.

And nothing said so: reaching the Treasury was reported as LIVE whichever
paper it read.

Every text here is the real pdfplumber extraction, from ``fixtures/brop_pages.py``.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import brop_pages as fx  # noqa: E402

from seeding.domains.pending_bills import brop_parser as bp  # noqa: E402

B = 1_000_000_000


def _pdf(pages):
    """A stand-in for ``pdfplumber.open(...)`` serving real extracted pages."""
    fake_pages = []
    for text in pages:
        page = MagicMock()
        page.extract_text.return_value = text
        fake_pages.append(page)
    pdf = MagicMock()
    pdf.pages = fake_pages
    pdf.__enter__ = lambda s: pdf
    pdf.__exit__ = lambda *a: None
    return pdf


def _brop_2026():
    p = fx.BROP_2026_PAGES
    # The cover, filler for pp.2-17, the para-20 page, filler, Table 11.
    return _pdf([p[1]] + [""] * 16 + [p[18]] + [""] * 14 + [p[33], p[34]])


def _brop_2025():
    p = fx.BROP_2025_PAGES
    return _pdf([p[1]] + [""] * 16 + [p[18]])


class _Listing:
    """An HTTP client whose only page is a Treasury listing."""

    def __init__(self, html):
        self.html = html

    def get(self, url, **_kw):
        return SimpleNamespace(text=self.html, content=b"", status_code=200)


def _settings(**kw):
    return SimpleNamespace(
        treasury_brop_page_url=fx.TREASURY_LISTING_URL,
        treasury_brop_url=fx.BROP_2025_URL,
        live_pdf_fetch_enabled=True,
        **kw,
    )


# --------------------------------------------------------------------------
# 1. discovery
# --------------------------------------------------------------------------


class TestDiscovery:
    def test_the_real_listing_yields_the_2026_final(self):
        """RED before the fix: the 2025 paper."""
        from seeding.domains.pending_bills.fetcher import _discover_brop

        found = _discover_brop(_Listing(fx.TREASURY_LISTING_HTML), _settings())

        assert found is not None
        assert found.url == fx.BROP_2026_URL

    @pytest.mark.parametrize(
        "href",
        [
            "/sites/default/files/BROP/Draft%202027%20Budget%20Review%20and%20Outlook%20Paper.pdf",
            "/sites/default/files/BROP/Draft 2027 Budget Review and Outlook Paper.pdf",
            "/sites/default/files/BROP/DRAFT_2027_Budget_Review_and_Outlook_Paper.pdf",
        ],
    )
    def test_a_draft_is_still_refused_however_its_url_is_spelled(self, href):
        from seeding.domains.pending_bills.fetcher import _discover_brop

        html = f'<a href="{href}">Draft 2027</a>\n' + fx.TREASURY_LISTING_HTML
        found = _discover_brop(_Listing(html), _settings())

        assert found.url == fx.BROP_2026_URL

    def test_the_old_matching_cannot_see_the_2026_paper(self):
        """Positive control: the separator-insensitive match is what finds it."""
        from seeding.discovery import discover_latest_pdf

        kw = dict(
            must_match=("budget-review-and-outlook-paper",),
            must_not_match=("draft",),
        )
        literal = discover_latest_pdf(
            fx.TREASURY_LISTING_HTML, fx.TREASURY_LISTING_URL, **kw
        )
        normalised = discover_latest_pdf(
            fx.TREASURY_LISTING_HTML, fx.TREASURY_LISTING_URL,
            normalise_separators=True, **kw,
        )

        assert literal.url == fx.BROP_2025_URL
        assert normalised.url == fx.BROP_2026_URL

    def test_the_default_matching_is_unchanged_for_other_callers(self):
        """fiscal_summary matches "/budget%20books/" literally."""
        from seeding.discovery import discover_latest_pdf

        html = '<a href="/budget%20books/2026-27/Budget-Summary.pdf">x</a>'
        found = discover_latest_pdf(
            html, "https://www.treasury.go.ke/", must_match=("/budget%20books/",)
        )
        assert found is not None


# --------------------------------------------------------------------------
# 2. the national paragraph, read by what it says
# --------------------------------------------------------------------------


class TestNationalParagraph:
    def test_the_2026_paragraph_is_read(self):
        """RED before the fix: None."""
        national = bp._detect_national_paragraph(_brop_2026(), "FY 2025/26")

        assert national is not None
        assert national.total == Decimal(475_500_000_000)
        assert national.state_corporations == Decimal(365_600_000_000)
        assert national.mdas == Decimal(109_900_000_000)
        assert national.as_at_date == date(2026, 6, 30)
        assert national.as_at_stated is True
        assert national.paragraph == 20

    def test_the_2025_paragraph_still_reads_the_same(self):
        national = bp._detect_national_paragraph(_brop_2025(), "FY 2024/25")

        assert (national.total, national.state_corporations, national.mdas) == (
            Decimal(525_900_000_000), Decimal(404_300_000_000), Decimal(121_600_000_000)
        )
        assert national.as_at_date == date(2025, 6, 30)
        assert national.as_at_stated is True
        assert national.paragraph == 18

    def test_the_figures_are_assigned_by_the_labels_not_their_order(self):
        """A paper that lists MDAs first must not swap the two lines."""
        text = fx.BROP_2026_PAGES[18].replace(
            "for the State Corporations (SCs) and Ministries/State Departments/other\n"
            "government entities respectively",
            "for the Ministries/State Departments/other government entities and the\n"
            "State Corporations (SCs) respectively",
        )
        assert text != fx.BROP_2026_PAGES[18]

        national = bp._detect_national_paragraph(_pdf([text]), "FY 2025/26")

        assert national.mdas == Decimal(365_600_000_000)
        assert national.state_corporations == Decimal(109_900_000_000)

    def test_each_figure_followed_by_its_own_label(self):
        text = (
            "20. The total outstanding National Government pending bills as of 30th June "
            "2026 amounted\nto KSh 475.5 billion comprising of KSh 109.9 billion for "
            "Ministries/State Departments\nand KSh 365.6 billion for State Corporations.\n"
            "21. The National Government policy ..."
        )
        national = bp._detect_national_paragraph(_pdf([text]), "FY 2025/26")

        assert national.mdas == Decimal(109_900_000_000)
        assert national.state_corporations == Decimal(365_600_000_000)

    def test_a_paragraph_that_does_not_add_up_is_refused(self):
        """Printed to 0.1B, so the halves may miss the total by 0.1B, no more."""
        text = fx.BROP_2026_PAGES[18].replace("KSh 365.6 billion", "KSh 356.6 billion")
        assert text != fx.BROP_2026_PAGES[18]

        with pytest.raises(bp.BropNationalUnreconciled, match="475.5"):
            bp._detect_national_paragraph(_pdf([text]), "FY 2025/26")

    def test_figures_it_cannot_label_are_not_guessed(self):
        text = (
            "20. The total outstanding National Government pending bills as of 30th June "
            "2026 amounted\nto KSh 475.5 billion comprising of KSh 365.6 billion and "
            "KSh 109.9 billion.\n21. The National Government policy ..."
        )
        assert bp._detect_national_paragraph(_pdf([text]), "FY 2025/26") is None

    def test_another_paragraphs_figure_is_not_borrowed(self):
        """Para 19's billions sit just above para 20 on the same page."""
        text = fx.BROP_2026_PAGES[18].split("Pending Bills\n")[0] + (
            "Pending Bills\n20. The total outstanding National Government pending bills "
            "as of 30th June 2026 amounted\nto KSh 475.5 billion.\n"
            "21. Something else: KSh 365.6 billion and KSh 109.9 billion for the State "
            "Corporations and MDAs respectively.\n"
        )
        assert bp._detect_national_paragraph(_pdf([text]), "FY 2025/26") is None


# --------------------------------------------------------------------------
# 3. the whole read, as the fetcher does it
# --------------------------------------------------------------------------


def _fetch(tmp_path, pdf):
    from seeding.domains.pending_bills.fetcher import _fetch_from_treasury_brop

    fake = tmp_path / "brop.pdf"
    fake.write_bytes(b"%PDF-stub")
    with patch.object(bp.pdfplumber, "open", return_value=pdf):
        return _fetch_from_treasury_brop(None, f"file://{fake}")


class TestFetch:
    def test_the_2026_paper_parses(self, tmp_path):
        """RED before the fix: "No pending-bills data found"."""
        with patch.object(bp.pdfplumber, "open", return_value=_brop_2026()):
            result = bp.parse_brop_pdf(tmp_path / "x.pdf")

        assert result.fiscal_year_label == "FY 2025/26"
        assert result.national.total == Decimal(475_500_000_000)

    def test_the_payload_states_30_june_2026_on_both_lines(self, tmp_path):
        payload = _fetch(tmp_path, _brop_2026())

        rows = payload["pending_bills"]
        assert [(r["category"], Decimal(r["total_pending"]), r["as_at"]) for r in rows] == [
            ("state_corporation", Decimal(365_600_000_000), "2026-06-30"),
            ("mda", Decimal(109_900_000_000), "2026-06-30"),
        ]
        assert {r["fiscal_year"] for r in rows} == {"FY 2025/26"}
        assert all("para 20" in r["notes"] for r in rows)
        assert payload["summary"]["total_national"] == str(475_500_000_000)

    def test_a_county_table_that_does_not_add_up_does_not_cost_the_national_figure(
        self, tmp_path
    ):
        """Counties are read from the CoB (#238). A BROP county table the strict
        check refuses used to take the national paragraph down with it."""
        broken_table = (
            "Table 10: County Governments Pending Bills as at 30th June 2025\n"
            "1. Nairobi 78,949.1 7,169.4 86,118.6 650.6 650.6 86,769.2 43,564.27 199.2\n"
            "Total 122,625.9 49,121.0 171,746.9 4,232.7 924.5 5,157.3 176,904.2 601,689.14 29\n"
        )
        pdf = _pdf([fx.BROP_2025_PAGES[1]] + [""] * 16 + [fx.BROP_2025_PAGES[18], broken_table])
        with patch.object(bp.pdfplumber, "open", return_value=pdf):
            with pytest.raises(bp.BropTableIncomplete):
                bp.parse_brop_pdf(tmp_path / "x.pdf")

        payload = _fetch(tmp_path, pdf)

        assert sorted(Decimal(r["total_pending"]) for r in payload["pending_bills"]) == [
            Decimal(121_600_000_000), Decimal(404_300_000_000)
        ]

    def test_a_paper_without_the_national_paragraph_is_an_error(self, tmp_path):
        """Even one whose county table reads whole: the counties are not read
        from it, so it would be a run that published nothing and said LIVE."""
        pdf = _pdf([fx.BROP_2026_PAGES[1], fx.BROP_2026_PAGES[33], fx.BROP_2026_PAGES[34]])
        with pytest.raises(ValueError, match="national pending-bills paragraph"):
            _fetch(tmp_path, pdf)


# --------------------------------------------------------------------------
# 4. the national + county total is publishable again
# --------------------------------------------------------------------------


@pytest.fixture()
def entities(db_session, seed_country, seed_source_doc):
    from models import Entity, EntityType

    national = Entity(
        id=900, country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name="National Government", slug="national-government",
    )
    nairobi = Entity(
        id=3, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    db_session.add_all([national, nairobi])
    db_session.commit()
    return national, nairobi


def _write(db_session, payload, **kw):
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills

    write_pending_bills(
        db_session, parse_pending_bills_payload(payload),
        source_url=payload["source_url"], source_title=payload["source_title"],
        publication=payload["publication"], publisher=payload["publisher"], **kw,
    )
    db_session.commit()


def _nairobi_cob_2026():
    from seeding.domains.pending_bills.fetcher import county_payables_payload

    entry = {
        "county": "Nairobi", "status": "reported", "withheld_reason": None,
        "total_millions": "86899.38", "assembly_printed": True,
        "cob_marked_inconsistent": False, "chapter_total_millions": None,
        "chapter_table": None, "chapter_page": None, "as_at": "2026-06-30",
        "fiscal_year": "FY 2025/26", "table": "Table 2.10", "page": 52,
    }
    return county_payables_payload([entry], "https://cob.go.ke/download/cbirr/?wpdmdl=16482")


def test_reading_the_2026_paper_makes_the_total_publishable(
    client, db_session, entities, tmp_path
):
    """Production today: national at 30 June 2025, counties at 30 June 2026, so
    no total. The 2026 paper replaces both national lines in place, and the
    two halves are one day's stock again."""
    from main import clear_all_caches

    _write(db_session, _fetch(tmp_path, _brop_2025()))
    cob = _nairobi_cob_2026()
    _write(db_session, cob, county_table=cob["county_table"])

    clear_all_caches()
    before = client.get("/api/v1/pending-bills").json()["summary"]
    assert (before["national_as_at"], before["county_as_at"]) == ("2025-06-30", "2026-06-30")
    assert before["total_pending"] is None

    _write(db_session, _fetch(tmp_path, _brop_2026()))

    clear_all_caches()
    after = client.get("/api/v1/pending-bills").json()["summary"]
    assert after["national_total"] == 475_500_000_000
    assert after["county_total"] == 86_899_380_000
    assert after["as_at"] == "2026-06-30"
    assert after["total_pending"] == 475_500_000_000 + 86_899_380_000


# --------------------------------------------------------------------------
# 5. a pipeline behind the publisher says so
# --------------------------------------------------------------------------


class TestEditionSignal:
    def _run(self, monkeypatch, tmp_path, html, pdf, today):
        from seeding import freshness
        from seeding.domains.pending_bills import fetcher

        freshness.reset("pending_bills")
        fake = tmp_path / "brop.pdf"
        fake.write_bytes(b"%PDF-stub")
        monkeypatch.setattr(fetcher, "_today", lambda: today)
        # Every PDF URL resolves to the stub file; the listing is the real one.
        real_fetch = fetcher._fetch_from_treasury_brop

        def fetch(client, url):
            payload = real_fetch(client, f"file://{fake}")
            payload["source_url"] = url
            return payload

        monkeypatch.setattr(fetcher, "_fetch_from_treasury_brop", fetch)
        settings = _settings()
        with patch.object(bp.pdfplumber, "open", return_value=pdf):
            payload = fetcher.fetch_pending_bills_payload(_Listing(html), settings)
        return payload, freshness.get("pending_bills")

    def test_the_current_paper_is_live(self, monkeypatch, tmp_path):
        payload, mode = self._run(
            monkeypatch, tmp_path, fx.TREASURY_LISTING_HTML, _brop_2026(), date(2026, 9, 26)
        )
        assert payload["source_url"] == fx.BROP_2026_URL
        assert mode["mode"] == "live"

    def test_a_newer_paper_on_the_listing_than_the_one_read_is_not_live(
        self, monkeypatch, tmp_path
    ):
        """The incident's shape, one naming change later: the listing links a
        newer paper under a name discovery does not match, discovery picks the
        newest paper it can match, and the run used to say LIVE."""
        html = (
            '<a href="/sites/default/files/BROP/BROP%202027%20Final.pdf">2027 BROP</a>\n'
            + fx.TREASURY_LISTING_HTML
        )
        payload, mode = self._run(
            monkeypatch, tmp_path, html, _brop_2026(), date(2027, 9, 20)
        )
        assert payload["source_url"] == fx.BROP_2026_URL
        assert payload["publication"] == "treasury_brop"  # still written
        assert mode["mode"] == "partial"
        assert mode["reason"] == "brop_edition_behind"
        assert "BROP%202027" in mode["detail"]

    def test_a_newer_draft_on_the_listing_is_not_a_newer_paper(
        self, monkeypatch, tmp_path
    ):
        html = (
            '<a href="/sites/default/files/BROP/Draft%202027%20BROP.pdf">draft</a>\n'
            + fx.TREASURY_LISTING_HTML
        )
        _payload, mode = self._run(
            monkeypatch, tmp_path, html, _brop_2026(), date(2027, 8, 20)
        )
        assert mode["mode"] == "live"

    def test_a_paper_a_year_overdue_is_not_live(self, monkeypatch, tmp_path):
        """No newer link anywhere (the listing lost it), but by 1 November 2026
        the paper on 30 June 2026 is due and 30 June 2025 is last year's."""
        listing = "\n".join(
            a for a in fx.TREASURY_LISTING_ANCHORS if "2026%20Budget" not in a
        )
        _payload, mode = self._run(
            monkeypatch, tmp_path, listing, _brop_2025(), date(2026, 11, 1)
        )
        assert mode["mode"] == "partial"
        assert mode["reason"] == "brop_edition_behind"
        assert "2025-06-30" in mode["detail"]

    def test_last_years_paper_before_this_years_is_due_is_live(
        self, monkeypatch, tmp_path
    ):
        """Before the 2026 paper appeared, reading 2025 was right."""
        listing = "\n".join(
            a for a in fx.TREASURY_LISTING_ANCHORS if "2026%20Budget" not in a
        )
        _payload, mode = self._run(
            monkeypatch, tmp_path, listing, _brop_2025(), date(2026, 8, 1)
        )
        assert mode["mode"] == "live"

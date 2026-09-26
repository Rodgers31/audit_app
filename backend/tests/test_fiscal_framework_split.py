"""Issue #237: the enacted year's borrowing, spending split and tax vs non-tax.

On 2026-09-26 ``/api/v1/fiscal/summary`` served FY 2026/27 with
``total_borrowing``, ``development_spending``, ``recurrent_spending``,
``tax_revenue`` and ``non_tax_revenue`` all null, although the Budget Summary
the nightly already downloads prints every one of them in Annex Table 2a.

These tests run the parser over the REAL text layer of two editions (saved
verbatim in ``tests/fixtures/budget_summary/``, with their byte counts and
sha256), and then tamper with it to prove each gate refuses what it should.
The numbers asserted below were read off the PDFs, not computed here.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

from seeding.domains.fiscal_summary import fiscal_framework as ff
from seeding.domains.fiscal_summary.fetcher import (
    _apply_fiscal_framework,
    _fetch_budget_summary_editions,
)
from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload

FIXTURES = Path(__file__).parent / "fixtures" / "budget_summary"
URL_2627 = (
    "https://www.treasury.go.ke/sites/default/files/Budget%20summary/"
    "Budget%20Summary%20for%20the%20FY%202026_27%20Budget.pdf"
)
URL_2324 = (
    "https://www.treasury.go.ke/sites/default/files/Budget%20summary/"
    "Budget-Summary-for-the-FY-2023_24.pdf"
)


def _pages(name: str) -> List[str]:
    doc = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    count = doc["_source"]["page_count"]
    return [doc["pages"].get(str(i), "") for i in range(1, count + 1)]


def _edition(name="fy2026_27", fy="FY 2026/27", pages=None):
    return ff.read_edition(pages or _pages(name), fiscal_year=fy)


def _tamper(pages: List[str], page: int, old: str, new: str) -> List[str]:
    out = list(pages)
    assert old in out[page - 1], f"{old!r} not on p.{page}"
    out[page - 1] = out[page - 1].replace(old, new, 1)
    return out


# ── The real FY 2026/27 edition ─────────────────────────────────────────


class TestEnactedEdition:
    def test_reads_the_approved_column(self):
        ed = _edition()
        assert ed.table.page == 63
        split = ff.split_for_fiscal_year(ed, "FY 2026/27", known_ordinary_revenue=2985.7)
        v = {k: float(x) for k, x in split.values.items()}
        # Annex Table 2a p.63, FY 2026/27 "Approved Budget" column, and paras
        # 29/31/33 (PDF pp.12-13), which restate the same figures.
        assert v["expenditure"] == 4785.2
        assert v["recurrent"] == 3538.7
        assert v["interest"] == 1254.2
        assert v["development"] == 749.0
        assert v["county_transfers"] == 495.5
        assert v["equitable_share"] == 420.0
        assert v["contingency"] == 2.0
        assert v["ordinary_revenue"] == 2985.7
        assert v["tax_revenue"] == 2858.7
        assert v["non_tax_revenue"] == 127.1
        assert v["total_financing"] == 1111.8
        assert v["net_foreign_financing"] == 116.2
        assert v["net_domestic_financing"] == 995.7
        assert split.identified_by == "approved_budget"
        assert split.tax_split_ok

    def test_the_bps_column_beside_it_is_not_chosen(self):
        """The BPS 2026 column prints 2,901.9 ordinary revenue. Publishing it
        as the approved budget would be out by 84B."""
        ed = _edition()
        assert float(ed.table.column(ed.approved_index)["ordinary_revenue"]) == 2985.7
        assert float(ed.table.column(ed.approved_index - 1)["ordinary_revenue"]) == 2901.9

    def test_split_reconciles_to_its_own_total_not_to_cob_gross(self):
        payload = ff.framework_payload(
            ff.split_for_fiscal_year(_edition(), "FY 2026/27", known_ordinary_revenue=None),
            source_url=URL_2627,
            page=63,
        )
        parts = (
            payload["recurrent_billion"]
            + payload["development_billion"]
            + payload["county_transfers_billion"]
            + payload["contingency_billion"]
        )
        assert round(parts, 1) == payload["total_expenditure_billion"] == 4785.2
        # ...and not to the 5,485.7 COB gross figure the page headlines.
        assert abs(parts - 5485.7) > 600
        assert payload["basis"] == "treasury_fiscal_framework"
        assert payload["source"]["page"] == "Annex Table 2a, PDF p.63"

    def test_tax_heads_are_published(self):
        payload = ff.framework_payload(
            ff.split_for_fiscal_year(_edition(), "FY 2026/27", known_ordinary_revenue=None),
            source_url=URL_2627,
            page=63,
        )
        assert payload["tax_heads_billion"] == {
            "income_tax": 1383.6,
            "import_duty": 186.2,
            "excise_duty": 382.2,
            "vat": 829.2,
            "other_tax": 77.4,
        }

    @pytest.mark.parametrize(
        "fy,revenue,expected",
        [
            # Each past year joins on the ordinary revenue revenue_estimates
            # published for it, and lands on that column's figures.
            ("FY 2023/24", 2288.9, {"expenditure": 3605.2, "recurrent": 2678.4, "total_financing": 818.3}),
            ("FY 2024/25", 2420.2, {"expenditure": 3975.9, "recurrent": 2948.4, "total_financing": 1034.2}),
            ("FY 2025/26", 2784.4, {"expenditure": 4638.4, "recurrent": 3393.2, "total_financing": 1199.4}),
        ],
    )
    def test_past_years_come_from_their_revenue_column(self, fy, revenue, expected):
        split = ff.split_for_fiscal_year(_edition(), fy, known_ordinary_revenue=revenue)
        assert split.identified_by == "revenue_column"
        for key, value in expected.items():
            assert float(split.values[key]) == value

    def test_statistical_discrepancy_is_part_of_the_financing_identity(self):
        """FY 2023/24 actual: financing 818.3 = 835.1 (cash deficit) - 16.8."""
        split = ff.split_for_fiscal_year(_edition(), "FY 2023/24", known_ordinary_revenue=2288.9)
        assert float(split.values["statistical_discrepancy"]) == -16.8


class TestOlderEdition:
    def test_fy2023_24_reads_its_approved_column(self):
        ed = _edition("fy2023_24", "FY 2023/24")
        assert ed.table.page == 62
        split = ff.split_for_fiscal_year(ed, "FY 2023/24", known_ordinary_revenue=None)
        v = {k: float(x) for k, x in split.values.items()}
        # Para 24-25, PDF p.10 of the FY 2023/24 edition.
        assert (v["expenditure"], v["recurrent"], v["development"]) == (3599.3, 2477.6, 689.1)
        assert (v["county_transfers"], v["total_financing"]) == (429.7, 663.5)

    def test_edition_without_a_tax_row_withholds_the_tax_split(self):
        """The FY 2023/24 edition prints the tax heads but no "Tax Revenue"
        or "Non-Tax Revenue" row, and its "Other" line mixes both."""
        ed = _edition("fy2023_24", "FY 2023/24")
        split = ff.split_for_fiscal_year(ed, "FY 2023/24", known_ordinary_revenue=None)
        assert not split.tax_split_ok
        payload = ff.framework_payload(split, source_url=URL_2324, page=62)
        assert "tax_revenue_billion" not in payload
        assert payload["tax_split_absent_reason"] == "edition_prints_no_tax_or_non_tax_row"


# ── Gates: each one refuses ─────────────────────────────────────────────


class TestGatesRefuse:
    def test_a_changed_cell_breaks_the_spending_identity(self):
        # Recurrent 3,538.7 -> 3,548.7 in the approved column only.
        pages = _pages("fy2026_27")
        line = next(l for l in pages[62].splitlines() if l.startswith("Recurrent expenditure"))
        bad = line.replace("3,538.7", "3,548.7")
        pages = _tamper(pages, 63, line, bad)
        # The narrative still quotes 3,538.7, so the column is still found by
        # its other eight figures; the identity is what must refuse it.
        ed = ff.read_edition(pages, fiscal_year="FY 2026/27")
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.split_for_fiscal_year(ed, "FY 2026/27", known_ordinary_revenue=None)
        assert exc.value.reason == "does_not_reconcile"

    def test_no_narrative_no_column(self):
        pages = _pages("fy2026_27")
        pages[11] = pages[12] = ""  # paras 29-33
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.read_edition(pages, fiscal_year="FY 2026/27")
        assert exc.value.reason == "narrative_does_not_identify_a_column"

    def test_cover_and_link_must_agree(self):
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.read_edition(_pages("fy2026_27"), fiscal_year="FY 2027/28")
        assert exc.value.reason == "cover_disagrees_with_link"

    def test_table_2_and_the_annex_must_agree_on_the_enacted_year(self):
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.split_for_fiscal_year(_edition(), "FY 2026/27", known_ordinary_revenue=2901.9)
        assert exc.value.reason == "revenue_column_disagrees"

    def test_a_revenue_no_column_prints_is_not_joined(self):
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.split_for_fiscal_year(_edition(), "FY 2022/23", known_ordinary_revenue=2042.0)
        assert exc.value.reason == "no_column_prints_this_revenue"

    def test_a_scanned_annex_is_refused_by_name(self):
        pages = [""] * 60
        pages[0] = "THE BUDGET SUMMARY FOR THE FISCAL YEAR\n2022/23"
        pages[57] = "Annex Table 2a: Fiscal Framework (Ksh billion)\n58"
        with pytest.raises(ff.FiscalFrameworkError) as exc:
            ff.read_edition(pages, fiscal_year="FY 2022/23")
        assert exc.value.reason == "annex_has_no_rows"

    def test_a_broken_tax_split_withholds_only_the_tax_split(self):
        pages = _pages("fy2026_27")
        line = next(l for l in pages[62].splitlines() if l.startswith("Non-Tax Revenue"))
        pages = _tamper(pages, 63, line, line.replace("127.1", "137.1"))
        split = ff.split_for_fiscal_year(
            ff.read_edition(pages, fiscal_year="FY 2026/27"),
            "FY 2026/27",
            known_ordinary_revenue=None,
        )
        assert not split.tax_split_ok
        assert float(split.values["recurrent"]) == 3538.7  # spending split survives


# ── Apply: what lands on the rows ───────────────────────────────────────


def _payload_as_revenue_step_leaves_it():
    """The shipped fixture, with the revenue the Budget Summary's Table 2
    step writes, as it stands just before the framework step runs."""
    fixture = json.loads(
        (Path(__file__).parents[1] / "seeding" / "real_data" / "fiscal_summary.json").read_text()
    )
    table2 = {"FY 2023/24": 2288.9, "FY 2024/25": 2420.2, "FY 2025/26": 2784.4, "FY 2026/27": 2985.7}
    for row in fixture["fiscal_years"]:
        if row["fiscal_year"] in table2:
            row["total_revenue"] = table2[row["fiscal_year"]]
            row["revenue_source"] = {"url": URL_2627}
    return fixture


class TestApply:
    def test_enacted_year_gets_every_split_field(self):
        payload, status = _apply_fiscal_framework(
            _payload_as_revenue_step_leaves_it(), [(URL_2627, _edition())]
        )
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
        assert status.startswith("applied=")
        assert row["split_basis"] == "treasury_fiscal_framework"
        assert row["total_borrowing"] == 1111.8
        assert row["recurrent_spending"] == 3538.7
        assert row["development_spending"] == 749.0
        assert row["county_allocation"] == 495.5  # transfers, not the 420 share
        assert row["tax_revenue"] == 2858.7
        assert row["non_tax_revenue"] == 127.1
        assert row["fiscal_framework"]["county_equitable_share_billion"] == 420.0

    def test_legacy_year_no_edition_supplies_keeps_no_basis(self):
        payload, _ = _apply_fiscal_framework(
            _payload_as_revenue_step_leaves_it(), [(URL_2627, _edition())]
        )
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2022/23")
        assert "split_basis" not in row and "fiscal_framework" not in row

    def test_tax_split_not_shown_beside_a_total_it_does_not_add_up_to(self):
        payload = _payload_as_revenue_step_leaves_it()
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
        row["revenue_source"] = {"url": "https://elsewhere.example/x.pdf"}
        row["total_revenue"] = 3000.0  # a different vintage from a different document
        payload, _ = _apply_fiscal_framework(payload, [(URL_2627, _edition())])
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
        assert row["tax_revenue"] is None and row["non_tax_revenue"] is None
        assert "not shown against it" in row["tax_split_absent_reason"]
        assert row["recurrent_spending"] == 3538.7

    def test_enacted_year_revenue_is_filled_when_table_2_left_it_absent(self):
        """Next year's situation: revenue_estimates refuses a budget year it
        has no BPS constant for, so the row arrives with no revenue."""
        payload = _payload_as_revenue_step_leaves_it()
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
        row["total_revenue"] = None
        row.pop("revenue_source")
        payload, _ = _apply_fiscal_framework(payload, [(URL_2627, _edition())])
        row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
        assert row["total_revenue"] == 2985.7
        assert row["revenue_basis"] == "ordinary_revenue_excl_aia"
        assert row["tax_revenue"] == 2858.7

    def test_older_edition_backs_up_its_own_year_when_the_newest_cannot(self):
        """Only the FY 2023/24 edition could be read: it still supplies FY
        2023/24 (its approved column), and nothing else."""
        payload = _payload_as_revenue_step_leaves_it()
        payload, status = _apply_fiscal_framework(
            payload, [(URL_2324, _edition("fy2023_24", "FY 2023/24"))]
        )
        by_year = {r["fiscal_year"]: r for r in payload["fiscal_years"]}
        assert by_year["FY 2023/24"]["recurrent_spending"] == 2477.6
        assert by_year["FY 2023/24"]["fiscal_framework"]["identified_by"] == "approved_budget"
        # Its approved ordinary revenue (2,571.2) is not the actual the row
        # publishes (2,288.9), so no tax split is placed beside it.
        assert by_year["FY 2023/24"]["tax_revenue"] is None
        assert "split_basis" not in by_year["FY 2026/27"]

    def test_record_parser_derives_borrowing_share_on_one_basis(self):
        payload, _ = _apply_fiscal_framework(
            _payload_as_revenue_step_leaves_it(), [(URL_2627, _edition())]
        )
        recs = {r.fiscal_year: r for r in parse_fiscal_summary_payload(payload)}
        # 1,111.8 / 4,785.2 — both from the same Annex column.
        assert recs["FY 2026/27"].borrowing_pct_of_budget == 23.2
        # FY 2022/23: legacy borrowing with no spending total on its basis.
        assert recs["FY 2022/23"].borrowing_pct_of_budget is None
        assert recs["FY 2026/27"].fiscal_framework["total_expenditure_billion"] == 4785.2


# ── Discovery: every edition, and the facts the gate reads ──────────────


class _Resp:
    def __init__(self, text):
        self.text = text


class _Client:
    def __init__(self, html):
        self.html = html

    def get(self, url, raise_for_status=True):
        return _Resp(self.html)


LISTING = f"""
<a href="/sites/default/files/Budget%20summary/Budget%20Summary%20for%20the%20FY%202026_27%20Budget.pdf">x</a>
<a href="/sites/default/files/Budget%20summary/Budget-Summary-for-the-FY-2023_24.pdf">x</a>
<a href="https://oldsite.treasury.go.ke/wp-content/uploads/2025/06/Budget-Summary-for-the-FY-2025-26F.pdf">x</a>
<a href="/sites/default/files/TNT-%20Expenditure%20Requisition%20Form%20Amended%20Final.pdf">x</a>
"""


def test_discovery_reads_every_edition_and_records_the_listing(monkeypatch, tmp_path):
    from seeding import pdf_download
    from seeding.config import SeedingSettings

    by_url = {URL_2627: "fy2026_27", URL_2324: "fy2023_24"}

    def fake_download(client, url, **kw):
        if url not in by_url:
            raise RuntimeError("404")
        return Path(by_url[url])

    monkeypatch.setattr(pdf_download, "get_or_download_pdf", fake_download)
    monkeypatch.setattr(
        ff,
        "extract_page_texts",
        lambda p: [{"page": i + 1, "text": t} for i, t in enumerate(_pages(str(p)))],
    )
    settings = SeedingSettings(cache_path=str(tmp_path), parse_cache_enabled=False)
    editions, facts = _fetch_budget_summary_editions(_Client(LISTING), settings)

    assert [e.fiscal_year for _u, e in editions] == ["FY 2026/27", "FY 2023/24"]
    assert facts["budget_summary_listing_newest_fy"] == "FY 2026/27"
    statuses = {u.rsplit("/", 1)[-1]: e["status"] for u, e in facts["budget_summary_editions"].items()}
    assert statuses["Budget-Summary-for-the-FY-2025-26F.pdf"] == "unreadable(RuntimeError)"
    # The requisition form is not a Budget Summary.
    assert len(statuses) == 3


# ── End to end: through the writer and the API ──────────────────────────


def test_api_serves_the_split_with_its_total(db_session, seed_country):
    from main import clear_all_caches, get_fiscal_summary
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records

    payload, _ = _apply_fiscal_framework(
        _payload_as_revenue_step_leaves_it(), [(URL_2627, _edition())]
    )
    # Stand in for the budget books step, which sets the enacted budget.
    row = next(r for r in payload["fiscal_years"] if r["fiscal_year"] == "FY 2026/27")
    row.update(
        appropriated_budget=5485.7,
        budget_basis="cob_gross",
        budget_basis_source={"url": "https://x/pbb.pdf", "page": "voted total PDF p.11"},
    )
    write_fiscal_summary_records(
        db_session, parse_fiscal_summary_payload(payload), payload["metadata"]
    )
    db_session.commit()
    clear_all_caches()
    body = asyncio.run(get_fiscal_summary(db=db_session))

    cur = body["current"]
    assert cur["fiscal_year"] == "FY 2026/27"
    assert cur["total_borrowing"] == pytest.approx(1111.8e9)
    assert cur["recurrent_spending"] == pytest.approx(3538.7e9)
    assert cur["tax_revenue"] == pytest.approx(2858.7e9)
    assert cur["borrowing_pct_of_budget"] == 23.2
    assert cur["split_basis"] == "treasury_fiscal_framework"
    assert cur["fiscal_framework"]["total_expenditure_billion"] == 4785.2
    assert cur["fiscal_framework"]["interest_payments_billion"] == 1254.2


# ── The freshness gate ──────────────────────────────────────────────────

NOW = datetime(2027, 7, 15, tzinfo=timezone.utc)


def _job(days_ago, newest_fy, status="read"):
    from models import IngestionJob, IngestionStatus

    meta = {
        "source_mode": "live",
        "budget_summary_listing_status": status,
        "budget_summary_listing_newest_fy": newest_fy,
        "budget_summary_editions": {
            "u": {"fiscal_year": newest_fy, "status": "refused:narrative_ambiguous"}
        },
    }
    return IngestionJob(
        domain="fiscal_summary",
        status=IngestionStatus.COMPLETED,
        dry_run=False,
        started_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None),
        items_processed=6,
        items_created=0,
        items_updated=6,
        errors=[],
        meta=meta,
    )


def _split_row(db_session, fy):
    from models import FiscalSummary

    db_session.add(
        FiscalSummary(
            fiscal_year=fy,
            unit="KES",
            meta={"split_basis": "treasury_fiscal_framework", "fiscal_framework": {"total_expenditure_billion": 4785.2}},
        )
    )


class TestSplitGate:
    def test_red_when_a_newer_budget_summary_is_listed(self, db_session):
        from seeding.staleness import FAIL, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        db_session.add(_job(1, "FY 2027/28"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == FAIL
        assert "FY 2027/28" in f.message and "FY 2026/27" in f.message
        assert "narrative_ambiguous" in f.message

    def test_ok_when_the_split_is_current(self, db_session):
        from seeding.staleness import OK, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        db_session.add(_job(1, "FY 2026/27"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == OK

    def test_a_row_without_a_declared_basis_is_not_a_split(self, db_session):
        from models import FiscalSummary
        from seeding.staleness import FAIL, check_fiscal_split_freshness

        db_session.add(FiscalSummary(fiscal_year="FY 2026/27", unit="KES", meta={}))
        db_session.add(_job(1, "FY 2026/27"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == FAIL

    def test_judged_on_the_newest_run_not_the_window(self, db_session):
        """Ten green nights must not hide a red one."""
        from seeding.staleness import FAIL, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        for d in range(2, 12):
            db_session.add(_job(d, "FY 2026/27"))
        db_session.add(_job(1, "FY 2027/28"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == FAIL

    def test_unrecorded_is_warn_never_ok(self, db_session):
        from seeding.staleness import WARN, check_fiscal_split_freshness

        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == WARN

    def test_unreadable_listing_is_warn(self, db_session):
        from seeding.staleness import WARN, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        db_session.add(_job(1, None, status="unreachable(ConnectError)"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == WARN and "unreachable" in f.message

    def test_an_empty_framework_object_is_not_a_split(self, db_session):
        from models import FiscalSummary
        from seeding.staleness import FAIL, check_fiscal_split_freshness

        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2026/27",
                unit="KES",
                meta={"split_basis": "treasury_fiscal_framework", "fiscal_framework": {}},
            )
        )
        db_session.add(_job(1, "FY 2026/27"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == FAIL

    def test_a_listing_that_lost_its_newest_edition_is_not_ok(self, db_session):
        """Split published through FY 2026/27, listing now tops out at FY
        2025/26: the source of the newest split has gone from the listing."""
        from seeding.staleness import WARN, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        db_session.add(_job(1, "FY 2025/26"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == WARN

    def test_an_unparseable_listed_year_is_not_ok(self, db_session):
        from seeding.staleness import WARN, check_fiscal_split_freshness

        _split_row(db_session, "FY 2026/27")
        db_session.add(_job(1, "next year"))
        db_session.commit()
        [f] = check_fiscal_split_freshness(db_session, now=NOW)
        assert f.level == WARN

    def test_basis_constant_matches_the_parser(self):
        from seeding.staleness import FISCAL_SPLIT_BASIS

        assert FISCAL_SPLIT_BASIS == ff.FISCAL_FRAMEWORK_BASIS

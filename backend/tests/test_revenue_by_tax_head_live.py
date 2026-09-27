"""Revenue by tax head follows KRA's newest annual release (#243).

Before: the breakdown came from ONE configured URL — the FY 2024/25 press
release — so the nightly reported ``promoted:5/FY 2024/25`` and LIVE for
eleven weeks after KRA published FY 2025/26 (2026-07-10), and /budget kept
serving FY 2025/26 as the fixture's projections. KRA had moved the release: it
is no longer in the press-release listing but on
``/annual-revenue-performance-fy-2025-2026``, an iframe onto a dashboard app
whose figures live in the app's JS bundle.

Every fixture here is a real capture (2026-09-26): the kra.go.ke page, the
dashboard shell, the dashboard's JS bundle, the
press-release listing, and the FY 2024/25 release text already in the repo.
The bundle is the whole file: a 32 KB excerpt passed every test here while
the live run read nothing from the real one.
"""

from __future__ import annotations

import copy
import gzip
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from seeding.domains.revenue_by_source import kra_discovery as kd
from seeding.domains.revenue_by_source.fetcher import (
    _overlay_kra_breakdown,
    _overlay_kra_release,
)

KRA = Path(__file__).resolve().parent / "fixtures" / "kra"
PAGE_URL = "https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026"
BUNDLE_URL = "https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js"


def _bundle() -> str:
    """The WHOLE bundle as served (628,077 bytes, md5 31c3506f…), gzipped. An
    excerpt around the data object hid a locator bug that the real file
    exposed on the first live run."""
    with gzip.open(KRA / "fy2025_26_dashboard_bundle.js.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture()
def release():
    return kd.parse_dashboard_bundle(_bundle(), url=PAGE_URL, data_url=BUNDLE_URL)


def _before_fixture():
    """revenue_by_source.json as it stood before #243: FY 2025/26 projected."""
    return json.loads((KRA / "revenue_fixture_before_243.json").read_text())


# ── Reading the dashboard ───────────────────────────────────────────────────


def test_bundle_yields_kras_own_figures_by_name(release):
    assert release.fiscal_year == "FY 2025/26"
    got = {h: str(f.amount_bn) for h, f in release.heads.items()}
    assert got == {
        "PAYE": "598.807",
        "Corporation Tax": "347.066",
        "VAT": "355.255",
        "Excise Duty": "61.845",
        "Customs & Import Duty": "988.78",
    }
    assert (release.total_bn, release.domestic_bn, release.exchequer_bn) == (
        Decimal("2844"),
        Decimal("1851"),
        Decimal("2568"),
    )
    # The prior-year exchequer the fixture's FY 2024/25 residual is built on.
    assert release.previous_exchequer_bn == Decimal("2323")
    assert release.heads["Corporation Tax"].target_bn == Decimal("365.249")


def test_release_validates_against_its_own_totals(release):
    assert kd.validate_release(release) == []
    assert kd.residual_bn(release) == Decimal("216.247")


def test_a_misread_head_fails_kras_own_arithmetic():
    tampered = _bundle().replace("amount:598807e6", "amount:998807e6")
    bad = kd.parse_dashboard_bundle(tampered, url=PAGE_URL, data_url=BUNDLE_URL)
    problems = kd.validate_release(bad)
    assert problems and "leaves" in problems[0]


def test_a_dashboard_with_no_exchequer_figure_is_refused(release):
    release.exchequer_bn = None
    assert "dashboard states no exchequer revenue" in kd.validate_release(release)


# ── Discovery candidates ────────────────────────────────────────────────────


def test_slug_candidates_cover_the_year_that_just_ended():
    fys = [fy for fy, _ in kd.slug_candidates(date(2026, 9, 26))]
    assert fys == ["FY 2026/27", "FY 2025/26", "FY 2024/25"]


def test_listing_candidates_are_revenue_results_not_the_publishers_name():
    html = (KRA / "press_release_listing_2026-09-26.html").read_text(encoding="utf-8")
    titles = [t for _, t, _ in kd.listing_candidates(html)]
    assert titles[0] == "Customs Surpasses Revenue Target, Records Remarkable Kshs. 3.5 Billion Average Daily Collection"
    assert "KRA Grows Revenue by 6.8% Despite Tough Economic Environment" in titles
    assert not any("Revenue Authority" in t for t in titles)


# ── The overlay: its own year, every describing field, no zeros ────────────


def test_dashboard_overlay_replaces_projections_with_kras_actuals(release):
    out, status = _overlay_kra_release(_before_fixture(), release)
    assert status == "promoted:5/FY 2025/26 (dashboard, residual)"
    fy = {r["revenue_type"]: r for r in out if r["fiscal_year"] == "FY 2025/26"}
    table = {
        k: (r["basis"], r["amount_billion_kes"], r["target_billion_kes"], r["share_of_total_pct"])
        for k, r in fy.items()
    }
    assert table == {
        "PAYE": ("published", 598.81, None, 23.3),
        "Corporation Tax": ("published", 347.07, 365.25, 13.5),
        "VAT": ("published", 355.26, None, 13.8),
        "Excise Duty": ("published", 61.85, None, 2.4),
        "Customs & Import Duty": ("published", 988.78, None, 38.5),
        "Other Tax Revenue": ("residual", 216.25, None, 8.4),
    }
    # No note may still describe the projection the row used to hold.
    assert not any(r["notes"].startswith("Projected") for r in fy.values())
    assert all(r["source_url"] == PAGE_URL for r in fy.values())
    # Earlier years untouched.
    before = {(r["fiscal_year"], r["revenue_type"]): r for r in _before_fixture()}
    for r in out:
        if r["fiscal_year"] != "FY 2025/26":
            assert r == before[(r["fiscal_year"], r["revenue_type"])]


def test_prose_overlay_lands_on_its_own_year_not_the_newest_fixture_year():
    """RED before #243: a year the payload did not list fell back to
    ``max(fiscal_years)`` — a FY 2026/27 release was written onto FY 2025/26."""
    payload = _before_fixture()
    # 2,750B — within 10% of FY 2025/26's projected 2,815B, so the old code
    # reconciled it against the wrong year, passed, and returned
    # "promoted:5/FY 2025/26" with PAYE 700.0 stamped "published" on FY 2025/26.
    heads = {"PAYE": 700.0, "Corporation Tax": 420.0, "VAT": 440.0, "Excise Duty": 90.0,
             "Customs & Import Duty": 1100.0}
    out, status = _overlay_kra_breakdown(copy.deepcopy(payload), heads, "FY 2026/27")
    assert status == "promoted:5/FY 2026/27"
    fy2526 = [r for r in out if r["fiscal_year"] == "FY 2025/26"]
    assert fy2526 == [r for r in payload if r["fiscal_year"] == "FY 2025/26"]
    fy2627 = {r["revenue_type"]: r["amount_billion_kes"] for r in out if r["fiscal_year"] == "FY 2026/27"}
    assert fy2627 == heads


def test_prose_overlay_rewrites_what_describes_a_projected_row():
    """RED before #243: amount and basis moved, but the row kept its
    projection target and a note reading "Projected: …"."""
    payload = _before_fixture()
    heads = {"PAYE": 598.807, "Corporation Tax": 347.066, "VAT": 355.255,
             "Excise Duty": 61.845, "Customs & Import Duty": 988.78}
    out, status = _overlay_kra_breakdown(payload, heads, "FY 2025/26")
    assert status == "promoted:5/FY 2025/26"
    paye = next(r for r in out if r["fiscal_year"] == "FY 2025/26" and r["revenue_type"] == "PAYE")
    assert paye["target_billion_kes"] is None
    assert paye["notes"].startswith("KRA Annual Revenue Performance FY 2025/26: PAYE collected")


def test_a_new_year_from_prose_needs_every_head():
    out, status = _overlay_kra_breakdown(_before_fixture(), {"PAYE": 640.0}, "FY 2026/27")
    assert status.startswith("failed_validation: new year FY 2026/27 lacks")
    assert not any(r["fiscal_year"] == "FY 2026/27" for r in out)


def test_the_git_fixture_holds_exactly_what_the_release_says(release):
    """The fixture is the fallback a failed night serves, and the writer
    re-stamps its basis and target. If it still said "projected" for FY
    2025/26, one bad night would re-label KRA's published figures."""
    current = json.loads(
        (Path(__file__).resolve().parents[1] / "seeding" / "real_data" / "revenue_by_source.json").read_text()
    )
    out, _ = _overlay_kra_release(_before_fixture(), release)
    keys = list(current[0])
    assert current == [{k: r.get(k) for k in keys} for r in out]


# ── End to end: discovery finds FY 2025/26 although the configured URL is
#    last year's release ──────────────────────────────────────────────────


def _serve():
    page = (KRA / "fy2025_26_annual_page.html").read_text(encoding="utf-8")
    shell = (KRA / "fy2025_26_dashboard_shell.html").read_text(encoding="utf-8")
    listing = (KRA / "press_release_listing_2026-09-26.html").read_text(encoding="utf-8")
    prose = (KRA / "fy2024_25_press_release.txt").read_text(encoding="utf-8")
    bundle = _bundle()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.worldbank.org"):
            return httpx.Response(503, request=request)
        if url == PAGE_URL:
            return httpx.Response(200, text=page, headers={"content-type": "text/html"}, request=request)
        if url.rstrip("/") == "https://krarevenue2526testingdashboard.bolt.host":
            return httpx.Response(200, text=shell, headers={"content-type": "text/html"}, request=request)
        if url == BUNDLE_URL:
            return httpx.Response(200, text=bundle, headers={"content-type": "application/javascript"}, request=request)
        if url == kd.LISTING_URL:
            return httpx.Response(200, text=listing, headers={"content-type": "text/html"}, request=request)
        if "/news-center/press-release/2235-" in url or "/news-center/press-release/223" in url:
            return httpx.Response(200, text=f"<html><body>{prose}</body></html>",
                                  headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, text="not found", request=request)

    return handler


def test_nightly_promotes_fy2025_26_and_records_the_edition(tmp_path, monkeypatch):
    """RED before #243: with SEED_KRA_REVENUE_URL on the FY 2024/25 release,
    the run promoted FY 2024/25, left FY 2025/26 as projections, and recorded
    no publisher edition at all."""
    import seeding.domains.revenue_by_source.kra_discovery as kdm
    from seeding import freshness
    from seeding.config import SeedingSettings
    from seeding.domains.revenue_by_source import fetcher
    from seeding.http_client import SeedingHttpClient

    fixture = tmp_path / "revenue_by_source.json"
    fixture.write_text(json.dumps(_before_fixture()))
    settings = SeedingSettings(
        storage_path=tmp_path / "s", cache_path=tmp_path / "c", log_path=tmp_path / "l" / "x.log",
        http_cache_enabled=False, rate_limit="1000/sec", max_retries=1, retry_backoff=0.01,
        revenue_by_source_dataset_url=f"file://{fixture}",
        kra_revenue_url="https://www.kra.go.ke/news-center/press-release/2235-kra-grows-revenue-by-6-8-despite-tough-economic-environment-4",
        enrich_with_worldbank=False,
    )
    settings.ensure_directories()
    real = kdm.slug_candidates
    monkeypatch.setattr(kdm, "slug_candidates", lambda today: real(date(2026, 9, 26)))
    freshness.reset("revenue_by_source")
    inner = httpx.Client(transport=httpx.MockTransport(_serve()))
    with SeedingHttpClient(settings, cache=None, client=inner) as client:
        payload = fetcher.fetch_revenue_payload(client, settings)

    paye = next(r for r in payload if r["fiscal_year"] == "FY 2025/26" and r["revenue_type"] == "PAYE")
    assert (paye["basis"], paye["amount_billion_kes"]) == ("published", 598.81)
    mode = freshness.get("revenue_by_source")
    assert mode["mode"] == "live" and "FY 2025/26" in mode["detail"]
    edition = freshness.get_publisher_edition("revenue_by_source")
    assert edition["edition"] == "FY 2025/26" and edition["url"] == PAGE_URL


# ── The gate ────────────────────────────────────────────────────────────────


def _seed_revenue(db_session, published_years):
    from models import RevenueBySource

    for fy in ("FY 2024/25", "FY 2025/26"):
        for head in kd.PUBLISHED_HEADS:
            published = fy in published_years
            db_session.add(RevenueBySource(
                fiscal_year=fy, revenue_type=head, category="tax",
                amount_billion_kes=100 if published else None,
                target_billion_kes=None if published else 120,
                meta={"basis": "published" if published else "projected"},
            ))


def _job(db_session, edition):
    from models import IngestionJob, IngestionStatus

    db_session.add(IngestionJob(
        domain="revenue_by_source", status=IngestionStatus.COMPLETED,
        started_at=datetime(2026, 9, 26, 2, 35),
        meta={"source_mode": "live", "publisher_edition": edition},
    ))
    db_session.commit()


def _revenue_finding(session):
    from seeding.staleness import run_all

    return [f for f in run_all(session) if f.label.startswith("Revenue by tax head")]


def test_gate_fails_while_the_newest_year_is_only_projections(db_session):
    """Production's state: FY 2025/26 held as projections, KRA has published it."""
    _seed_revenue(db_session, {"FY 2024/25"})
    _job(db_session, {"dataset": kd.DATASET, "edition": "FY 2025/26", "url": PAGE_URL})
    [finding] = _revenue_finding(db_session)
    assert finding.level == "FAIL"
    assert "newest we publish is FY 2024/25" in finding.message


def test_gate_ok_once_the_year_is_published(db_session):
    _seed_revenue(db_session, {"FY 2024/25", "FY 2025/26"})
    _job(db_session, {"dataset": kd.DATASET, "edition": "FY 2025/26", "url": PAGE_URL})
    [finding] = _revenue_finding(db_session)
    assert finding.level == "OK"


# ── What the first live run exposed ────────────────────────────────────────


def test_an_older_edition_promoting_does_not_hide_a_failed_newest_one(monkeypatch):
    """On the first live run the FY 2025/26 bundle read no heads, FY 2024/25's
    prose release promoted instead, and the run reported
    ``promoted:5/FY 2024/25`` — LIVE. The status must say the newest edition
    failed, so the domain records PARTIAL, not LIVE."""
    from seeding.domains.revenue_by_source import fetcher

    broken = kd.KraRelease(fiscal_year="FY 2025/26", url=PAGE_URL, shape="dashboard")
    older = kd.KraRelease(
        fiscal_year="FY 2024/25",
        url="https://www.kra.go.ke/news-center/press-release/2235-x",
        shape="press_release",
        heads={h: kd.HeadFigure(amount_bn=Decimal(str(v))) for h, v in {
            "PAYE": 560.963, "Corporation Tax": 304.833, "VAT": 327.336,
            "Excise Duty": 69.385, "Customs & Import Duty": 879.329}.items()},
    )
    monkeypatch.setattr(
        fetcher, "discover_kra_releases",
        lambda client, settings: ([broken, older], "FY 2025/26", PAGE_URL),
    )
    _, status = fetcher._apply_kra_live(_before_fixture(), None, None)
    assert status.startswith("newest_edition_not_promoted(FY 2025/26: FY 2025/26 dashboard: heads not found")
    assert not status.startswith("promoted")


def test_re_promoting_an_unchanged_published_figure_keeps_its_note():
    """The fixture's FY 2024/25 notes carry performance and growth that the
    prose parse does not; the live run rewrote five of them to the bare
    "…collected KES 560.963B" form."""
    payload = _before_fixture()
    heads = {"PAYE": 560.963, "Corporation Tax": 304.833, "VAT": 327.336,
             "Excise Duty": 69.385, "Customs & Import Duty": 879.329}
    before = {r["revenue_type"]: r["notes"] for r in payload if r["fiscal_year"] == "FY 2024/25"}
    out, status = _overlay_kra_breakdown(payload, heads, "FY 2024/25")
    assert status == "promoted:5/FY 2024/25"
    after = {r["revenue_type"]: r["notes"] for r in out if r["fiscal_year"] == "FY 2024/25"}
    assert after == before
    assert after["PAYE"] == "KRA Annual Performance FY 2024/25: PAYE collected KES 560.963B, performance 99.0%, growth 3.3%"

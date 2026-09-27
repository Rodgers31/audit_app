"""Find and read KRA's newest ANNUAL revenue performance release (#243).

WHY THIS EXISTS
---------------
The per-tax-head breakdown came from ONE configured URL
(``SEED_KRA_REVENUE_URL``). It pointed at the FY 2024/25 press release, so
every nightly re-read last year's figures and reported
``KRA overlay: promoted:5/FY 2024/25`` — LIVE, [OK] — while KRA had published
FY 2025/26 on 2026-07-10. And that edition could not have been found by
watching the press-release listing: KRA moved it.

KRA has published the annual result in two shapes:

* FY 2024/25 and earlier — a press release in
  ``/news-center/press-release/<id>-<slug>`` whose PROSE names each head
  ("PAYE collected Kshs 560.963 Billion…"). Read by ``kra_parser``.
* FY 2025/26 — a standalone page ``/annual-revenue-performance-fy-2025-2026``
  whose body is only an ``<iframe>`` onto a dashboard app. The figures are a
  data object in the app's JavaScript bundle::

      sr={metadata:{fiscalYear:"FY 2025/2026",…},
          revenueStreams:{…items:[{name:"PAYE",amount:598807e6,growth:6.7,
                                   performanceRate:91.8,…}, …]},
          customsVsDomestic:{domestic:{value:1851e9,…},
                             customs:{value:98878e7,…,performanceRate:100.8}},
          exchequerVsAgency:{exchequer:{collected:2568e9,…,
                                        previousFYCollection:2323e9},…}, …}

  Structured, so it is read by name — never by proximity in prose.

Discovery therefore takes every candidate it can find and ranks them by the
fiscal year each one turns out to be ABOUT:

1. the annual-performance slug, probed for the FY that most recently ended,
   the one before, and the current one (cheap 404s otherwise);
2. press releases on the listing dated July-September whose title mentions
   revenue (the season KRA reports the year just closed);
3. the configured ``kra_revenue_url``, if any — one candidate, not the answer.

Nothing here validates figures for publication; ``validate_release`` does,
against KRA's OWN stated totals from the same release.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

logger = logging.getLogger("seeding.revenue_by_source.kra_discovery")

KRA_BASE = "https://www.kra.go.ke"
LISTING_URL = f"{KRA_BASE}/news-center/press-release"
ANNUAL_SLUG = "annual-revenue-performance-fy-{y1}-{y2}"

#: ``ingestion_jobs.meta.publisher_edition.dataset`` for this series.
DATASET = "kra_annual_revenue_performance"

#: Dashboard stream name -> the fixture's revenue_type. Only these five are
#: heads of the published series; betting and digital-service taxes are
#: inside "Other Tax Revenue" in every earlier year and stay there.
DASHBOARD_HEADS: Dict[str, str] = {
    "PAYE": "PAYE",
    "Corporation Tax": "Corporation Tax",
    "Domestic VAT": "VAT",
    "Domestic Excise": "Excise Duty",
}
CUSTOMS_HEAD = "Customs & Import Duty"
RESIDUAL_HEAD = "Other Tax Revenue"
PUBLISHED_HEADS = ("PAYE", "Corporation Tax", "VAT", "Excise Duty", CUSTOMS_HEAD)

_BILLION = Decimal("1000000000")
_JS_NUM = r"(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)"


@dataclass
class HeadFigure:
    amount_bn: Decimal
    growth_pct: Optional[Decimal] = None
    performance_pct: Optional[Decimal] = None
    target_bn: Optional[Decimal] = None


@dataclass
class KraRelease:
    """One KRA annual release, as read. Totals are KRA's own statements."""

    fiscal_year: str  # canonical "FY 2025/26"
    url: str
    shape: str  # "dashboard" | "press_release"
    heads: Dict[str, HeadFigure] = field(default_factory=dict)
    total_bn: Optional[Decimal] = None
    domestic_bn: Optional[Decimal] = None
    exchequer_bn: Optional[Decimal] = None
    previous_exchequer_bn: Optional[Decimal] = None
    data_url: Optional[str] = None  # the bundle the figures were read from


# ─────────────────────────────────────────────────────────────────────────
# Fiscal-year helpers
# ─────────────────────────────────────────────────────────────────────────


def canonical_fy(y1: int) -> str:
    return f"FY {y1}/{str(y1 + 1)[-2:]}"


def fy_from_text(text: str) -> Optional[str]:
    """First "FY 2025/2026", "FY2025/26", "2025/26" style pair in ``text``
    whose second year is the successor of the first."""
    for m in re.finditer(r"(?<!\d)(20\d{2})\s*[/-]\s*(20\d{2}|\d{2})(?!\d)", text or ""):
        y1 = int(m.group(1))
        raw = m.group(2)
        y2 = int(raw) if len(raw) == 4 else (y1 // 100) * 100 + int(raw)
        if y2 == y1 + 1:
            return canonical_fy(y1)
    return None


def slug_candidates(today: date) -> List[Tuple[str, str]]:
    """``(fiscal_year, url)`` for the annual-performance slug of the FY that
    most recently ended, the one before it, and the current one."""
    ended = today.year - 1 if today.month >= 7 else today.year - 2
    out = []
    for y1 in (ended + 1, ended, ended - 1):
        out.append(
            (canonical_fy(y1), f"{KRA_BASE}/" + ANNUAL_SLUG.format(y1=y1, y2=y1 + 1))
        )
    return out


# ─────────────────────────────────────────────────────────────────────────
# Press-release listing
# ─────────────────────────────────────────────────────────────────────────

_LISTING_ITEM_RE = re.compile(
    r'href="(?P<href>/news-center/press-release/(?P<id>\d+)-[^"]+)"'
    r".{0,800}?<p>[A-Z ]+ (?P<d>\d\d)/(?P<m>\d\d)/(?P<y>\d{4})</p>\s*"
    r'<p class="title">(?P<title>[^<]+)',
    re.DOTALL,
)


def listing_candidates(html: str) -> List[Tuple[date, str, str]]:
    """``(published, title, url)`` for press releases that could be an annual
    revenue result: dated July-September and mentioning revenue."""
    out: List[Tuple[date, str, str]] = []
    seen = set()
    for m in _LISTING_ITEM_RE.finditer(html or ""):
        try:
            published = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            continue
        title = " ".join(m.group("title").split())
        if published.month not in (7, 8, 9):
            continue
        # "Kenya Revenue Authority …" is the publisher's name, not a result.
        if not re.search(r"revenue(?!\s+authority)", title, re.IGNORECASE):
            continue
        url = urljoin(KRA_BASE, m.group("href"))
        if url in seen:
            continue
        seen.add(url)
        out.append((published, title, url))
    out.sort(reverse=True)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Dashboard bundle
# ─────────────────────────────────────────────────────────────────────────


def iframe_src(html: str) -> Optional[str]:
    m = re.search(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html or "", re.IGNORECASE)
    return m.group(1) if m else None


def module_script_src(html: str) -> Optional[str]:
    m = re.search(
        r"<script[^>]+type=[\"']module[\"'][^>]+src=[\"']([^\"']+\.js)[\"']",
        html or "",
        re.IGNORECASE,
    )
    if not m:
        m = re.search(r"<script[^>]+src=[\"']([^\"']+\.js)[\"']", html or "", re.IGNORECASE)
    return m.group(1) if m else None


def _num(token: str) -> Optional[Decimal]:
    try:
        return Decimal(token)
    except (InvalidOperation, ValueError):
        return None


def _bn(token: Optional[str]) -> Optional[Decimal]:
    value = _num(token) if token is not None else None
    return value / _BILLION if value is not None else None


def _field(obj: str, name: str) -> Optional[str]:
    m = re.search(rf"\b{name}:{_JS_NUM}", obj)
    return m.group(1) if m else None


def _object_after(src: str, anchor: str, start_at: int = 0) -> Optional[str]:
    """The balanced ``{…}`` that follows the first ``anchor`` at or after
    ``start_at`` in minified JS (strings are skipped so a "}" inside prose
    does not close the object)."""
    i = src.find(anchor, start_at)
    if i == -1:
        return None
    start = src.find("{", i + len(anchor) - 1)
    if start == -1:
        return None
    depth = 0
    quote: Optional[str] = None
    k = start
    while k < len(src):
        ch = src[k]
        if quote:
            if ch == "\\":
                k += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start : k + 1]
        k += 1
    return None


def parse_dashboard_bundle(js: str, *, url: str, data_url: str) -> Optional[KraRelease]:
    """Read the data object out of KRA's annual-performance dashboard bundle.

    Returns ``None`` when the object is not there. Every figure is taken by its
    field name; a figure that is not present stays ``None`` — nothing is
    estimated here.
    """
    meta = _object_after(js, "metadata:{")
    if meta is None:
        return None
    fy_m = re.search(r'fiscalYear:"([^"]+)"', meta)
    fy = fy_from_text(fy_m.group(1)) if fy_m else None
    if fy is None:
        return None
    # The data object is the one whose metadata we just read: the "={" that
    # opens it is the last one before "metadata:{". Anchoring the search
    # THERE matters — the full 628 KB bundle has its first "={" at offset 910,
    # inside library code, and reading from there returned no heads at all
    # (the 32 KB excerpt this was first tested on hid that).
    data_start = js.rfind("={", 0, js.find("metadata:{"))
    if data_start == -1:
        return None
    data = _object_after(js, "={", data_start)
    if data is None or "metadata:{" not in data[:40]:
        return None

    release = KraRelease(fiscal_year=fy, url=url, shape="dashboard", data_url=data_url)

    streams = _object_after(data, "revenueStreams:{") or ""
    for item in re.finditer(r"\{name:\"([^\"]+)\",amount:" + _JS_NUM + r"([^{}]*)", streams):
        name, amount, rest = item.group(1), item.group(2), item.group(3)
        head = DASHBOARD_HEADS.get(name)
        if head is None:
            continue
        release.heads[head] = HeadFigure(
            amount_bn=_bn(amount),  # type: ignore[arg-type]
            growth_pct=_num(_field(rest, "growth") or "x"),
            performance_pct=_num(_field(rest, "performanceRate") or "x"),
            target_bn=_bn(_field(rest, "target")),
        )

    cvd = _object_after(data, "customsVsDomestic:{") or ""
    customs = _object_after(cvd, "customs:{")
    domestic = _object_after(cvd, "domestic:{")
    if customs:
        value = _bn(_field(customs, "value"))
        if value is not None:
            release.heads[CUSTOMS_HEAD] = HeadFigure(
                amount_bn=value,
                growth_pct=_num(_field(customs, "growth") or "x"),
                performance_pct=_num(_field(customs, "performanceRate") or "x"),
            )
    if domestic:
        release.domestic_bn = _bn(_field(domestic, "value"))

    overview = _object_after(data, "overviewMetrics:{") or ""
    total = _object_after(overview, "totalRevenue:{")
    if total:
        release.total_bn = _bn(_field(total, "value"))

    eva = _object_after(data, "exchequerVsAgency:{") or ""
    exchequer = _object_after(eva, "exchequer:{")
    if exchequer:
        release.exchequer_bn = _bn(_field(exchequer, "collected"))
        release.previous_exchequer_bn = _bn(_field(exchequer, "previousFYCollection"))
    return release


# ─────────────────────────────────────────────────────────────────────────
# Validation — against KRA's own totals in the same release
# ─────────────────────────────────────────────────────────────────────────

#: Domestic + Customs must reproduce KRA's stated total within this share.
TOTAL_TOLERANCE = Decimal("0.01")
#: The residual (exchequer less the five heads) held 7.8%-9.6% of exchequer
#: in FY 2022/23-FY 2024/25. Outside 0-20% the heads or the exchequer figure
#: are not what we think they are.
RESIDUAL_MAX_SHARE = Decimal("0.20")


def validate_release(release: KraRelease) -> List[str]:
    """Why ``release`` must not be published; empty when it may be.

    Every check compares figures from the SAME release, so a mis-read field
    has to agree with KRA's own arithmetic to get through.
    """
    problems: List[str] = []
    missing = [h for h in PUBLISHED_HEADS if h not in release.heads]
    if missing:
        problems.append(f"heads not found: {missing}")
    for head, fig in release.heads.items():
        if fig.amount_bn is None or fig.amount_bn <= 0:
            problems.append(f"{head}: non-positive amount {fig.amount_bn}")
    if problems:
        return problems

    domestic_heads = sum(
        (release.heads[h].amount_bn for h in PUBLISHED_HEADS if h != CUSTOMS_HEAD),
        Decimal("0"),
    )
    five = domestic_heads + release.heads[CUSTOMS_HEAD].amount_bn

    if release.shape == "dashboard":
        # The dashboard states every total, so require them all.
        if release.domestic_bn is None or release.total_bn is None:
            problems.append("dashboard states no domestic/total revenue")
        else:
            combined = release.domestic_bn + release.heads[CUSTOMS_HEAD].amount_bn
            if abs(combined - release.total_bn) > TOTAL_TOLERANCE * release.total_bn:
                problems.append(
                    f"domestic {release.domestic_bn} + customs "
                    f"{release.heads[CUSTOMS_HEAD].amount_bn} = {combined} does not "
                    f"reproduce KRA's total {release.total_bn}"
                )
            if domestic_heads > release.domestic_bn:
                problems.append(
                    f"PAYE+Corporation+VAT+Excise = {domestic_heads} exceeds "
                    f"domestic revenue {release.domestic_bn}"
                )
        if release.exchequer_bn is None:
            problems.append("dashboard states no exchequer revenue")
    if release.exchequer_bn is not None:
        residual = release.exchequer_bn - five
        if residual < 0 or residual > RESIDUAL_MAX_SHARE * release.exchequer_bn:
            problems.append(
                f"exchequer {release.exchequer_bn} less the five heads {five} "
                f"leaves {residual}, outside 0-{RESIDUAL_MAX_SHARE:.0%} of exchequer"
            )
    return problems


def residual_bn(release: KraRelease) -> Optional[Decimal]:
    """Exchequer revenue less the five heads — the same subtraction the
    fixture's earlier "Other Tax Revenue" rows declare — or ``None`` when the
    release states no exchequer figure. Never a zero standing in for it."""
    if release.exchequer_bn is None:
        return None
    return release.exchequer_bn - sum(
        (release.heads[h].amount_bn for h in PUBLISHED_HEADS), Decimal("0")
    )


__all__ = [
    "CUSTOMS_HEAD",
    "DATASET",
    "HeadFigure",
    "KraRelease",
    "LISTING_URL",
    "PUBLISHED_HEADS",
    "RESIDUAL_HEAD",
    "canonical_fy",
    "fy_from_text",
    "iframe_src",
    "listing_candidates",
    "module_script_src",
    "parse_dashboard_bundle",
    "residual_bn",
    "slug_candidates",
    "validate_release",
]

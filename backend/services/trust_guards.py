"""Lightweight trust/plausibility alerts for production (April 2026).

Each check returns a list of human-readable notes suitable for surfacing
in an API response's ``_meta.quality_notes`` field, and emits a WARNING
log line when a threshold is crossed. Keep every check pure — no DB
writes, no external calls — so they're safe to run inside request
handlers behind ``@cached`` decorators.

Callers are expected to:

1. Pass the already-aggregated data (sectors list, totals, etc.) to
   the relevant checker.
2. Merge the returned notes into ``_response_meta(quality_notes=...)``
   so the frontend can show a single "data quality" badge.
3. Trust the log side-channel (WARNING level with the "TRUST:" prefix)
   for ops alerting — Datadog / CloudWatch filters on that prefix.

None of the checks raise. A check failing to run should *never* take
down an endpoint — degrade silently and emit a WARNING.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
import statistics
from typing import Iterable, Optional, Sequence

logger = logging.getLogger("trust_guards")

# Prefix every WARNING we emit so ops can filter cleanly.
_TRUST_PREFIX = "TRUST"


def _warn(msg: str) -> None:
    """Emit a tagged WARNING. Kept as a single helper so tests and ops
    filters only need to key off one string."""
    logger.warning("%s: %s", _TRUST_PREFIX, msg)


# ── Budget sector checks ─────────────────────────────────────────────


# Real Kenyan county spending is dominated by Personnel Emoluments
# (~50%). If a sector breakdown lacks this category entirely, the
# numbers reflect modeled allocations (CRA formula) rather than
# observed execution, and the UI should say so.
_WAGE_CATEGORY_ALIASES = {
    "personnel emoluments",
    "personnel",
    "wages & salaries",
    "wages and salaries",
    "salaries & wages",
    "compensation of employees",
}


def check_budget_sectors(sectors: Sequence[dict]) -> list[str]:
    """Inspect a /budget/overview-style sector list for credibility
    red flags. Returns a list of human-readable notes (empty if clean).

    Flags:
    - Empty sector list (nothing to display).
    - Missing Personnel Emoluments category (real county data almost
      always has this as the single largest line).
    - Suspiciously uniform utilization across sectors (σ < 1.0%),
      which is a hallmark of modeled or formula-generated data.
    """
    notes: list[str] = []
    if not sectors:
        notes.append("No sector data available for the selected period.")
        _warn("budget sector list is empty")
        return notes

    # 1. Personnel Emoluments presence check.
    names = {str(s.get("sector", "")).strip().lower() for s in sectors}
    if not (names & _WAGE_CATEGORY_ALIASES):
        notes.append(
            "Personnel Emoluments — typically ~50% of county spending — "
            "is not broken out as a separate category. Figures shown "
            "reflect non-wage allocations only."
        )
        # This is structural, not an anomaly worth a WARNING every
        # request. It's only useful in the response.

    # 2. Utilization uniformity check.
    utilization = [
        float(s.get("utilization", 0))
        for s in sectors
        if isinstance(s.get("utilization"), (int, float))
        and s.get("utilization") is not None
    ]
    if len(utilization) >= 3:
        try:
            stdev = statistics.pstdev(utilization)
        except statistics.StatisticsError:
            stdev = None
        if stdev is not None and stdev < 1.0:
            msg = (
                f"Utilization is suspiciously uniform across sectors "
                f"(σ={stdev:.2f}%). The underlying data may be modeled "
                f"rather than observed."
            )
            notes.append(msg)
            _warn(f"budget/overview utilization uniformity σ={stdev:.2f}")

    return notes


# ── Debt reconciliation check ────────────────────────────────────────


def reconcile_debt_totals(
    primary_total_kes: float,
    secondary_total_kes: float,
    *,
    primary_label: str,
    secondary_label: str,
    threshold_pct: float = 5.0,
) -> tuple[str, float, list[str]]:
    """Compare two independent debt totals and classify divergence.

    Returns (status, diff_pct, notes) where:
    - status ∈ {"consistent", "divergent", "unchecked"}
    - diff_pct is |primary - secondary| / max(|primary|, |secondary|) * 100
    - notes is surfaced to the UI when status != "consistent".

    Emits a WARNING when status == "divergent" so ops monitoring picks
    it up without a separate alarm wiring.
    """
    notes: list[str] = []
    if primary_total_kes <= 0 or secondary_total_kes <= 0:
        notes.append(
            f"Cannot reconcile: one of the debt sources "
            f"({primary_label} / {secondary_label}) returned zero."
        )
        return "unchecked", 0.0, notes

    diff_pct = (
        abs(primary_total_kes - secondary_total_kes)
        / max(primary_total_kes, secondary_total_kes)
        * 100.0
    )
    if diff_pct > threshold_pct:
        msg = (
            f"{primary_label} (KES {primary_total_kes / 1e12:.2f}T) and "
            f"{secondary_label} (KES {secondary_total_kes / 1e12:.2f}T) "
            f"diverge by {diff_pct:.1f}% — exceeds {threshold_pct:.0f}% "
            f"reconciliation threshold."
        )
        notes.append(msg)
        _warn(msg)
        return "divergent", diff_pct, notes

    return "consistent", diff_pct, notes


# ── Debt composition plausibility ────────────────────────────────────


def check_debt_composition(
    *,
    total: Optional[float],
    external: Optional[float],
    domestic: Optional[float],
    debt_to_gdp: Optional[float] = None,
    tolerance_pct: float = 2.0,
) -> list[str]:
    """Objective plausibility checks on the national-debt composition.

    Returns notes (empty if clean). Deliberately makes NO assumption about
    which side *should* be larger (that changes over time) — it only flags
    structural impossibilities and out-of-band ratios:
      - negative components,
      - external + domestic exceeding the headline total (cannot reconcile),
      - external + domestic covering well under the total (uncategorised gap),
      - debt-to-GDP outside a 30-120% plausible band.
    """
    notes: list[str] = []
    for label, v in (("external", external), ("domestic", domestic), ("total", total)):
        if v is not None and v < 0:
            notes.append(f"Implausible: {label} debt is negative.")
            _warn(f"debt composition: {label} is negative ({v})")
    if total and total > 0 and external is not None and domestic is not None:
        split = external + domestic
        if split > total * (1 + tolerance_pct / 100.0):
            msg = (
                "External + domestic debt exceed the headline total — the "
                "composition does not reconcile."
            )
            notes.append(msg)
            _warn(msg)
        elif split < total * (1 - tolerance_pct / 100.0):
            covered = split / total * 100.0
            notes.append(
                f"External + domestic cover only {covered:.0f}% of the headline "
                "total; the remainder is uncategorised."
            )
    if (
        debt_to_gdp is not None
        and debt_to_gdp > 0
        and not (30.0 <= debt_to_gdp <= 120.0)
    ):
        msg = f"Debt-to-GDP {debt_to_gdp:.1f}% is outside the plausible 30-120% band."
        notes.append(msg)
        _warn(msg)
    return notes


# ── Fiscal-summary plausibility (budget / revenue) ───────────────────


# Plausibility bands for Kenya national fiscal aggregates, in BILLION KES,
# for the mid-2020s. Wide enough to admit real year-on-year revisions,
# tight enough to catch a parser that grabbed the wrong table row or got
# the units wrong (raw KES instead of billions → a ~1e9× blow-up; trillions
# → a ~1e-3 collapse). Revisit the upper bounds as the economy grows.
_FISCAL_BANDS_BILLION: dict[str, tuple[float, float]] = {
    "appropriated_budget": (2_000.0, 8_000.0),
    "total_revenue": (1_000.0, 5_000.0),
    "tax_revenue": (800.0, 4_500.0),
    "non_tax_revenue": (30.0, 1_500.0),
    "total_borrowing": (0.0, 3_000.0),
    "debt_service_cost": (400.0, 4_000.0),
    "development_spending": (100.0, 2_000.0),
    "recurrent_spending": (800.0, 5_000.0),
    "county_allocation": (150.0, 1_200.0),
}


def check_fiscal_summary(row) -> list[str]:
    """Objective plausibility + reconciliation checks for ONE fiscal-year
    summary row (values in billion KES). Returns notes (empty if clean).

    ``row`` may be a dict (the API's ``current`` row) OR an object with the
    same attributes (the seed-time ``FiscalSummaryRecord`` dataclass) — field
    access is normalised so the SAME guard runs in both places.

    Every note represents a HARD inconsistency suitable for quarantine: a
    value outside its plausible band (the classic unit-slip / wrong-row
    parse), or a component breakdown that does not reconcile to its total.
    Used both at seed time (quarantine the row, keep last-known-good) and at
    request time (surface as a data-quality caveat). Pure; never raises.
    """
    notes: list[str] = []

    def _get(field: str):
        if isinstance(row, dict):
            return row.get(field)
        return getattr(row, field, None)

    fy = _get("fiscal_year") or "?"

    def _num(field: str) -> Optional[float]:
        v = _get(field)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # 1. Plausibility bands (unit-safety + wrong-row detection).
    for field, (lo, hi) in _FISCAL_BANDS_BILLION.items():
        v = _num(field)
        if v is None:
            continue
        if not (lo <= v <= hi):
            msg = (
                f"{fy}: {field}={v:,.0f}B is outside the plausible "
                f"[{lo:,.0f}, {hi:,.0f}]B band."
            )
            notes.append(msg)
            _warn(msg)

    # 2. Revenue reconciliation: tax + non-tax ≈ total revenue (±5%).
    tax, nontax, total = _num("tax_revenue"), _num("non_tax_revenue"), _num("total_revenue")
    if tax is not None and nontax is not None and total and total > 0:
        if abs((tax + nontax) - total) > 0.05 * total:
            msg = (
                f"{fy}: tax ({tax:,.0f}) + non-tax ({nontax:,.0f}) = "
                f"{tax + nontax:,.0f}B does not reconcile to total_revenue "
                f"({total:,.0f}B) within 5%."
            )
            notes.append(msg)
            _warn(msg)

    # 3. Spending cannot exceed the budget: recurrent + development ≤ budget.
    rec, dev, budget = (
        _num("recurrent_spending"),
        _num("development_spending"),
        _num("appropriated_budget"),
    )
    if rec is not None and dev is not None and budget and budget > 0:
        if (rec + dev) > 1.05 * budget:
            msg = (
                f"{fy}: recurrent ({rec:,.0f}) + development ({dev:,.0f}) = "
                f"{rec + dev:,.0f}B exceeds the appropriated budget "
                f"({budget:,.0f}B)."
            )
            notes.append(msg)
            _warn(msg)

    return notes


# ── Revenue-breakdown plausibility (per tax head) ────────────────────


# No single tax head realistically exceeds this (billion KES, mid-2020s).
# Broad on purpose: the point is catching a parse that grabbed a wrong/huge
# number, not policing normal variation.
_REVENUE_HEAD_MAX_BILLION = 3_000.0


def check_revenue_breakdown(
    by_type: dict,
    expected_total: Optional[float] = None,
    *,
    tolerance_pct: float = 10.0,
) -> list[str]:
    """Plausibility + reconciliation checks on a parsed per-tax-head revenue
    breakdown (``{revenue_type: amount_billion}``). Returns notes (empty if
    clean). Any note means the parse should be QUARANTINED (not promoted),
    keeping the fixture. Pure; never raises.

    Checks: each head non-negative and under a sane cap; and — when an
    ``expected_total`` is given (e.g. the fixture's known tax-revenue total) —
    the heads must sum to it within ``tolerance_pct`` (a garbled/partial parse
    won't reconcile and is rejected).
    """
    notes: list[str] = []
    if not by_type:
        notes.append("Revenue breakdown is empty.")
        return notes

    total = 0.0
    for rtype, amount in by_type.items():
        try:
            v = float(amount)
        except (TypeError, ValueError):
            notes.append(f"Revenue '{rtype}' is non-numeric.")
            _warn(f"revenue breakdown: {rtype} non-numeric ({amount!r})")
            continue
        if v < 0:
            notes.append(f"Revenue '{rtype}' is negative.")
            _warn(f"revenue breakdown: {rtype} negative ({v})")
        if v > _REVENUE_HEAD_MAX_BILLION:
            msg = (
                f"Revenue '{rtype}'={v:,.0f}B exceeds the "
                f"{_REVENUE_HEAD_MAX_BILLION:,.0f}B per-head cap."
            )
            notes.append(msg)
            _warn(msg)
        total += max(v, 0.0)

    if expected_total and expected_total > 0:
        if abs(total - expected_total) > (tolerance_pct / 100.0) * expected_total:
            msg = (
                f"Revenue breakdown sums to {total:,.0f}B — does not reconcile "
                f"to the expected {expected_total:,.0f}B within {tolerance_pct:.0f}%."
            )
            notes.append(msg)
            _warn(msg)

    return notes


# ── Coverage / staleness check ───────────────────────────────────────


_FY_START_RE = re.compile(r"(\d{4})")


def _fy_start_year(label: str | None) -> int | None:
    """Extract the start year from a label like 'FY2024/25' or
    'FY 2023/24' or '2024'. Returns None if unparseable."""
    if not label:
        return None
    m = _FY_START_RE.search(label)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def check_coverage_staleness(
    covers_through: str | None,
    *,
    current_fy_label: str,
    max_stale_fys: int = 1,
) -> list[str]:
    """Flag when the data we're about to serve is older than
    *max_stale_fys* fiscal years behind the current one.

    Example
    -------
    current_fy_label="FY2025/26", covers_through="FY2023/24",
    max_stale_fys=1 → 2 FY behind → produces a note AND a WARNING.
    """
    notes: list[str] = []
    cur = _fy_start_year(current_fy_label)
    cov = _fy_start_year(covers_through)

    if covers_through is None or cov is None:
        notes.append(
            "Coverage period is unknown — unable to verify freshness."
        )
        return notes

    if cur is None:
        # Can't compare without a reference. Degrade silently.
        return notes

    gap = cur - cov
    if gap > max_stale_fys:
        msg = (
            f"Data covers {covers_through}, but the current fiscal "
            f"year is {current_fy_label} ({gap} FY behind)."
        )
        notes.append(msg)
        _warn(msg)
    return notes


# ── Empty-period check ───────────────────────────────────────────────


def check_period_nonempty(
    row_count: int,
    *,
    endpoint: str,
    period_label: str | None,
) -> list[str]:
    """Flag when an endpoint that should have data for *period_label*
    returned zero rows. A silent empty response is a credibility
    landmine — the UI will show zero or a cryptic loading state."""
    if row_count > 0:
        return []
    msg = (
        f"{endpoint} returned 0 rows for "
        f"{period_label or 'the latest period'}; "
        f"downstream UI may render blank."
    )
    _warn(msg)
    return [msg]


# ── Implausible-total check ──────────────────────────────────────────


def check_plausible_total(
    value_kes: float,
    *,
    label: str,
    ceiling_kes: float,
) -> list[str]:
    """Returns a note (and logs WARNING) when *value_kes* exceeds
    *ceiling_kes*. Complements the existing ``_check_plausibility``
    helper in main.py by exposing the warning to the UI as well."""
    if value_kes <= ceiling_kes:
        return []
    msg = (
        f"{label} = KES {value_kes / 1e12:.2f}T exceeds the plausibility "
        f"ceiling of KES {ceiling_kes / 1e12:.2f}T — review input data."
    )
    _warn(msg)
    return [msg]


# ── Source-freshness check (post-activation monitoring) ─────────────
#
# Once the live COB C-BIRR ingestion path is live, we want to know when
# the last successful fetch gets too old. COB publishes quarterly plus
# annually (≥ 1 PDF every ~90 days), so a 120-day gap means either:
#   1. The scraping heuristic has broken against a site refresh.
#   2. COB itself is down / has restructured (again).
#   3. Our nightly cron stopped running (!).
# Any of those should downgrade the /budget/overview badge to
# "estimated" — we'd rather be honest than optimistic.


def check_source_freshness(
    newest_fetch_date: Optional[_dt.datetime],
    *,
    label: str,
    max_age_days: int = 120,
    now: Optional[_dt.datetime] = None,
) -> list[str]:
    """Flag when the newest SourceDocument.fetch_date for a given
    dataset is older than *max_age_days*.

    This is the post-activation watchdog for the COB county budget
    feed: COB publishes quarterly + annually, so 120 days is the
    maximum natural gap between releases. Anything longer indicates
    the ingestion pipeline has quietly failed.

    Parameters
    ----------
    newest_fetch_date
        The max(SourceDocument.fetch_date) for the dataset — i.e. the
        timestamp of our latest *successful* fetch. None means we've
        never ingested anything (fresh DB or totally-failed pipeline).
    label
        Human label used in the note and the WARNING log.
    max_age_days
        Threshold. 120 is the recommended default for COB county data.
    now
        Override for deterministic tests. Defaults to UTC now.
    """
    notes: list[str] = []
    _now = now or _dt.datetime.now(_dt.timezone.utc)

    if newest_fetch_date is None:
        msg = f"{label}: no successful fetch has ever been recorded."
        _warn(msg)
        notes.append(msg)
        return notes

    # Normalise to aware UTC so timedelta math is safe.
    if newest_fetch_date.tzinfo is None:
        newest_fetch_date = newest_fetch_date.replace(tzinfo=_dt.timezone.utc)
    else:
        newest_fetch_date = newest_fetch_date.astimezone(_dt.timezone.utc)

    age_days = (_now - newest_fetch_date).days
    if age_days > max_age_days:
        msg = (
            f"{label}: last fetch was {age_days} days ago "
            f"(exceeds {max_age_days}-day freshness window). "
            f"Review the COB ingestion pipeline."
        )
        _warn(msg)
        notes.append(msg)
    return notes


# ── Category-coverage check (Total-only detection) ──────────────────
#
# When the CoBQuarterlyReportParser extracts only the aggregate
# "Total" table (the Recurrent / Development / Personnel Emoluments
# heuristics all missed), we still produce data — but it's not the
# rich breakdown the Budget page advertises. Flag so the badge stays
# honest about the partial extraction.


def check_category_coverage(
    categories: Iterable[str],
    *,
    require_pe: bool = True,
    require_recurrent_dev_split: bool = True,
) -> list[str]:
    """Flag when a county budget extraction yielded only 'Total' rows,
    or is missing the Recurrent/Development split, or is missing a
    Personnel Emoluments row.

    Returns an empty list when the extraction is healthy.
    """
    notes: list[str] = []
    cats = {
        str(c).strip().lower()
        for c in categories
        if isinstance(c, str) and c.strip()
    }
    if not cats:
        return notes  # handled by check_period_nonempty

    only_total = cats <= {"total", "total budget"}
    if only_total:
        msg = (
            "County budget extraction produced only aggregate Total rows "
            "— Recurrent, Development, and Personnel Emoluments tables "
            "were not found in the source PDF. The Budget page will show "
            "estimated figures for category breakdowns."
        )
        _warn(msg)
        notes.append(msg)
        return notes

    if require_recurrent_dev_split:
        has_recurrent = any("recurrent" in c for c in cats)
        has_development = any("development" in c for c in cats)
        if not (has_recurrent and has_development):
            notes.append(
                "Recurrent/Development split is incomplete — one or both "
                "sub-aggregate tables were not extracted from the source."
            )

    if require_pe:
        has_pe = any(
            ("personnel" in c) or ("emolument" in c) or (c in _WAGE_CATEGORY_ALIASES)
            for c in cats
        )
        if not has_pe:
            # This is a more specific cousin of the message emitted by
            # check_budget_sectors, kept separate so it fires even when
            # sectors[] is empty but the raw DB categories are not.
            notes.append(
                "Personnel Emoluments category missing from the source "
                "extraction."
            )
    return notes


# ── Repeated-fetch-failure check ─────────────────────────────────────
#
# When called from /budget/overview or an ops dashboard, this inspects
# the recent IngestionJob history for the counties_budget domain and
# alerts when consecutive runs failed — a clear signal that either the
# COB site is down or the scraper has broken.


def check_consecutive_fetch_failures(
    recent_statuses: Sequence[str],
    *,
    domain: str,
    threshold: int = 3,
) -> list[str]:
    """Given a chronological list of recent IngestionJob statuses for a
    domain (e.g. ``["completed", "failed", "failed", "failed"]``),
    emit a WARNING when the tail of the list contains >= *threshold*
    consecutive failures.

    Accepts any case / status token; treats anything not in
    {"completed","completed_with_errors"} as a failure.
    """
    notes: list[str] = []
    if not recent_statuses:
        return notes

    success_tokens = {"completed", "completed_with_errors"}
    tail_failures = 0
    for status in reversed(recent_statuses):
        if str(status).lower() in success_tokens:
            break
        tail_failures += 1

    if tail_failures >= threshold:
        msg = (
            f"{domain}: last {tail_failures} ingestion job(s) failed. "
            f"Investigate the upstream source and scraper heuristics."
        )
        _warn(msg)
        notes.append(msg)
    return notes


__all__ = [
    "check_budget_sectors",
    "reconcile_debt_totals",
    "check_coverage_staleness",
    "check_period_nonempty",
    "check_plausible_total",
    "check_source_freshness",
    "check_category_coverage",
    "check_consecutive_fetch_failures",
]

"""Layer 1 — the declarative source registry.

One entry per Tier-1 dataset: who publishes it, where discovery starts,
how often it appears, and how late it is allowed to be. The fetcher
(Layer 2) and the scheduler decide *when* to look and *where* from this
table; nothing downstream hardcodes a URL or a cadence.

Every URL and every lag figure here is copied from the
``kenya-data-sources`` skill's Tier-1 table and ``PUBLICATION_SCHEDULE``
— the registry deliberately invents nothing. If a source moves, fix it
here (and in the skill), not at a call site.

The registry also answers "when is the next publication expected?", which
the API uses to render an honest empty state ("annual, expected December–
April") instead of a bare blank panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

# ── Publication schedule ─────────────────────────────────────────────
# Verbatim from kenya-data-sources PUBLICATION_SCHEDULE. Month-day
# strings ("11-15") are calendar anchors, resolved against a concrete
# year by next_expected_window().
PUBLICATION_SCHEDULE: Dict[str, dict] = {
    "cob_qbirr": {
        "frequency": "quarterly",
        "lag_days": 45,
        # Q1 (Jul-Sep) report → check from Nov 15
        # Q2 (Oct-Dec) report → check from Feb 15
        # Q3 (Jan-Mar) report → check from May 15
        # Q4 (Apr-Jun) report → check from Aug 15
        "check_dates": ["11-15", "02-15", "05-15", "08-15"],
        "retry_days": 14,
    },
    "oag_county_audits": {
        "frequency": "annual",
        "lag_months": "6-9",
        # FY ending June → reports typically Dec-Mar
        "check_window": {"start": "12-01", "end": "04-30"},
        "check_interval_days": 7,
    },
    "oag_national_audits": {
        # Same statutory cycle as the county reports: the consolidated
        # national report ("Blue Book") covers the FY ended 30 June and
        # lands 6-9 months later.
        "frequency": "annual",
        "lag_months": "6-9",
        "check_window": {"start": "12-01", "end": "04-30"},
        "check_interval_days": 7,
    },
    "treasury_bps": {
        "frequency": "annual",
        "expected_month": "February",
        "check_window": {"start": "01-15", "end": "03-31"},
    },
    "treasury_qebr": {
        "frequency": "quarterly",
        "lag_days": 60,
        "check_dates": ["12-01", "03-01", "06-01", "09-01"],
    },
    "knbs_economic_survey": {
        "frequency": "annual",
        "expected_month": "May-June",
        "check_window": {"start": "04-15", "end": "07-31"},
    },
    "knbs_cpi": {
        "frequency": "monthly",
        "lag_days": 30,
    },
    "cbk_debt_bulletin": {
        "frequency": "monthly",
        "lag_days": 45,
    },
    "cbk_forex_rates": {
        "frequency": "daily",
        "lag_days": 1,
    },
    "cra_recommendations": {
        "frequency": "annual",
        "expected_month": "October-November",
    },
}


@dataclass(frozen=True)
class SourceDataset:
    """One dataset a Tier-1 publisher issues on a schedule."""

    dataset_id: str  # key into PUBLICATION_SCHEDULE
    publisher: str  # canonical publisher name (matches source_documents)
    publisher_url: str  # the publisher's site, from the Tier-1 table
    doc_type: str  # models.DocumentType name
    description: str
    # Where discovery starts. For WordPress sites this is the REST media
    # API; for others the listing page. Never a guessed deep link.
    discovery_urls: Tuple[str, ...] = ()
    # Which Layer-3 parser understands this dataset's documents. None
    # means "fetch and register only" — no extraction implemented yet.
    parser_id: Optional[str] = None
    # Substrings a discovered document URL/title must contain to belong
    # to this dataset (case-insensitive; empty = accept all).
    match_keywords: Tuple[str, ...] = ()


# ── Tier-1 registry ──────────────────────────────────────────────────
# Publishers and URLs from the kenya-data-sources Tier-1 table.
SOURCE_REGISTRY: Dict[str, SourceDataset] = {
    d.dataset_id: d
    for d in [
        SourceDataset(
            dataset_id="oag_national_audits",
            publisher="Office of the Auditor-General",
            publisher_url="https://www.oagkenya.go.ke",
            doc_type="AUDIT",
            description=(
                "Consolidated audit report on national government "
                "ministries, departments and agencies (the Blue Book)"
            ),
            discovery_urls=(
                "https://www.oagkenya.go.ke/wp-json/wp/v2/media"
                "?per_page=100&search=national+government",
            ),
            parser_id="oag_blue_book",
            match_keywords=("national-government",),
        ),
        SourceDataset(
            dataset_id="oag_county_audits",
            publisher="Office of the Auditor-General",
            publisher_url="https://www.oagkenya.go.ke",
            doc_type="AUDIT",
            description="County government and county assembly audit reports",
            discovery_urls=(
                "https://www.oagkenya.go.ke/wp-json/wp/v2/media"
                "?per_page=100&search=county",
            ),
            parser_id=None,  # county report parser not yet implemented
            match_keywords=("county",),
        ),
        SourceDataset(
            dataset_id="cob_qbirr",
            publisher="Controller of Budget",
            publisher_url="https://cob.go.ke",
            doc_type="BUDGET",
            description="Quarterly budget implementation review reports",
            discovery_urls=("https://cob.go.ke/reports/",),
            parser_id=None,
        ),
        SourceDataset(
            dataset_id="treasury_qebr",
            publisher="National Treasury",
            publisher_url="https://treasury.go.ke",
            doc_type="BUDGET",
            description="Quarterly economic and budgetary review",
            discovery_urls=("https://treasury.go.ke",),
            parser_id=None,
        ),
        SourceDataset(
            dataset_id="knbs_economic_survey",
            publisher="Kenya National Bureau of Statistics",
            publisher_url="https://knbs.or.ke",
            doc_type="REPORT",
            description="Annual Economic Survey",
            discovery_urls=("https://knbs.or.ke",),
            parser_id=None,
        ),
    ]
}


def _md(anchor: str, year: int) -> date:
    month, day = anchor.split("-")
    return date(year, int(month), int(day))


def next_expected_window(
    dataset_id: str, today: date
) -> Optional[dict]:
    """When the next publication of ``dataset_id`` is expected.

    Returns a machine-readable dict (never a hand-written sentence):
    ``{"dataset": ..., "publisher": ..., "cadence": ...,
    "window_start": iso-date, "window_end": iso-date, "in_window": bool}``
    or None when the dataset has no schedule entry.

    For window-based schedules (annual reports) the window may span a
    year boundary (Dec 1 → Apr 30); ``in_window`` is True while today is
    inside it — meaning "the next report may appear any day now".
    """
    sched = PUBLICATION_SCHEDULE.get(dataset_id)
    if sched is None:
        return None
    entry = SOURCE_REGISTRY.get(dataset_id)

    window = sched.get("check_window")
    result = {
        "dataset": dataset_id,
        "publisher": entry.publisher if entry else None,
        "cadence": sched.get("frequency"),
        "lag": sched.get("lag_months") or sched.get("lag_days"),
        "lag_unit": "months" if sched.get("lag_months") else "days",
    }
    if window:
        start_anchor, end_anchor = window["start"], window["end"]
        start = _md(start_anchor, today.year)
        end = _md(end_anchor, today.year)
        if end < start:  # spans the year boundary (Dec → Apr)
            # Window runs start(Y)→end(Y+1); today may sit inside the
            # tail of last year's window (Jan–Apr) or before this year's.
            if today <= end:  # inside the tail: window began last year
                start = _md(start_anchor, today.year - 1)
            else:
                end = _md(end_anchor, today.year + 1)
        elif today > end:  # this year's window has passed
            start = _md(start_anchor, today.year + 1)
            end = _md(end_anchor, today.year + 1)
        result.update(
            window_start=start.isoformat(),
            window_end=end.isoformat(),
            in_window=start <= today <= end,
        )
        return result

    check_dates: List[str] = sched.get("check_dates", [])
    if check_dates:
        candidates = sorted(
            _md(a, y) for a in check_dates for y in (today.year, today.year + 1)
        )
        nxt = next(c for c in candidates if c >= today)
        result.update(
            window_start=nxt.isoformat(),
            window_end=nxt.isoformat(),
            in_window=nxt == today,
        )
        return result

    # Monthly/daily lag-only schedules: always effectively "in window".
    result.update(window_start=None, window_end=None, in_window=True)
    return result


__all__ = [
    "PUBLICATION_SCHEDULE",
    "SOURCE_REGISTRY",
    "SourceDataset",
    "next_expected_window",
]

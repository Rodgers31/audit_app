"""
Audit Dashboard Router — National Audit Findings API

Provides endpoints for:
- Summary statistics (totals, breakdowns, worst counties)
- Year-over-year trends
- Recurring findings detection
- Paginated findings list with filters
"""

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from cache.redis_cache import cached
from services.audit_opinions import opinion_facet, opinion_facet_by_year
from services.oag_report_sections import canonical_section
from services.publication_gate import (
    count_withheld_audits,
    publishable_audit_criterion,
)

try:
    from database import get_db
    from models import Audit, Entity, Extraction, SourceDocument

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False

    def get_db():
        return None


router = APIRouter(prefix="/api/v1/audit", tags=["Audit Dashboard"])
logger = logging.getLogger(__name__)


# ===== Response Models =====


class WithheldFigure(BaseModel):
    """A published figure, or absence with the reason stated.

    Same shape as ``services.publication_gate.withheld_file_figure`` so a
    reader meets one convention across the API. ``value is None`` means **not
    published**; it never means zero. A zero here would be a claim about the
    world — "the Auditor-General questioned nothing" — and the two must not be
    spelled the same way (the zero-for-absence rule).
    """

    value: Optional[float] = None
    reason: Optional[str] = None


class WorstCounty(BaseModel):
    county_id: int
    county_name: str
    total_amount: float = Field(
        ...,
        description=(
            "Sum of the amounts recorded on this county's findings. These are "
            "amounts the Auditor-General DISCUSSED — the extraction takes the "
            "single Kshs. figure in a finding paragraph, which is often the "
            "account balance under review rather than a sum being queried — "
            "so this is not a measure of money lost or irregularly spent."
        ),
    )
    finding_count: int


class YearRange(BaseModel):
    min_year: Optional[int] = None
    max_year: Optional[int] = None


class AuditSummaryResponse(BaseModel):
    total_irregular_expenditure: WithheldFigure = Field(
        ...,
        description=(
            "Irregular expenditure as the Auditor-General defines it. "
            "Published only when findings carry that classification."
        ),
    )
    total_unsupported_expenditure: WithheldFigure = Field(
        ...,
        description=(
            "Unsupported expenditure as the Auditor-General defines it. "
            "Published only when findings carry that classification."
        ),
    )
    total_findings: int
    findings_by_type: Dict[str, int]
    findings_by_opinion: Optional[Dict[str, int]] = Field(
        None,
        description=(
            "Findings grouped by the audit opinion on the entity's accounts. "
            "`null` means the facet is not published — see "
            "`findings_by_opinion_reason`. Never an empty object as a "
            "stand-in for absence."
        ),
    )
    findings_by_opinion_reason: Optional[str] = Field(
        None,
        description="Why `findings_by_opinion` is null, when it is.",
    )
    worst_counties: Optional[List[WorstCounty]] = Field(
        None,
        description=(
            "`null` — not published. A ranking of named counties by flagged "
            "amount is not supported by the data behind it; see "
            "`worst_counties_reason`. Never an empty list as a stand-in for "
            "absence, which would read as 'no county has any finding'."
        ),
    )
    worst_counties_reason: Optional[str] = Field(
        None, description="Why `worst_counties` is null."
    )
    year_range: YearRange
    withheld_findings: int = Field(
        0,
        description=(
            "Findings excluded from these totals because their source document "
            "has no URL a reader could open. Retained in the database, not served."
        ),
    )


class AuditTrendsResponse(BaseModel):
    years: List[int]
    findings_per_year: Dict[str, int]
    amount_per_year: Dict[str, float]
    opinion_per_year: Optional[Dict[str, Dict[str, int]]] = Field(
        None,
        description=(
            "Findings grouped by audit opinion, per year. `null` means the "
            "facet is not published — see `opinion_per_year_reason`."
        ),
    )
    opinion_per_year_reason: Optional[str] = Field(
        None, description="Why `opinion_per_year` is null, when it is."
    )


class RecurringFinding(BaseModel):
    county_name: str
    query_type: str
    years_appeared: List[int]
    total_amount: float
    finding_ids: List[int]


class RecurringFindingsResponse(BaseModel):
    recurring_findings: List[RecurringFinding]
    total: int
    #: Why the list is empty, when it is. "0 recurring findings" is a claim
    #: about Kenyan county audits; what is actually true is narrower — no
    #: entity-and-section group in the PUBLISHED rows appears in two different
    #: audit years — and a reader cannot tell those apart from the integer.
    #: None whenever there is something to show; present data explains itself.
    absent_reason: Optional[str] = None


class FindingDetail(BaseModel):
    id: int
    entity_id: int
    county_name: Optional[str] = None
    period_id: int
    finding_text: str
    severity: str
    recommended_action: Optional[str] = None
    query_type: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    audit_opinion: Optional[str] = None
    audit_year: Optional[int] = None
    follow_up_status: Optional[str] = None
    external_reference: Optional[str] = None
    management_response: Optional[str] = None
    source_document_url: Optional[str] = None
    confidence_score: Optional[float] = None


class FindingsListResponse(BaseModel):
    items: List[FindingDetail]
    total: int
    page: int
    limit: int


# ===== Helpers =====


def _check_db(db: Session):
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")


# ── Expenditure classes ──────────────────────────────────────────────
#
# "Irregular expenditure" and "unsupported expenditure" are specific findings
# in the Auditor-General's vocabulary, not loose descriptions. A figure
# published under either name has to be the sum of findings classified that
# way — and if nothing carries the classification, the honest answer is that
# the figure does not exist, not that it is zero.
#
# WHAT THE TWO SUMS USED TO BE
# ----------------------------
# `total_irregular_expenditure` summed `query_type == "Financial Irregularity"`
# wrapped in `coalesce(..., 0)`. Measured against production on 2026-09-06:
# **no row has ever carried that value.** The only rows whose `query_type`
# contains "Irregularit" at all are four — Payroll, Procurement, Subsidy
# Programme and ASAL Fund — and all four hang off source_document 1836, the
# fabricated `oag_national_audit_data.json` dataset, which the publication gate
# withholds for having no URL. So the sum ran over an empty set and published
# `0.0` as "Kenya's irregular expenditure".
#
# The taxonomy did not drift out from under the query so much as never arrive.
# `query_type` is written by the Blue Book extractor and holds the OAG REPORT
# SECTION a finding sits under ("Report on the Financial Statements", and 11
# truncation/case variants of the other two) — a location in the document, not
# a nature of irregularity. Nothing in the pipeline classifies an amount as
# irregular or unsupported, so neither figure is measured anywhere.
#
# `total_unsupported_expenditure` summed `status != "Resolved"`, i.e. the
# amount on findings of EVERY type whose status was not one particular word —
# a general quantity under a specific accounting name. That clause is also
# inert: no row in the table has ever had status "Resolved" (publishable
# statuses are `published_report` × 2,311 and `pending` × 1), so the figure
# production published as unsupported expenditure — KES 214,814,058,083.86 —
# was simply the sum of every amount on every publishable finding.
#
# These sets are kept as the classifications a future extractor would write.
# When one starts writing them the figures publish themselves; until then the
# endpoint says so in words.
IRREGULAR = "irregular"
UNSUPPORTED = "unsupported"

#: Why no county ranking is published. A ranking asserts a comparison BETWEEN
#: named public bodies, so it needs more than the sum it is ordered by — it
#: needs that sum to mean the same thing for every body in the list.
#: `Audit.amount` does not: it is present on 152 of the county findings and
#: absent on the rest, and where present it is whatever single `Kshs.` figure
#: the finding paragraph contained, usually the balance under discussion. An
#: order built on that is an artefact of which findings happened to state a
#: number.
#:
#: This is an unconditional withdrawal, and deliberately so. The repo's rule
#: for a partial sum — publish it WITH its coverage, or not at all
#: (`test_partial_questioned_amount.py`) — rescues a national TOTAL, because a
#: coverage figure qualifies one number honestly. It cannot rescue an ORDERING:
#: coverage differs per county, so annotating the list does not stop it ranking
#: them wrongly. The figure returns when the extraction separates an amount
#: QUESTIONED from an amount DISCUSSED, and not before.
WORST_COUNTIES_WITHHELD_REASON = (
    "not published: this was a ranking of named counties by the sum of the "
    "amounts on their findings. Those amounts are taken from any finding "
    "paragraph carrying a single Kshs. figure — usually the account balance "
    "the Auditor-General was discussing, not a sum being queried — and only "
    "152 county findings record one at all, so the ordering reflects which "
    "findings happened to state a number rather than which counties fared "
    "worst. Naming counties in that order would be a claim the report does "
    "not make. Every finding, its entity and its own stated amount are served "
    "individually by /api/v1/audit/findings, each with its source document."
)

_EXPENDITURE_CLASSES = {
    IRREGULAR: {
        "query_types": ("Financial Irregularity", "Irregular Expenditure"),
        "reason": (
            "not published: no finding is classified as irregular expenditure. "
            "`query_type` carries the Auditor-General's report SECTION, not the "
            "nature of the irregularity, so nothing in the data measures this "
            "figure. A zero here would assert that no irregular expenditure was "
            "found, which is a different and unsupported claim."
        ),
    },
    UNSUPPORTED: {
        "query_types": ("Unsupported Expenditure",),
        "reason": (
            "not published: no finding is classified as unsupported "
            "expenditure. This field previously summed the amount on findings "
            "whose status was not \"Resolved\" — every finding of every type, "
            "since no row has that status — and published it under a specific "
            "accounting term it did not measure. A zero here would assert that "
            "the Auditor-General questioned no unsupported expenditure, which "
            "is a different and unsupported claim."
        ),
    },
}


def _expenditure_class_criterion(name: str):
    """SQL criterion: this finding is classified as `name` expenditure."""
    return Audit.query_type.in_(_EXPENDITURE_CLASSES[name]["query_types"])


def _expenditure_figure(name: str, matched: int, amount) -> WithheldFigure:
    """The class total, or absence with the reason — never a manufactured zero.

    Three cases, deliberately distinguished:

    * **no finding carries the classification** → absence, with the reason.
    * **findings carry it but none records an amount** → absence, saying so.
      `SUM()` over all-NULL amounts is NULL; publishing 0 there would claim the
      findings questioned nothing.
    * **findings carry it and record amounts** → the sum, including a genuine
      0.0 if that is what they add up to. A measured zero is publishable.
    """
    if not matched:
        return WithheldFigure(value=None, reason=_EXPENDITURE_CLASSES[name]["reason"])
    if amount is None:
        return WithheldFigure(
            value=None,
            reason=(
                f"not published: {matched} finding(s) are classified as {name} "
                "expenditure but none records an amount, so there is no total "
                "to publish."
            ),
        )
    return WithheldFigure(value=float(amount), reason=None)


# ===== Endpoints =====


@router.get("/summary", response_model=AuditSummaryResponse)
@cached(ttl=300, key_prefix="audit_summary")
async def get_audit_summary(db: Session = Depends(get_db)):
    """Return aggregate audit statistics for the national dashboard.

    Optimised: combines totals + expenditure sums into a single query and
    merges type/opinion breakdowns where possible.
    """
    _check_db(db)
    try:
        # --- Combined totals in ONE query (was 3 separate queries) ---
        # INDEX hint: CREATE INDEX ix_audits_query_type ON audits(query_type)
        #
        # Each expenditure class is asked for TWICE: how many findings carry
        # it, and what they sum to. The count is what makes the difference
        # between "KES 0 was questioned" and "no finding is classified this
        # way" expressible — the sum alone cannot tell them apart, because
        # SUM() over no rows is NULL and the old `coalesce(..., 0)` spelled
        # that absence as a published zero.
        totals = db.query(
            func.count(Audit.id),
            func.count(Audit.id).filter(_expenditure_class_criterion(IRREGULAR)),
            func.sum(
                case((_expenditure_class_criterion(IRREGULAR), Audit.amount))
            ),
            func.count(Audit.id).filter(_expenditure_class_criterion(UNSUPPORTED)),
            func.sum(
                case((_expenditure_class_criterion(UNSUPPORTED), Audit.amount))
            ),
            func.min(Audit.audit_year),
            func.max(Audit.audit_year),
        ).filter(publishable_audit_criterion()).first()

        total_findings = totals[0] or 0
        total_irregular = _expenditure_figure(IRREGULAR, totals[1] or 0, totals[2])
        total_unsupported = _expenditure_figure(
            UNSUPPORTED, totals[3] or 0, totals[4]
        )
        min_year = totals[5]
        max_year = totals[6]

        # Findings by type
        # INDEX hint: CREATE INDEX ix_audits_query_type ON audits(query_type)
        type_rows = (
            db.query(Audit.query_type, func.count(Audit.id))
            .filter(publishable_audit_criterion())
            .filter(Audit.query_type.isnot(None))
            .group_by(Audit.query_type)
            .all()
        )
        # Fold the twelve stored heading variants onto the three OAG report
        # sections they actually belong to. The facet drove both a bar chart
        # and a filter dropdown, so a reader saw twelve near-identical options
        # ("...and Governance," vs "...and Governance.") plus a raw
        # `financial_audit` enum (credibility audit F39).
        from services.oag_report_sections import group_counts

        findings_by_type = group_counts({t: c for t, c in type_rows})

        # Findings by opinion
        # INDEX hint: CREATE INDEX ix_audits_opinion ON audits(audit_opinion)
        opinion_rows = (
            db.query(Audit.audit_opinion, func.count(Audit.id))
            .filter(publishable_audit_criterion())
            .filter(Audit.audit_opinion.isnot(None))
            .group_by(Audit.audit_opinion)
            .all()
        )
        # Fold the superseded label onto the current one, then decide whether
        # the facet may be published at all. See services/audit_opinions.py:
        # "Unqualified" and "Unmodified" are the same opinion under ISA 700
        # before and after revision, and a facet holding no modified opinion
        # has not been shown to be complete.
        findings_by_opinion, findings_by_opinion_reason = opinion_facet(
            {o: c for o, c in opinion_rows}
        )

        # Worst counties — WITHHELD. See WORST_COUNTIES_WITHHELD_REASON.
        #
        # The query that used to stand here ranked entities by
        # `sum(Audit.amount)`. Two things were wrong with it and only one was
        # repairable:
        #
        #   * it had no entity-type filter, so it ranked national ministries
        #     under a field named `county_name` — production returned "State
        #     Department for Medical Services", "Executive Office of the
        #     President" and "State Department for Immigration and Citizen
        #     Services" in the top five, with 16 MINISTRY entities carrying KES
        #     73.4Bn of the KES 214.8Bn. That part was a one-line fix.
        #
        #   * the ordering key itself is not a measure of anything. The
        #     ordering IS the claim — "these are the worst counties" — and it
        #     rests on `Audit.amount`, which the loader fills from any finding
        #     paragraph carrying exactly one `Kshs.` figure, usually the
        #     account balance under discussion rather than a sum being queried
        #     (credibility audit F1). Only 152 county findings record an amount
        #     at all, and Mombasa County led the list at KES 21.62Bn on the
        #     strength of ONE finding. Filtering to counties would have left a
        #     correctly-categorised false statement about which counties fared
        #     worst.
        #
        # Fixing the category and keeping the ranking would have been the
        # smaller change and the wrong one. The frontend withdrew this ranking
        # on these grounds already (F1/F34); an API that goes on serving what
        # the page refuses to show is the same publication wearing a thinner
        # disguise.
        worst_counties = None

        withheld = count_withheld_audits(db)
        if withheld:
            logger.warning(
                "audit summary: %d finding(s) withheld — source document has no "
                "resolvable URL; %d published",
                withheld,
                total_findings,
            )

        return AuditSummaryResponse(
            total_irregular_expenditure=total_irregular,
            total_unsupported_expenditure=total_unsupported,
            total_findings=total_findings,
            findings_by_type=findings_by_type,
            findings_by_opinion=findings_by_opinion,
            findings_by_opinion_reason=findings_by_opinion_reason,
            worst_counties=worst_counties,
            worst_counties_reason=WORST_COUNTIES_WITHHELD_REASON,
            year_range=YearRange(min_year=min_year, max_year=max_year),
            withheld_findings=withheld,
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


def _query_type_filter(db, query_type: str):
    """SQL condition matching every stored heading in a canonical section.

    The facet now offers canonical section names, so the value coming back on
    the query string is a section, not one of the raw headings in the column.
    Expand it to the set of raw values that belong to that section. An exact
    raw heading still matches itself, so any link made before this change keeps
    working.
    """
    from services.oag_report_sections import raw_variants_for

    known = [
        row[0]
        for row in db.query(Audit.query_type)
        .filter(Audit.query_type.isnot(None))
        .distinct()
        .all()
    ]
    variants = raw_variants_for(query_type, known)
    if not variants:
        # Unknown value: match it literally so the filter returns nothing
        # rather than silently returning everything.
        return Audit.query_type == query_type
    return Audit.query_type.in_(variants)


@router.get("/trends", response_model=AuditTrendsResponse)
@cached(ttl=300, key_prefix="audit_trends")
async def get_audit_trends(
    county_id: Optional[int] = Query(None, description="Filter by county entity ID"),
    query_type: Optional[str] = Query(None, description="Filter by query type"),
    db: Session = Depends(get_db),
):
    """Return year-over-year audit trend data (SQL-aggregated)."""
    _check_db(db)
    try:
        # Build reusable filter conditions
        filters = [Audit.audit_year.isnot(None)]
        if county_id is not None:
            filters.append(Audit.entity_id == county_id)
        if query_type is not None:
            filters.append(_query_type_filter(db, query_type))

        # Findings count per year — single SQL GROUP BY
        # INDEX hint: CREATE INDEX ix_audits_year ON audits(audit_year)
        findings_rows = (
            db.query(Audit.audit_year, func.count(Audit.id))
            .filter(publishable_audit_criterion())
            .filter(*filters)
            .group_by(Audit.audit_year)
            .all()
        )
        findings_per_year = {str(yr): cnt for yr, cnt in findings_rows}

        # Amount per year — single SQL GROUP BY
        amount_rows = (
            db.query(Audit.audit_year, func.coalesce(func.sum(Audit.amount), 0))
            .filter(publishable_audit_criterion())
            .filter(*filters)
            .group_by(Audit.audit_year)
            .all()
        )
        amount_per_year = {str(yr): float(amt) for yr, amt in amount_rows}

        # Opinion breakdown per year — single SQL GROUP BY
        # INDEX hint: CREATE INDEX ix_audits_year_opinion ON audits(audit_year, audit_opinion)
        opinion_rows = (
            db.query(Audit.audit_year, Audit.audit_opinion, func.count(Audit.id))
            .filter(publishable_audit_criterion())
            .filter(*filters, Audit.audit_opinion.isnot(None))
            .group_by(Audit.audit_year, Audit.audit_opinion)
            .all()
        )
        # Same gate as /summary, applied per year. This is the same facet
        # sliced differently, so it withholds for the same reason and by the
        # same rule — an opinion mix carrying no Qualified, Adverse or
        # Disclaimer opinion is not published. Withholding it on /summary while
        # /trends went on serving it year by year would have moved the defect
        # rather than fixed it.
        raw_per_year: Dict[str, Dict[str, int]] = defaultdict(dict)
        for yr, opinion, cnt in opinion_rows:
            raw_per_year[str(yr)][opinion] = cnt
        opinion_per_year, opinion_reason = opinion_facet_by_year(dict(raw_per_year))

        # Distinct years
        years = sorted(int(y) for y in findings_per_year.keys())

        return AuditTrendsResponse(
            years=years,
            findings_per_year=findings_per_year,
            amount_per_year=amount_per_year,
            opinion_per_year=opinion_per_year,
            opinion_per_year_reason=opinion_reason,
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@router.get("/recurring", response_model=RecurringFindingsResponse)
async def get_recurring_findings(db: Session = Depends(get_db)):
    """Return findings flagged as recurring or appearing in 2+ years.

    Optimised: uses JOINs to fetch entity names and SQL aggregation to
    avoid N+1 per-row entity lookups.
    """
    _check_db(db)
    try:
        # INDEX hint: CREATE INDEX ix_audits_entity_qtype_year
        #   ON audits(entity_id, query_type, audit_year)

        # --- Identify recurring groups, folding heading variants FIRST ---
        #
        # The OAG writes the same standing section under several headings, and
        # canonical_section() folds them. Grouping by the RAW query_type and
        # canonicalising only the emitted label produced two defects:
        #
        #   * two variants for one county came back as duplicate rows carrying
        #     the same canonical label, with the years and amounts split
        #     between them, inflating the pattern count; and
        #   * worse, a finding recorded as variant A in 2022 and variant B in
        #     2023 never reached the "spans 2+ years" threshold, so a genuine
        #     recurrence was missed entirely.
        #
        # So fold to the canonical section BEFORE deciding recurrence, and
        # merge years, amounts and ids across the variants. One query rather
        # than the previous 2 + N.
        rows = (
            db.query(
                Audit.id,
                Audit.entity_id,
                Audit.query_type,
                Audit.audit_year,
                Audit.amount,
                Audit.follow_up_status,
            )
            .filter(publishable_audit_criterion())
            .all()
        )

        groups: Dict[tuple, dict] = {}
        for fid, eid, qt, yr, amt, follow_up in rows:
            label = canonical_section(qt) or qt or "Unknown"
            g = groups.setdefault(
                (eid, label),
                {"years": set(), "amount": 0.0, "ids": [], "flagged": False},
            )
            if yr is not None:
                g["years"].add(yr)
            if amt is not None:
                g["amount"] += float(amt)
            g["ids"].append(fid)
            if follow_up == "Recurring":
                g["flagged"] = True

        # A group is recurring if explicitly flagged OR it spans 2+ years.
        result_map = {
            key: value
            for key, value in groups.items()
            if value["flagged"] or len(value["years"]) >= 2
        }

        if not result_map:
            # Say which absence this is. The published rows may span one audit
            # year, in which case nothing CAN recur; or several, in which case
            # nothing did. Those are different facts and the count is the same.
            years = sorted({yr for _, _, _, yr, _, _ in rows if yr is not None})
            if not rows:
                reason = (
                    "No audit findings are published, so recurrence cannot be "
                    "assessed. See withheld_findings_by_reason on "
                    "/api/v1/audits/statistics."
                )
            elif len(years) < 2:
                covered = ", ".join(str(y) for y in years) or "no stated year"
                reason = (
                    f"The {len(rows)} published findings cover {covered}. A "
                    "finding is counted as recurring when its entity and "
                    "section appear in two or more audit years, which one year "
                    "of data cannot show."
                )
            else:
                covered = ", ".join(str(y) for y in years)
                reason = (
                    f"No entity and section appears in two or more of the "
                    f"audit years published ({covered}) across the "
                    f"{len(rows)} published findings."
                )
            return RecurringFindingsResponse(
                recurring_findings=[], total=0, absent_reason=reason
            )

        entity_name_map: Dict[int, str] = {}
        _entity_ids = list({eid for eid, _ in result_map})
        if _entity_ids:
            for eid, name in (
                db.query(Entity.id, Entity.canonical_name)
                .filter(Entity.id.in_(_entity_ids))
                .all()
            ):
                entity_name_map[eid] = name

        for (eid, label), value in result_map.items():
            value["county_name"] = entity_name_map.get(eid, "Unknown")
            value["query_type"] = label

        recurring = []
        for v in result_map.values():
            recurring.append(RecurringFinding(
                county_name=v["county_name"],
                query_type=v["query_type"],
                years_appeared=sorted(v["years"]),
                total_amount=v["amount"],
                finding_ids=sorted(set(v["ids"])),
            ))

        return RecurringFindingsResponse(
            recurring_findings=recurring,
            total=len(recurring),
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@router.get("/findings", response_model=FindingsListResponse)
async def get_audit_findings(
    county_id: Optional[int] = Query(None, description="Filter by county entity ID"),
    year: Optional[int] = Query(None, description="Filter by audit year"),
    query_type: Optional[str] = Query(None, description="Filter by query type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    audit_opinion: Optional[str] = Query(None, description="Filter by audit opinion"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """Return paginated list of audit findings with filters."""
    _check_db(db)
    try:
        # Subquery: average confidence per source_document from extractions
        confidence_sub = (
            db.query(
                Extraction.source_document_id,
                func.avg(Extraction.confidence).label("avg_confidence"),
            )
            .group_by(Extraction.source_document_id)
            .subquery()
        )

        query = (
            db.query(
                Audit,
                Entity.canonical_name,
                SourceDocument.url.label("doc_url"),
                confidence_sub.c.avg_confidence,
            )
            .join(Entity, Audit.entity_id == Entity.id)
            .outerjoin(SourceDocument, Audit.source_document_id == SourceDocument.id)
            .outerjoin(
                confidence_sub,
                Audit.source_document_id == confidence_sub.c.source_document_id,
            )
            .filter(publishable_audit_criterion())
        )

        if county_id is not None:
            query = query.filter(Audit.entity_id == county_id)
        if year is not None:
            query = query.filter(Audit.audit_year == year)
        if query_type is not None:
            query = query.filter(_query_type_filter(db, query_type))
        if severity is not None:
            query = query.filter(Audit.severity == severity)
        if audit_opinion is not None:
            query = query.filter(Audit.audit_opinion == audit_opinion)
        if status is not None:
            query = query.filter(Audit.status == status)

        total = query.count()
        offset = (page - 1) * limit
        rows = query.order_by(desc(Audit.audit_year), desc(Audit.id)).offset(offset).limit(limit).all()

        items = []
        for a, county_name, doc_url, avg_conf in rows:
            # Build source document URL: prefer external_reference, then doc URL
            source_url = None
            if a.external_reference:
                ref = a.external_reference.strip()
                if ref.startswith("http"):
                    source_url = ref
                else:
                    source_url = f"https://www.oagkenya.go.ke/wp-content/uploads/{ref}"
            elif doc_url:
                source_url = doc_url

            items.append(
                FindingDetail(
                    id=a.id,
                    entity_id=a.entity_id,
                    county_name=county_name,
                    period_id=a.period_id,
                    finding_text=a.finding_text,
                    severity=a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                    recommended_action=a.recommended_action,
                    # The row's own label must match the facet the reader
                    # filtered on, otherwise selecting a section shows rows
                    # apparently of a different type.
                    query_type=canonical_section(a.query_type) or a.query_type,
                    amount=float(a.amount) if a.amount is not None else None,
                    status=a.status,
                    audit_opinion=a.audit_opinion,
                    audit_year=a.audit_year,
                    follow_up_status=a.follow_up_status,
                    external_reference=a.external_reference,
                    management_response=a.management_response,
                    source_document_url=source_url,
                    confidence_score=float(avg_conf) if avg_conf is not None else None,
                )
            )

        return FindingsListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

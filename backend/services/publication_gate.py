"""The publication gate — one definition of "may this figure be published?".

Provenance-or-nothing (``IMPLEMENTATION_PROMPT.md`` A.2, L5). A figure may be
served to the public only if it resolves to a source a reader can open. This
module is the single place that rule is expressed, so that:

* ``main.py`` and ``routers/audit_dashboard.py`` cannot drift apart — Stage 0
  gated the router only, and ``/api/v1/audits/federal`` in ``main.py`` went on
  serving KES 3.313T of withheld rows as ``total_amount_in_findings``;
* Stage 1 can backfill the ``publishable`` column from the same predicate the
  API enforces, rather than a second copy of the rule.

Nothing here deletes data. Withheld rows stay in the database and are counted
so the omission is visible in the response and the log.

WHAT THIS GATE DOES **NOT** CHECK
---------------------------------
These are real, known holes. They are named here so callers do not mistake a
passing row for a verified one:

1. **The URL is not fetched.** A row citing a dead link passes. ``AUDIT_FINDINGS``
   §5.0c found 3 of 20 sampled URLs return 404 and 8 resolve to landing pages
   rather than a document, so e.g. ``treasury.go.ke/public-debt/`` (404) passes
   this gate today. Resolvability is Stage 2/3 work (fetcher + ``last_verified_at``).
2. **``md5`` is not checked.** It is NULL on 100% of the source documents behind
   published figures, so requiring it would withhold everything. Stage 2 populates
   it; only then can a reissued document invalidate its derived rows.
3. **The locator is not resolved.** A ``page_ref`` of ``p.409`` is required and
   is checked for being a locator at all — present, non-blank, and a positive
   page rather than ``0`` or ``-3`` — but nobody opens the PDF at page 409 to
   see whether the finding is there. That is Stage 2/3 work alongside item 1.

NO LONGER AN ASYMMETRY — closed 2026-09-07 (issue #137)
--------------------------------------------------------
``missing_funds_provenance_failure`` requires *document + URL + page*, and
``publishable_audit_criterion`` now requires the same. This section used to
explain why audits were exempt. Both of its reasons had expired:

* *"``Audit`` has no page column."* It has one. Stage 1 added ``page_ref`` to
  ``audits``, and the extractors fill it: measured on production 2026-09-07,
  **2,311 of 2,338** rows carry one, every one of the form ``p.NNN``, none
  blank and none numeric-only.
* *"Requiring a page would withhold audit id 902 — the single genuine
  extraction in the table."* Audit 902 is withheld already, by the clause
  below it: it is 89.6% ``(cid:NN)`` glyph codes off a cover page and carries
  ``publishable = False`` today. It was never the genuine extraction this
  paragraph took it for, which is also why an ``extraction_id`` is not the
  rung this ladder uses — 902 had one.

The cost of closing it, measured before it was closed: **one row**. Audit 901,
Homa Bay, source document 2391 — the OAG report's PREAMBLE ("I draw your
attention to the contents of my report which is in three parts"), 500
characters cut mid-word, no amount, no extraction, no page, stored with
severity CRITICAL and published. It was that county's only critical finding
and it is counted in ``/api/v1/audit/summary``'s ``total_findings``. Requiring
a locator does not lose a finding here; it stops publishing a page of front
matter as one.
"""

from __future__ import annotations

import logging
import hashlib
import json
import re
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlsplit

from sqlalchemy import and_ as sa_and
from sqlalchemy import Integer, LargeBinary, case, cast
from sqlalchemy import func
from sqlalchemy import or_ as sa_or
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Imported unguarded on purpose. A try/except here would set a flag nobody
# reads and let callers build a query against ``None``, turning a missing model
# into an AttributeError deep inside a request instead of a clear failure at
# import. The gate must fail closed, and loudly.
from models import Audit, SourceDocument
from services.audit_citations import (
    NAMED_LOCATOR_PATTERN,
    NUMERIC_LOCATOR_PATTERN,
    SOURCE_URL_PATTERN,
    citation_page,
    safe_source_url,
)


# --------------------------------------------------------------------------
# audits
# --------------------------------------------------------------------------


def _source_document_has_url():
    return Audit.source_document_id.in_(
        select(SourceDocument.id).where(
            SourceDocument.url.isnot(None),
            SourceDocument.url.regexp_match(r"[^ \t\n\r\f\v]"),
        )
    )


def _source_document_is_resolvable():
    """A linked document with a syntactically safe HTTP(S) URL.

    Extracted while fixing the PR #135 reason-breakdown finding: the
    per-reason count has to ask "did THIS clause fail?", and re-typing the
    subquery there would have created a second copy of the rule — the exact
    thing this module exists to prevent.
    """
    return Audit.source_document_id.in_(
        select(SourceDocument.id).where(
            _ascii_only(SourceDocument.url),
            func.lower(SourceDocument.url).regexp_match(SOURCE_URL_PATTERN),
        )
    )


def _ascii_only(column):
    """Portable byte-length guard against Unicode case-folding aliases."""
    return func.length(column) == func.length(cast(column, LargeBinary))


_DESCRIPTIVE_PDF_PAGE = re.compile(
    r"\bPDF[ \t]+pp?\.[ \t]*[1-9][0-9]{0,8}"
    r"(?:[ \t]*(?:,|[-–])[ \t]*[1-9][0-9]{0,8})*\b",
    re.I,
)

# Treasury's fiscal-framework rows also retain the concise source-table form
# "Annex 2a p63". Keep this outside the shared audit/county locator policy.
_FISCAL_ANNEX_PAGE = re.compile(
    r"Annex(?:[ \t]+Table)?[ \t]+[1-9][0-9]{0,2}[a-z]?"
    r"(?:[ \t]*,[ \t]*|[ \t]+)p\.?[ \t]*[1-9][0-9]{0,8}",
    re.I | re.ASCII,
)


def _has_page_locator(*candidates, allow_descriptive=False) -> bool:
    """Validate a direct citation; fiscal summaries may cite PDF pages in prose."""
    for value in candidates:
        if citation_page(value) is not None:
            return True
        if (
            allow_descriptive
            and isinstance(value, str)
            and _DESCRIPTIVE_PDF_PAGE.search(value)
        ):
            return True
    return False


_WHITESPACE = (" ", "\t", "\n", "\r", "\f", "\v")


def _has_page_locator_criterion(column):
    """SQL form of the shared direct-citation policy, including range order."""
    squeezed = column
    for ch in _WHITESPACE:
        squeezed = func.replace(squeezed, ch, "")
    # The shape regex bounds each integer to nine digits before a SQL cast.
    # ltrim removes only the permitted page-prefix characters; the regex
    # rules out arbitrary prose before these numeric operations are evaluated.
    body = func.ltrim(func.lower(func.replace(squeezed, "–", "-")), "pages.")
    start_length = func.length(body) - func.length(func.ltrim(body, "0123456789"))
    start = func.substr(body, 1, start_length)
    remainder = func.substr(body, start_length + 1)
    numeric = sa_and(
        _ascii_only(func.replace(column, "–", "-")),
        func.lower(column).regexp_match(NUMERIC_LOCATOR_PATTERN.lower()),
    )
    return func.coalesce(
        sa_or(
            sa_and(
                _ascii_only(column),
                func.lower(column).regexp_match(NAMED_LOCATOR_PATTERN.lower()),
            ),
            case(
                (
                    numeric,
                    sa_and(
                        cast(start, Integer) > 0,
                        sa_or(
                            remainder == "",
                            cast(func.substr(remainder, 2), Integer)
                            >= cast(start, Integer),
                        ),
                    ),
                ),
                else_=False,
            ),
        ),
        False,
    )


def _finding_text_is_readable():
    """The text-integrity half of the gate, named once so it cannot drift.

    Extracted while adding the locator clause: ``count_withheld_by_reason``
    has to ask "did THIS clause fail?" for three causes now, and re-typing the
    condition there would have created a second copy of it.
    """
    return sa_or(
        Audit.finding_text.is_(None),
        ~Audit.finding_text.contains("(cid:"),
    )


def retired_audit_fixture_criterion():
    """Unextracted rows from the retired hand-written audit fixtures.

    Match stored origin, not a deployment-specific document ID. Genuine
    extractions remain subject to the ordinary publication/evidence rules.
    Storage is retained pending the reviewed cleanup in #319.
    """
    fixture_docs = select(SourceDocument.id).where(
        SourceDocument.meta["source"].as_string().in_(
            ("oag_national_audit_data.json", "oag_audit_data.json")
        )
    )
    return sa_and(Audit.extraction_id.is_(None), Audit.source_document_id.in_(fixture_docs))


def publishable_audit_criterion():
    """SQL criterion: this finding resolves to a document a reader can open.

    Apply to **every** public query that reads ``audits``::

        db.query(...).filter(publishable_audit_criterion())

    Twenty-five rows hang off source_document 1836 — an authoritative-looking
    OAG title whose ``url`` and ``md5`` are both NULL and whose ``status`` is
    nevertheless ``AVAILABLE`` — which contributed KES 3.313T of the KES 3.91T
    ``/audits`` headline (``AUDIT_FINDINGS`` F5.4).

    That 25 was once **25 of 27**, and this docstring said so. The extractor
    work since has taken ``audits`` to **2,338** rows on production
    (2026-09-07), so the old phrasing read as if the table held 27 rows in
    total — 27 was the ``page_ref`` count, not the table — and anyone sizing
    the blast radius of a change here off that sentence would have been wrong
    by two orders of magnitude. Today the gate withholds 27 of 2,338:
    25 for no URL, 1 for unreadable text (audit 902), 1 for no page
    reference (audit 901).

    Because ``Audit.source_document_id`` is ``nullable=False`` and this is an
    ``IN (SELECT ...)``, the criterion already implies *the FK target exists*
    and *its URL is non-empty*. See the module docstring for what it does not
    imply.
    """
    return sa_and(
        ~retired_audit_fixture_criterion(),
        _source_document_is_resolvable(),
        # Text integrity. Audit 902 — the row previously described as "the
        # single genuine extraction" — is 89.6% ``(cid:NN)`` glyph codes ending
        # in the report's VISION statement: the PDF's cover page, not a
        # finding, with an empty ``amount``.
        #
        # A.4 quarantines text that is >20% ``(cid:``; expressing a ratio in
        # SQL is awkward, so this withholds a finding containing ANY such
        # token. That is deliberately stricter than A.4 and is the safe
        # direction while the OCR-retry path A.4 assumes does not yet exist
        # (Stage 2). Revisit when it does.
        _finding_text_is_readable(),
        # A locator. Closing the gap this module's docstring asked Stage 1 to
        # close. Costs exactly one row on production: audit 901, the OAG
        # report's PREAMBLE, published today as Homa Bay's only CRITICAL
        # finding with no amount and no page.
        _has_page_locator_criterion(Audit.page_ref),
    )


def count_withheld_by_reason(db, entity_id=None, entity_types=None) -> dict:
    """Withheld audit rows grouped by WHY, not just how many.

    A row can fail on a missing URL, an invalid URL, unreadable text or an
    invalid locator. Each bucket names the first actual failure.

    Keys are the same slugs the backfill writes to ``quarantine_reason``, so a
    response, a log line and the column all say the same word. Always returns
    every known reason (0 where none apply) so a caller can render a stable
    shape, and the values always sum to :func:`count_withheld_audits`.
    """
    def _count(criterion):
        q = db.query(func.count(Audit.id)).filter(
            criterion, ~retired_audit_fixture_criterion()
        )
        if entity_id is not None:
            q = q.filter(Audit.entity_id == entity_id)
        if entity_types is not None:
            from models import Entity

            q = q.join(Entity, Audit.entity_id == Entity.id).filter(
                Entity.type.in_(entity_types)
            )
        return q.scalar() or 0

    # Mutually exclusive by precedence, so each row is counted once and under
    # the first thing actually wrong with it.
    #
    # This used to derive the second bucket by subtracting the first from the
    # total, on the reasoning that the parts would then always sum "even if a
    # third cause is added without updating this function". A third cause has
    # now been added, and subtraction handles it exactly wrong: a finding
    # withheld for citing no page would have been reported as unreadable glyph
    # text — the same mislabelling this function was written to fix, one layer
    # down. Summing to the total is necessary, not sufficient; the words have
    # to be true too.
    has_url = _source_document_has_url()
    resolvable = _source_document_is_resolvable()
    readable = _finding_text_is_readable()
    located = _has_page_locator_criterion(Audit.page_ref)

    total = _count(~publishable_audit_criterion())
    reasons = {
        "source_document_has_no_url": _count(~has_url),
        "source_document_has_invalid_url": _count(sa_and(has_url, ~resolvable)),
        "finding_text_unreadable_cid": _count(sa_and(resolvable, ~readable)),
        "no_page_reference": _count(sa_and(resolvable, readable, ~located)),
    }

    # The named clauses above cover the criterion, so a residual means an
    # eligibility clause was added without a word for it. Report it rather
    # than let the parts quietly stop summing, or file it under a cause it
    # does not have.
    residual = total - sum(reasons.values())
    if residual:
        logger.error(
            "publication gate: %d withheld audit row(s) match no named reason "
            "— a clause was added to publishable_audit_criterion() without "
            "extending count_withheld_by_reason()",
            residual,
        )
        reasons["unclassified"] = residual
    return reasons


def count_withheld_audits(db, entity_id=None, entity_types=None) -> int:
    """How many audit rows the gate is holding back.

    Never let a withheld row be silent: a response that drops rows without
    saying so is the same defect as publishing them, wearing a different hat.

    **Scope the count to the same rows the endpoint would otherwise have
    shown.** A federal endpoint reporting a global withheld count states a
    number that does not mean what its field name says, which is its own small
    dishonesty. Pass ``entity_id`` for one entity, or ``entity_types`` (a list
    of ``EntityType``) to match an endpoint's own entity filter.
    """
    q = db.query(func.count(Audit.id)).filter(
        ~publishable_audit_criterion(), ~retired_audit_fixture_criterion()
    )
    if entity_id is not None:
        q = q.filter(Audit.entity_id == entity_id)
    if entity_types is not None:
        from models import Entity

        q = q.join(Entity, Audit.entity_id == Entity.id).filter(
            Entity.type.in_(entity_types)
        )
    return q.scalar() or 0


def backfill_publishable_audits(session) -> Dict[str, int]:
    """Write the gate's verdict into ``audits.publishable`` — same predicate.

    The Layer-4 loader calls this after inserting rows, and the Stage-1
    backfill migration calls it once over the existing table, so the column
    always carries what :func:`publishable_audit_criterion` would compute.
    One definition, three call sites, zero copies of the rule.

    Withheld rows also get a machine-readable ``quarantine_reason`` derived
    from *which* clause failed, so an operator can see why a row is held
    without re-deriving the predicate by hand.

    Returns ``{"published": n, "withheld": n}``.
    """
    from sqlalchemy import update

    # Timed because it was not, and that cost a diagnosis. This line is
    # emitted three times a night with byte-identical text ("2311 published,
    # 27 withheld (25 no-url, 1 cid, 1 no-page)"), which made it the obvious
    # suspect for the audits domain's 434s — and it is not the culprit. With
    # no duration on it, the only way to find that out was to regress the
    # gaps between log lines against the extraction counts. Print the number
    # instead of making the next reader derive it.
    started = time.monotonic()

    crit = publishable_audit_criterion()
    # Which clause failed? In order: missing URL, invalid URL, text integrity,
    # then the locator. A row can fail more than one; the earliest reason wins,
    # and the buckets are disjoint so no row is
    # counted or stamped twice.
    #
    # These reuse the named clauses the criterion is built from.
    has_url = _source_document_has_url()
    resolvable = _source_document_is_resolvable()
    readable = _finding_text_is_readable()
    located = _has_page_locator_criterion(Audit.page_ref)

    retired = retired_audit_fixture_criterion()
    no_url = sa_and(~retired, ~has_url)
    invalid_url = sa_and(~retired, has_url, ~resolvable)
    unreadable = sa_and(~retired, resolvable, ~readable)
    unlocated = sa_and(~retired, resolvable, readable, ~located)

    # The counts describe the TABLE, so they are read, not inferred from how
    # many rows this particular call happened to write. Previously they were
    # the UPDATEs' rowcounts, which forced every UPDATE to match every row it
    # was reporting on — see the write guards below.
    published = session.execute(
        select(func.count(Audit.id)).where(crit)
    ).scalar_one()
    no_url_count = session.execute(
        select(func.count(Audit.id)).where(no_url)
    ).scalar_one()
    invalid_url_count = session.execute(
        select(func.count(Audit.id)).where(invalid_url)
    ).scalar_one()
    withheld_cid = session.execute(
        select(func.count(Audit.id)).where(unreadable)
    ).scalar_one()
    withheld_no_page = session.execute(
        select(func.count(Audit.id)).where(unlocated)
    ).scalar_one()

    # Write only where the stored verdict differs from the computed one.
    #
    # The loader calls this after EVERY document it loads, and each of these
    # three statements used to be unconditional — so a settled table was
    # rewritten end to end, several times a run, to the values it already
    # held. Measured on production 2026-09-06: 2338 rows, 2312 matching the
    # criterion, 0 needing any change, and the audits domain spending
    # 120s + 146s + 80s = 346s of a 1320s global seed budget on three
    # backfills that logged identical results. The run then ran out of budget
    # in `pending_bills` and dropped four domains.
    #
    # It was never the scan: EXPLAIN (ANALYZE) on this same WHERE returns in
    # 9ms. It was the writing — `audits` is 16MB with nine indexes, so each
    # pointless row rewrite dragged nine index entries with it.
    #
    # `IS NOT TRUE` / `IS NOT FALSE` rather than `!=` so a NULL `publishable`
    # (a row inserted before the column was backfilled) still converges.
    # `quarantine_reason` is compared with an explicit NULL branch rather than
    # `IS DISTINCT FROM`, which SQLite only learned in 3.39.
    def _needs(publishable: bool, reason: Optional[str]):
        stored_reason = (
            Audit.quarantine_reason.isnot(None)
            if reason is None
            else sa_or(
                Audit.quarantine_reason.is_(None),
                Audit.quarantine_reason != reason,
            )
        )
        stored_flag = (
            Audit.publishable.isnot(True)
            if publishable
            else Audit.publishable.isnot(False)
        )
        return sa_or(stored_flag, stored_reason)

    session.execute(
        update(Audit)
        .where(crit, _needs(True, None))
        .values(publishable=True, quarantine_reason=None)
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(Audit)
        .where(no_url, _needs(False, "source_document_has_no_url"))
        .values(publishable=False, quarantine_reason="source_document_has_no_url")
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(Audit)
        .where(invalid_url, _needs(False, "source_document_has_invalid_url"))
        .values(publishable=False, quarantine_reason="source_document_has_invalid_url")
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(Audit)
        .where(unreadable, _needs(False, "finding_text_unreadable_cid"))
        .values(publishable=False, quarantine_reason="finding_text_unreadable_cid")
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(Audit)
        .where(unlocated, _needs(False, "no_page_reference"))
        .values(publishable=False, quarantine_reason="no_page_reference")
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(Audit)
        .where(retired, _needs(False, "retired_legacy_fixture"))
        .values(publishable=False, quarantine_reason="retired_legacy_fixture")
        .execution_options(synchronize_session=False)
    )
    session.flush()
    stats = {
        "published": published,
        "withheld": no_url_count + invalid_url_count + withheld_cid + withheld_no_page,
    }
    logger.info(
        "publishable backfill: %d published, %d withheld "
        "(%d no-url, %d invalid-url, %d cid, %d no-page) in %.2fs",
        stats["published"],
        stats["withheld"],
        no_url_count,
        invalid_url_count,
        withheld_cid,
        withheld_no_page,
        time.monotonic() - started,
    )
    return stats


def log_withheld_audits(context: str, withheld: int, published: int) -> None:
    """Emit the withholding at WARNING, with enough detail to act on."""
    if withheld:
        logger.warning(
            "%s: %d audit finding(s) withheld by the evidence gate; "
            "%d published",
            context,
            withheld,
            published,
        )


# --------------------------------------------------------------------------
# fiscal summaries
# --------------------------------------------------------------------------

#: Slug written into a response and a log line when a fiscal row names no page.
#: One word for one cause, matching the ``quarantine_reason`` vocabulary the
#: audits backfill already writes, so a response, a log and a column agree.
FISCAL_SUMMARY_NO_PAGE_REF = "no_page_reference"


def fiscal_summary_withheld_reason(row) -> Optional[str]:
    """Why this fiscal row may not be published, or ``None`` if it may.

    Tier B of the provenance ladder: a **locator**. The rung is deliberately
    ``page_ref`` and not ``extraction_id`` — a reader cannot open an extraction
    id, and it is neither necessary nor sufficient. The FY2026/27 headline
    carries ``"voted total PDF p.11; CFS summary PDF p.1193"`` and no
    ``extraction_id`` at all; audit 902 had an ``Extraction`` and was 89.6%
    ``(cid:NN)`` glyphs off a cover page.

    Fiscal rows use the shared direct citation policy plus explicit exceptions
    for descriptive PDF pages and Treasury's "Annex 2a p63" shorthand. They are
    materialised before this check; audit findings use the matching SQL expression.
    """
    page_ref = getattr(row, "page_ref", None)
    if not (
        _has_page_locator(page_ref, allow_descriptive=True)
        or (
            isinstance(page_ref, str)
            and _FISCAL_ANNEX_PAGE.fullmatch(page_ref) is not None
        )
    ):
        return FISCAL_SUMMARY_NO_PAGE_REF
    return None


def publishable_fiscal_summaries(rows: Iterable[Any]) -> list:
    """The subset of ``rows`` that names a page a reader can turn to."""
    return [r for r in rows if fiscal_summary_withheld_reason(r) is None]


def latest_publishable_fiscal_summary(db):
    """The newest fiscal row that cites a page, or ``None``.

    Named once because three sites want it — the national per-capita budget,
    the civic-figures panel and the debt-sustainability ratios — and each of
    them wrote ``.order_by(fiscal_year.desc()).first()``. That is a publication
    decision wearing the clothes of a lookup: whichever row happens to be
    newest becomes a headline. Gating has to happen before the ``first()``, not
    after, or the answer is "the newest row, and it is withheld, so None" when
    a perfectly publishable older row was available.
    """
    from models import FiscalSummary

    rows = db.query(FiscalSummary).order_by(FiscalSummary.fiscal_year.desc()).all()
    published = publishable_fiscal_summaries(rows)
    return published[0] if published else None


def fiscal_summary_withheld_disclosure(rows: Iterable[Any]) -> Dict[str, Any]:
    """What a response must say about the rows it is not showing.

    Withholding is itself a claim. A history that silently loses FY2017/18
    through FY2021/22 asserts, by omission, that Kenya's national budget series
    begins in 2022 — five real figures between KES 1,924.5B and 3,380.9B simply
    gone, with no way for a reader to know they existed or why they went.

    So this names the years as well as counting them. A count tells a reader
    that something is missing; only the years tell them *what*, which is the
    difference between a disclosure they can act on and an apology.

    Always returns the full shape, zeros and empty lists included. A key that
    appears only when there is something to report cannot be told apart from a
    build that has no disclosure at all.
    """
    withheld: Dict[str, list] = {}
    for row in rows:
        reason = fiscal_summary_withheld_reason(row)
        if reason is not None:
            withheld.setdefault(reason, []).append(row.fiscal_year)

    years = sorted(y for group in withheld.values() for y in group)
    return {
        "count": len(years),
        "by_reason": {
            FISCAL_SUMMARY_NO_PAGE_REF: len(
                withheld.get(FISCAL_SUMMARY_NO_PAGE_REF, [])
            ),
        },
        "fiscal_years": years,
        "criterion": (
            "A fiscal year is published only if its row cites a page of the "
            "document it came from (fiscal_summaries.page_ref)."
        ),
    }


# --------------------------------------------------------------------------
# missing-funds cases (free-form JSON on entity.meta, not a table)
# --------------------------------------------------------------------------


def missing_funds_provenance_failure(
    case: Dict[str, Any], docs: Dict[int, Any]
) -> Optional[str]:
    """Why this missing-funds case may not be published, or None if it may.

    These free-form cases use the same safe URL and direct locator policy as
    audit findings.

    ``docs`` maps ``source_document_id`` -> SourceDocument row, resolved by the
    caller so the check sees the real row rather than trusting an id that may
    point at nothing.
    """
    raw_doc_id = case.get("source_document_id")
    if raw_doc_id in (None, ""):
        return "no_source_document"
    try:
        doc = docs.get(int(raw_doc_id))
    except (TypeError, ValueError):
        return "no_source_document"
    if doc is None:
        return "source_document_not_found"
    if not (getattr(doc, "url", None) or "").strip():
        return "source_document_has_no_url"
    if not safe_source_url(getattr(doc, "url", None)):
        return "source_document_has_invalid_url"
    if not _has_page_locator(case.get("page_ref"), case.get("page_number")):
        return "no_page_reference"
    return None


# --------------------------------------------------------------------------
# county pending bills
# --------------------------------------------------------------------------

#: The bootstrap fixture stamps every row it writes with this dataset.
_BOOTSTRAP_COUNTY_DATASET = "enhanced_county_data.json"


def loan_is_modelled_fixture(loan: Any) -> bool:
    """True when this Loan row is bootstrap's modelled figure, not a source.

    ``enhanced_county_data.json`` does not measure county pending bills, it
    computes them: every one of the 47 is exactly 8% of a budget that is
    itself population x KSh 4,500. The rows are stamped
    ``[{"source": "bootstrap", "dataset": "enhanced_county_data.json"}]``,
    which is how they are told apart from the Treasury BROP rows that carry a
    real per-county figure.
    """
    provenance = getattr(loan, "provenance", None)
    entries = provenance if isinstance(provenance, list) else [provenance]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("dataset") == _BOOTSTRAP_COUNTY_DATASET:
            return True
    return False


#: Where each half of pending bills is read from. Written onto every row's
#: provenance by the pending_bills fetcher, never inferred.
#:
#: * National Government (State Corporations, MDAs): the National Treasury's
#:   Budget Review and Outlook Paper, which is where they are first published.
#: * Counties: the Controller of Budget's full-year County Governments Budget
#:   Implementation Review Report, table of trade payables at 30 June. The BROP
#:   used to be the county source too, but its county table is a reprint of
#:   this one — BROP 2025 Table 10 is the CoB's FY 2024/25 Table 2.9 row for
#:   row, less Narok's 6,151.50m, and BROP 2026 Table 11 is the CoB's
#:   nine-month table (31 March 2026) verbatim, printed after the CoB had
#:   published 30 June 2026 (#238).
NATIONAL_PENDING_BILLS_PUBLICATION = "treasury_brop"
COUNTY_PENDING_BILLS_PUBLICATION = "cob_cbirr_year_end"
#: #265's name for the national publication, kept for its callers.
PENDING_BILLS_PUBLICATION = NATIONAL_PENDING_BILLS_PUBLICATION


def _pending_bills_entries(loan: Any) -> list:
    provenance = getattr(loan, "provenance", None)
    entries = provenance if isinstance(provenance, list) else [provenance]
    return [entry for entry in entries if isinstance(entry, dict)]


def _pending_bills_entity_type(loan: Any, entity_type: Any = None) -> Any:
    if entity_type is None:
        entity_type = getattr(getattr(loan, "entity", None), "type", None)
    return getattr(entity_type, "value", entity_type)


def pending_bills_row_is_published(loan: Any, *, entity_type: Any = None) -> bool:
    """True for a PENDING_BILLS row read from the publication for its side.

    A county row is published when it declares the Controller of Budget's
    year-end report; a national row when it declares the Treasury BROP. Each
    row states its side (``category``) and its publication, both written by
    the fetcher. The attached entity must agree: CoB figures belong to counties,
    and the BROP's two national aggregates belong to national entities. So a BROP
    county row — every county row written before #238 moved the source — is
    not published, and it does not need deleting to stop being served.

    National rows go through the same test (#265). The pending-bills fixture
    wrote eleven per-ministry and state-corporation rows (405.4B — Ministry of
    Health 89.7B, KeNHA 42.3B, ...) beside the BROP's two national lines, under
    lenders that never collide with the BROP's, and every reader summed all
    thirteen: 931.3B against the 525.9B the BROP prints. The BROP's lines
    already cover every MDA and state corporation, so the fixture's rows were
    not more detail, they were the same bills counted again.

    The declaration, not the row's shape. A fixture row and a sourced row look
    identical in the loans table — same category, same lender key, a
    ``cob_pending_bills_etl`` source — so "sourced" used to mean only "not
    bootstrap's modelled 8%", and the pending-bills fixture's invented county
    figures passed. A row that does not declare its publication is not
    published, including rows written before the declaration existed: the
    nightly re-stamps every sourced row, so that is one run of absence, never
    a borrowed figure.
    """
    category = getattr(loan, "debt_category", None)
    if getattr(category, "value", category) != "pending_bills":
        return False
    side = _pending_bills_entity_type(loan, entity_type)
    if _is_published_county_row(loan, entity_type=side):
        return True
    if side != "national":
        return False
    for entry in _pending_bills_entries(loan):
        if (
            entry.get("category") in ("mda", "state_corporation")
            and entry.get("publication") == NATIONAL_PENDING_BILLS_PUBLICATION
        ):
            return True
    return False


def _is_published_county_row(loan: Any, *, entity_type: Any = None) -> bool:
    """A county row as the CoB fetcher writes it, and nothing looser.

    Found by an adversarial pass (#238): the provenance must be the single
    dict the writer writes — the retirement sweep reads only that shape, so a
    list-shaped row would never be retired and would be summed beside its
    successor — and it must state the day the figure is a stock on, since the
    page prints that date beside it.
    """
    category = getattr(loan, "debt_category", None)
    if getattr(category, "value", category) != "pending_bills":
        return False
    provenance = getattr(loan, "provenance", None)
    return (
        _pending_bills_entity_type(loan, entity_type) == "county"
        and isinstance(provenance, dict)
        and provenance.get("category") == "county"
        and provenance.get("publication") == COUNTY_PENDING_BILLS_PUBLICATION
        and pending_bills_row_as_at(loan) is not None
    )


def county_pending_bills_row_is_published(loan: Any) -> bool:
    """The county half of :func:`pending_bills_row_is_published`, alone."""
    return _is_published_county_row(loan)


def pending_bills_row_as_at(loan: Any) -> Optional[str]:
    """The ISO date a published row's figure is stated at, or None.

    Declared by the fetcher from the publication itself — the CoB table's
    caption, the BROP's paragraph — never derived from a fiscal-year label:
    "FY 2025/26" is a year, and the county and national figures are only
    comparable when they are stocks on the same day.
    """
    from datetime import date

    for entry in _pending_bills_entries(loan):
        value = entry.get("as_at")
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                date.fromisoformat(value)  # "2026-99-99" is not a day
            except ValueError:
                continue
            return value
    return None


#: Why a published county figure carries a note. Each is a fact the report
#: states about itself, read by the parser; the API passes the codes and the
#: page words them.
_COUNTY_PENDING_BILLS_NOTE_CODES = (
    "cob_marked_inconsistent",
    "assembly_not_printed",
    "chapter_table_differs",
)


def county_pending_bills_details(loans: Iterable[Any]) -> Dict[str, Any]:
    """The as-at date, source and notes behind a county's published figure.

    ``{"as_at", "fiscal_year", "table", "source_url", "notes"}``, each None (or
    an empty list) when no published row carries it. ``notes`` are dicts with
    a ``code`` from :data:`_COUNTY_PENDING_BILLS_NOTE_CODES` and the figures
    the note quotes.
    """
    details: Dict[str, Any] = {
        "as_at": None, "fiscal_year": None, "table": None,
        "source_url": None, "notes": [],
    }
    selection = select_county_pending_bills(loans)
    details["absent_reason"] = selection["absent_reason"]
    details["selection_policy"] = "latest_common_reporting_date"
    details["reporting_date"] = selection["as_at"]
    details["sources"] = selection["sources"]
    for loan in selection["rows"]:
        for entry in _pending_bills_entries(loan):
            details["as_at"] = pending_bills_row_as_at(loan)
            for key in ("fiscal_year", "table", "source_url"):
                details[key] = entry.get(key)
            for note in entry.get("reader_notes") or []:
                if isinstance(note, dict) and note.get("code") in _COUNTY_PENDING_BILLS_NOTE_CODES:
                    if note not in details["notes"]:
                        details["notes"].append(dict(note))
    return details


def pending_bills_row_amount(loan: Any) -> Optional[float]:
    """A pending-bills row's amount as a publishable figure, or None.

    ``outstanding``, falling back to ``principal`` only when outstanding is
    absent — never when it is 0, because a published zero is a figure. Only a
    finite, non-negative number counts: NaN reached ``/counties`` as a float
    JSON cannot encode (HTTP 500 for all 47 counties), and a bool is not an
    amount.
    """
    import math

    amount = getattr(loan, "outstanding", None)
    if amount is None:
        amount = getattr(loan, "principal", None)
    if amount is None or isinstance(amount, bool):
        return None
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def county_pending_bills(loans: Iterable[Any]) -> Optional[float]:
    """A county's pending bills from the CoB's year-end report, or None.

    ``None`` means "not published", and the caller must render it as absence
    rather than as zero. The distinction is the whole point here: Nandi did
    not report trade payables at 30 June 2026 — the CoB says so, and prints
    "-" across its row with a "0" in the ratio column — so Nandi's pending
    bills are unknown. A zero would say the county owes nothing, which is a
    different claim and one nobody has made.

    Modelled rows are excluded rather than used as a fallback. A fallback
    chain whose every rung is the same fixture is not a fallback, and until
    this existed the county list served the modelled figure for ALL 47
    counties — 8.7x below the Treasury's published total, and 21.9x below it
    for Nairobi — while the real BROP figures sat unused in the same table.

    Every endpoint that shows a county's pending bills reads it through here —
    the county list, the map, the detail page, compare, ``/pending-bills`` and
    the debt page's top counties — so they cannot disagree.
    """
    return select_county_pending_bills(loans)["amount"]


def select_county_pending_bills(loans: Iterable[Any], *, as_at=None) -> Dict[str, Any]:
    """Select a stock, never sum snapshots or choose a competing source by ID.

    Callers spanning counties supply the latest common declared reporting day.
    One county's direct reader selects its newest day. Exact duplicate evidence
    is idempotent; differing amount, source, period, table, batch, currency or
    qualifications is a conflict. Missing latest amounts never revive history.
    """
    candidates = [loan for loan in loans or [] if _is_published_county_row(loan)]
    day = as_at or max((pending_bills_row_as_at(l) for l in candidates), default=None)
    latest = [l for l in candidates if pending_bills_row_as_at(l) == day]

    def evidence(l):
        p = l.provenance
        return {
            "source_document_id": getattr(l, "source_document_id", None),
            "source_url": p.get("source_url"),
            "as_at": day,
            "fiscal_year": p.get("fiscal_year"),
            "table": p.get("table"),
            "publication_batch": p.get("publication_batch"),
            "currency": getattr(l, "currency", None),
            "reader_notes": p.get("reader_notes") or [],
            "page_ref": getattr(l, "page_ref", None) or p.get("page_ref"),
            "page": p.get("page"),
            "amount": pending_bills_row_amount(l),
        }

    import json

    sources = {json.dumps(evidence(l), sort_keys=True): evidence(l) for l in latest}
    reason = (
        "not_reported_at_latest_date"
        if not latest
        else "conflicting_same_date_pending_sources"
        if len(sources) > 1
        else "pending_amount_not_reported"
        if pending_bills_row_amount(latest[0]) is None
        else "unsupported_pending_currency"
        if getattr(latest[0], "currency", None) != "KES"
        else None
    )
    # Representative row only for byte-equivalent evidence, never max-ID wins.
    selected = latest[:1] if reason is None else []
    return {
        "amount": pending_bills_row_amount(selected[0]) if selected else None,
        "rows": selected,
        "as_at": day,
        "absent_reason": reason,
        "sources": [sources[k] for k in sorted(sources)[:20]],
        "source_count": len(sources),
        "sources_truncated": len(sources) > 20,
    }


def county_pending_reporting_date(db) -> Optional[str]:
    """One bounded-width query of county stocks; no finding text or source N+1."""
    from models import Loan, Entity, EntityType, DebtCategory

    rows = (
        db.query(Loan.provenance)
        .join(Entity, Loan.entity_id == Entity.id)
        .filter(
            Entity.type == EntityType.COUNTY,
            Loan.debt_category == DebtCategory.PENDING_BILLS,
        )
        .all()
    )
    from types import SimpleNamespace

    candidates = [
        SimpleNamespace(
            provenance=r.provenance,
            debt_category=DebtCategory.PENDING_BILLS,
            entity=SimpleNamespace(type=EntityType.COUNTY),
        )
        for r in rows
    ]
    return max(
        (pending_bills_row_as_at(l) for l in candidates if _is_published_county_row(l)),
        default=None,
    )


def county_loans_at_reporting_date(loans, as_at):
    """Retain borrowing rows and only the common-date pending observations."""
    return [
        l
        for l in loans
        if not _is_published_county_row(l) or pending_bills_row_as_at(l) == as_at
    ]


def annual_fiscal_year(value):
    """An annual FY whose start and end are representable Python dates."""
    match = re.fullmatch(
        r"(?:FY\s*)?(\d{4})/(\d{2}|\d{4})", str(value or "").strip(), re.I
    )
    if not match:
        return None
    start = int(match[1])
    if not 1 <= start < 9999:
        return None
    end = start + 1
    declared_end = int(match[2])
    if declared_end != (end if len(match[2]) == 4 else end % 100):
        return None
    return start, end


def pending_budget_compatible(loans, fiscal_period, *, budget_currency="KES") -> bool:
    """Only a year-end stock and budget for the same Kenyan fiscal year."""
    selection = select_county_pending_bills(loans)
    if selection["amount"] is None:
        return False
    return pending_period_compatible(
        selection["as_at"],
        selection["rows"][0].provenance.get("fiscal_year"),
        fiscal_period,
        budget_currency=budget_currency,
    )


def pending_period_compatible(
    as_at, fiscal_year, fiscal_period, *, budget_currency="KES"
):
    from datetime import date

    if not fiscal_period or budget_currency != "KES":
        return False
    try:
        end = date.fromisoformat(fiscal_period["end_date"][:10])
        start = date.fromisoformat(fiscal_period["start_date"][:10])
    except (TypeError, KeyError, ValueError):
        return False
    if end.year < 2:
        return False
    fy = annual_fiscal_year(fiscal_year)
    return bool(
        fy
        and start == date(end.year - 1, 7, 1)
        and end == date(end.year, 6, 30)
        and as_at == end.isoformat()
        and fy == (start.year, end.year)
    )


# --------------------------------------------------------------------------
# figures read from a static file rather than a fact table
# --------------------------------------------------------------------------

# A URL with no path beyond "/" is a publisher's homepage. It tells a reader
# who published something, never which document or which page, so it cannot
# support a figure. `backend/data/reference/oag_national_audit_data.json` cites exactly this.
_DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx")


def file_source_provenance_failure(meta: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why a figure read from a static file may not be published, or None.

    Same rule as everywhere else — a figure needs a document and a page — but
    applied to a JSON file's own ``metadata`` block instead of a database row.

    ``backend/data/reference/oag_national_audit_data.json`` holds 24 amounts summing to
    KES 3,313,000,000,000: the *same* fabricated dataset as the 24 quarantined
    ``audits`` rows (22 of 24 amounts byte-identical), attributed to a named
    Auditor-General's report. Its only citation is ``https://www.oagkenya.go.ke``.
    Gating the database while serving this file would leave the window open
    (``AUDIT_FINDINGS`` F5.3/F5.4; ``kenya-legal``).
    """
    if not meta:
        return "no_source_metadata"

    url = ""
    for key in ("source_url", "document_url", "url", "source"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            url = value
            break
    if not url:
        return "no_source_url"
    if not safe_source_url(url):
        return "source_url_is_invalid"

    path = urlsplit(url).path.strip("/")
    if not path:
        return "source_url_is_a_homepage_not_a_document"
    if not path.lower().endswith(_DOCUMENT_EXTENSIONS):
        return "source_url_is_not_a_document"

    if not _has_page_locator(*(meta.get(k) for k in ("page_ref", "page_number", "page"))):
        return "no_page_reference"
    return None


def withheld_file_figure(reason: str) -> Dict[str, Any]:
    """The shape an unpublishable file-sourced figure takes in a response.

    Never ``0`` and never the stale string — a reader must be able to tell
    "not published" from "published as zero".
    """
    return {"value": None, "reason": reason}


# --------------------------------------------------------------------------
# county-level debt instruments
# --------------------------------------------------------------------------
# the CBK Treasury bond register (debt_instruments)
# --------------------------------------------------------------------------
#
# NOT the same thing as ``county_debt_instrument_failure`` below, which governs
# county-level rows in ``loans``. This governs ``debt_instruments`` — the
# maturity-and-coupon register behind /api/v1/debt/instruments.

#: ISO 6166: two letters, nine alphanumerics, one check digit. Kenyan
#: securities are KE + ten digits, which this admits without hardcoding KE.
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

BOND_REGISTER_NO_URL = "source_document_has_no_url"
BOND_REGISTER_NO_ISIN = "no_isin_locator"
BOND_REGISTER_NO_FACE_VALUE = "no_face_value"


def bond_register_withheld_reason(row, source_document=None) -> Optional[str]:
    """Why this bond-register row may not be published, or ``None`` if it may.

    WHY THIS TABLE DOES NOT TAKE ``page_ref``
    -----------------------------------------
    ``fiscal_summaries`` and ``audits`` are gated on a page because they come
    from PDFs and a page is what a reader turns to. This register does not:
    source document 2432 is ``https://www.centralbank.go.ke/bills-bonds/treasury-bonds/``,
    which answers ``content-type: text/html``. It is a web table. It has no
    pages, all 56 production rows carry ``page_ref IS NULL``, and they are
    right to. Requiring one would withhold the whole maturity ladder over a
    category error rather than a provenance gap.

    A ``page_ref`` synthesised from the row's own ``isin`` and ``issue_no`` was
    considered and rejected: a locator computed from the data it locates can
    never be absent, so a gate on it can never fail. That is the constant this
    function replaces, wearing a better disguise.

    WHAT A READER ACTUALLY USES
    ---------------------------
    They open the CBK table and look for the security, and what finds it there
    is the **ISIN**. It is a first-class column, it is what CBK keys the table
    on, and — unlike a derived string — it can be malformed or missing. So the
    rule is the one ``instrument_writer`` already states in a comment and never
    checked: the row resolves to a document a reader can open, and carries the
    key that locates it inside that document.

    Reasons are ordered: an unopenable source first, since no locator helps
    when there is nothing to open.
    """
    url = getattr(source_document, "url", None) if source_document is not None else None
    if url is None or not str(url).strip():
        return BOND_REGISTER_NO_URL

    isin = getattr(row, "isin", None)
    if isin is None or not _ISIN_RE.match(str(isin).strip().upper()):
        return BOND_REGISTER_NO_ISIN

    face_value = getattr(row, "face_value", None)
    if face_value is None or Decimal(str(face_value)) <= 0:
        return BOND_REGISTER_NO_FACE_VALUE

    return None


BOND_REGISTER_QUARANTINED = "quarantined"


def bond_register_publication_failure(row, source_document=None) -> Optional[str]:
    """Why a reader must not be shown this row: the rule OR a stored quarantine.

    Two independent things can hold a row back, and the endpoint has to respect
    both:

    * the rule in :func:`bond_register_withheld_reason`, recomputed per request
      so a column written by an older seeder cannot publish what the current
      rule rejects; and
    * ``publishable = False`` in the column itself, which is the general
      quarantine channel — an operator or a future cause marking one row —
      and predates this function. Ignoring it would un-quarantine every row
      held back for any reason this rule does not happen to name.

    Fail closed: either one withholds. ``quarantine_reason`` is preferred as
    the word when the column is the cause, so the response repeats what is
    stored rather than inventing a second vocabulary for it.
    """
    reason = bond_register_withheld_reason(
        row,
        source_document
        if source_document is not None
        else getattr(row, "source_document", None),
    )
    if reason is not None:
        return reason
    if getattr(row, "publishable", True) is False:
        return getattr(row, "quarantine_reason", None) or BOND_REGISTER_QUARANTINED
    return None


def publishable_bond_register_rows(rows: Iterable[Any], source_document=None) -> list:
    """The subset of ``rows`` a reader could check against the CBK table."""
    return [
        r
        for r in rows
        if bond_register_publication_failure(r, source_document) is None
    ]


def bond_register_withheld_disclosure(rows: Iterable[Any]) -> Dict[str, Any]:
    """What the response must say about register rows the GATE held back.

    Deliberately separate from the ``withheld_isins`` the response already
    carries. Those are six securities the EXTRACTOR could not settle —
    ambiguous maturities — recorded on the source document. This is a different
    fact with a different remedy, and folding the two together would let a
    reader think the six covered both.

    Always the full shape, zeros included.
    """
    by_reason: Dict[str, int] = {}
    for row in rows:
        reason = bond_register_publication_failure(row)
        if reason is not None:
            by_reason[reason] = by_reason.get(reason, 0) + 1
    return {"count": sum(by_reason.values()), "by_reason": by_reason}


# --------------------------------------------------------------------------

# Creditors that lend to sovereigns, not to county governments. Article 212 of
# the Constitution and s.58 of the PFM Act 2012 let a county borrow only where
# the national government guarantees the loan and the county assembly approves
# it; a county cannot contract external debt directly. So a county-level row
# naming one of these is either (a) a national loan misattributed to a county,
# or (b) invented. Production carries rows reading
# "World Bank (County Infrastructure)" — KES 13.1B against Nairobi, 6.3B
# against Mombasa, rendered as "81.2% of total debt" on the county page — and
# that lender string appears NOWHERE in this repository: no fixture, no seeder,
# no migration. It is an orphaned row asserting that a named county owes a
# named multilateral. Credibility audit F15.
_SOVEREIGN_ONLY_CREDITORS = (
    "world bank",
    "ida",
    "ibrd",
    "african development bank",
    "afdb",
    "international monetary fund",
    "imf",
    "eurobond",
    "exim",
    "jica",
    "afd",
    "kfw",
    "syndicated",
    "bilateral",
    "multilateral",
)


#: Words that would appear in a document actually authorising a county to
#: borrow from a sovereign-only creditor.  Article 212 of the Constitution
#: allows county borrowing only where the national government guarantees the
#: loan and the county assembly approves it, so the evidence is a guarantee
#: instrument, a gazette notice, or a county loan register — not a national
#: debt bulletin that happens to list the creditor.
_BORROWING_AUTHORISATION_EVIDENCE = (
    "guarantee",
    "guaranteed",
    "loan register",
    "borrowing approval",
    "county assembly approval",
    "gazette",
    "on-lending",
    "onlending",
    "subsidiary loan agreement",
)


def county_debt_instrument_failure(loan, source_document=None) -> Optional[str]:
    """Why this county-level debt row may not be published, or None if it may.

    Deliberately NOT a string blocklist: the test is "does this row name a
    creditor that only lends to sovereigns, and can it show the instrument that
    let a county borrow from one?".

    Checking only that ``source_document_id`` is set would be a check that
    cannot fail — the column is ``nullable=False`` (models.py:281-283) and the
    baseline migration enforces it, so every persisted row has one.  The FK
    alone also proves nothing about *what* the document is: production rows
    carry a CBK national debt bulletin, which lists the creditor but does not
    authorise any county to borrow from it.

    So the document is resolved and read.  A row passes only when the document
    it points at reads like a borrowing authorisation.  Nothing in production
    does today, which is the finding — and the gate can still go green, which
    is what makes it a gate rather than a filter.

    ``source_document`` may be passed explicitly by callers that already have
    it loaded; otherwise the ORM relationship is used.
    """
    lender = (getattr(loan, "lender", "") or "").lower()
    if not any(name in lender for name in _SOVEREIGN_ONLY_CREDITORS):
        return None

    doc = source_document
    if doc is None:
        doc = getattr(loan, "source_document", None)
    if doc is None:
        return "external_creditor_no_source_document"

    haystack = " ".join(
        str(getattr(doc, field, "") or "")
        for field in ("title", "publisher", "url")
    ).lower()
    if not any(word in haystack for word in _BORROWING_AUTHORISATION_EVIDENCE):
        return "external_creditor_document_is_not_a_borrowing_authorisation"
    return None


def cpi_extraction_digest(payload) -> str:
    """Bind the reviewed table payload to the hashed document declaration."""
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def economic_publication_failure(row, db) -> Optional[str]:
    """CPI index publication requires an approved, matching source chain.

    Other economic measures retain their existing publication policy; this
    does not certify annual World Bank or monthly inflation source acceptance.
    The reader checks stored evidence, not remote PDF availability or bytes.
    """
    from models import Country, Extraction
    from decimal import InvalidOperation

    try:
        value = Decimal(str(row.value)) if type(row.value) is not bool else None
    except (InvalidOperation, ValueError, TypeError):
        value = None
    if value is None or not value.is_finite():
        return "non-finite economic value"
    if row.indicator_type.lower() != "cpi":
        return None
    if row.publishable is not True:
        return "CPI not approved for publication"
    if row.quarantine_reason:
        return "CPI quarantined"
    meta = row.meta
    if not isinstance(meta, dict) or meta.get("bootstrap"):
        return "CPI missing reviewed measure"
    if (
        value < 0
        or row.entity_id is not None
        or row.unit != "index_2019_02_100"
        or meta.get("base_period") != "2019-02"
        or meta.get("frequency") != "monthly"
        or meta.get("measure") != "overall consumer price index, February 2019 = 100"
        or getattr(row.basis, "value", row.basis) not in {"actual", "ACTUAL"}
    ):
        return "CPI base or measure conflict"
    source = (
        db.get(SourceDocument, row.source_document_id)
        if row.source_document_id
        else None
    )
    if source is None:
        return "CPI missing document"
    try:
        url = urlsplit(source.url or "")
    except ValueError:
        return "CPI unusable official document"
    country = db.get(Country, source.country_id)
    if (
        source.publisher != "Kenya National Bureau of Statistics"
        or getattr(source.status, "name", source.status) != "AVAILABLE"
        or getattr(source.doc_type, "name", source.doc_type) != "REPORT"
        or url.scheme != "https"
        or url.netloc != "www.knbs.or.ke"
        or not url.path.startswith("/wp-content/uploads/")
        or not url.path.endswith(".pdf")
        or url.query
        or url.fragment
        or source.content_type != "application/pdf"
        or source.http_status != 200
        or country is None
        or country.iso_code != "KEN"
    ):
        return "CPI unusable official document"
    source_meta = source.meta if isinstance(source.meta, dict) else {}
    sha = source_meta.get("sha256")
    if (
        not isinstance(sha, str)
        or not re.fullmatch(r"[0-9a-f]{64}", sha)
        or row.source_hash != sha
        or not isinstance(source.md5, str)
        or not re.fullmatch(r"[0-9a-f]{32}", source.md5)
    ):
        return "CPI document hash conflict"
    extraction = db.get(Extraction, row.extraction_id) if row.extraction_id else None
    if (
        extraction is None
        or extraction.source_document_id != source.id
        or type(row.source_page) is not int
        or row.source_page <= 0
        or extraction.page_number != row.source_page
        or row.page_ref != f"p.{row.source_page} / Table 1"
    ):
        return "CPI missing matching page/extraction"
    payload = extraction.extracted_json
    if (
        not isinstance(payload, dict)
        or payload.get("base_period") != "February 2019 = 100"
        or payload.get("measure") != "national overall CPI"
        or payload.get("table") != "Table 1"
        or not isinstance(payload.get("observations"), dict)
    ):
        return "CPI extraction measure conflict"
    try:
        payload_digest = cpi_extraction_digest(payload)
    except (TypeError, ValueError):
        return "CPI malformed extraction payload"
    if source_meta.get("reviewed_table1_sha256") != payload_digest:
        return "CPI reviewed extraction hash conflict"
    observed = payload["observations"].get(row.indicator_date.date().isoformat())
    try:
        extracted_value = Decimal(str(observed)) if type(observed) is not bool else None
    except (InvalidOperation, ValueError, TypeError):
        extracted_value = None
    if (
        extracted_value is None
        or not extracted_value.is_finite()
        or extracted_value != value
    ):
        return "CPI extraction value conflict"
    return None


def economic_publication_rows(query, db, limit):
    """Filter before the public limit; return reasons for examined omissions."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("economic publication limit must be 1..1000")
    rows, withheld = [], {}
    for row in query.yield_per(100):
        reason = economic_publication_failure(row, db)
        if reason:
            withheld[reason] = withheld.get(reason, 0) + 1
        else:
            rows.append(row)
            if len(rows) >= limit:
                break
    if withheld:
        logger.warning("Withheld economic observations: %s", withheld)
    return rows, withheld

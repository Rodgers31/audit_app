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
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import and_ as sa_and
from sqlalchemy import func
from sqlalchemy import or_ as sa_or
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Imported unguarded on purpose. A try/except here would set a flag nobody
# reads and let callers build a query against ``None``, turning a missing model
# into an AttributeError deep inside a request instead of a clear failure at
# import. The gate must fail closed, and loudly.
from models import Audit, SourceDocument


# --------------------------------------------------------------------------
# audits
# --------------------------------------------------------------------------


def _source_document_is_resolvable():
    """The URL half of the gate, named once so it cannot drift.

    Extracted while fixing the PR #135 reason-breakdown finding: the
    per-reason count has to ask "did THIS clause fail?", and re-typing the
    subquery there would have created a second copy of the rule — the exact
    thing this module exists to prevent.
    """
    return Audit.source_document_id.in_(
        select(SourceDocument.id).where(
            SourceDocument.url.isnot(None),
            func.length(func.trim(SourceDocument.url)) > 0,
        )
    )


def _has_page_locator(*candidates) -> bool:
    """True only if some candidate names a page a reader could turn to.

    Reported by review on PR #135: the previous test was ``in (None, "")``, so
    ``page_ref="   "`` and ``page_number=0`` both read as "present" and
    published a case that cannot be located. Whitespace is stripped, and a
    numeric locator must be POSITIVE — page 0 of a 400-page report is not a
    citation. A non-numeric string (``"p. 42"``, ``"Annex VII"``) is accepted
    on its own terms once it has any non-whitespace content.
    """
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, bool):  # a bool is an int; never a page number
            continue
        if isinstance(value, (int, float)):
            if value > 0:
                return True
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            return float(text) > 0
        except ValueError:
            return True  # a real textual locator, e.g. "p. 42" / "Annex VII"
    return False


#: Whitespace that ``str.strip()`` removes but SQL ``trim()`` does not — SQL
#: trims spaces only, so a page_ref of "\t\n" would read as present.
_WHITESPACE = (" ", "\t", "\n", "\r")

#: The characters a bare number is made of, minus the digits 1-9. Removing
#: these from a value leaves nothing only when the value was a number built
#: entirely from zeros, signs and a decimal point: "0", "00", "0.0", "-0".
_ZERO_ISH = ("0", "+", "-", ".")


def _has_page_locator_criterion(column):
    """SQL form of :func:`_has_page_locator`, for use inside a query.

    There are now two expressions of one rule — this and the Python predicate
    — because the audits gate runs in SQL at 47 call sites while the fiscal and
    missing-funds gates run over materialised rows. Two copies of a rule that
    must agree is exactly the drift this module exists to prevent, so they are
    not trusted to stay in step: ``tests/test_audits_page_locator_gate.py``
    runs both over one shared table of cases and fails if they ever disagree.

    Expressed with ``replace`` rather than a regular expression because the
    dialects do not share one — Postgres has ``~``, SQLite does not — and a
    criterion that behaves differently under test than in production would be
    worse than no criterion at all.
    """
    squeezed = column
    for ch in _WHITESPACE:
        squeezed = func.replace(squeezed, ch, "")
    bare = squeezed
    for ch in _ZERO_ISH:
        bare = func.replace(bare, ch, "")
    return sa_and(
        column.isnot(None),
        func.length(squeezed) > 0,   # not blank, whatever the whitespace
        func.length(bare) > 0,       # not "0" / "00" / "0.0" / "-0"
        ~squeezed.like("-%"),        # not a negative page number
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

    Reported by review on PR #135. There are two independent withholding
    causes — an unresolvable source document, and finding text that is
    unreadable ``(cid:NN)`` glyph codes — and ``count_withheld_audits``
    collapsed them into one integer that every caller then labelled "source
    document has no resolvable URL". A row withheld for unreadable text was
    reported under a reason that did not apply to it.

    The backfill in this module already tracks the two separately
    (``no_url_count`` vs ``withheld_cid``), which is what makes the runtime
    collapse a defect rather than a limitation of the data.

    Keys are the same slugs the backfill writes to ``quarantine_reason``, so a
    response, a log line and the column all say the same word. Always returns
    every known reason (0 where none apply) so a caller can render a stable
    shape, and the values always sum to :func:`count_withheld_audits`.
    """
    def _count(criterion):
        q = db.query(func.count(Audit.id)).filter(criterion)
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
    resolvable = _source_document_is_resolvable()
    readable = _finding_text_is_readable()
    located = _has_page_locator_criterion(Audit.page_ref)

    total = _count(~publishable_audit_criterion())
    reasons = {
        "source_document_has_no_url": _count(~resolvable),
        "finding_text_unreadable_cid": _count(sa_and(resolvable, ~readable)),
        "no_page_reference": _count(sa_and(resolvable, readable, ~located)),
    }

    # The three clauses above are the whole of the criterion, so a residual
    # means a fourth clause was added without a word for it. Report it rather
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
    q = db.query(func.count(Audit.id)).filter(~publishable_audit_criterion())
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

    crit = publishable_audit_criterion()
    # Which clause failed? In order: URL (the commonest and most fundamental
    # defect), then text integrity, then the locator. A row can fail more than
    # one; the earliest reason wins, and the buckets are disjoint so no row is
    # counted or stamped twice.
    #
    # These reuse the same three named clauses the criterion is built from,
    # rather than restating them. The URL clause used to be re-typed here as a
    # second copy of `_source_document_is_resolvable()`.
    resolvable = _source_document_is_resolvable()
    readable = _finding_text_is_readable()
    located = _has_page_locator_criterion(Audit.page_ref)

    no_url = ~resolvable
    unreadable = sa_and(resolvable, ~readable)
    unlocated = sa_and(resolvable, readable, ~located)

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
    session.flush()
    stats = {
        "published": published,
        "withheld": no_url_count + withheld_cid + withheld_no_page,
    }
    logger.info(
        "publishable backfill: %d published, %d withheld "
        "(%d no-url, %d cid, %d no-page)",
        stats["published"],
        stats["withheld"],
        no_url_count,
        withheld_cid,
        withheld_no_page,
    )
    return stats


def log_withheld_audits(context: str, withheld: int, published: int) -> None:
    """Emit the withholding at WARNING, with enough detail to act on."""
    if withheld:
        logger.warning(
            "%s: %d audit finding(s) withheld — source document has no "
            "resolvable URL; %d published",
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

    This is a Python predicate rather than a SQL criterion on purpose. The
    locator rule already exists exactly once, in :func:`_has_page_locator`, and
    restating "is this a positive page number?" in SQL would need a second copy
    of it whose regex differs between Postgres and SQLite. Two copies of a rule
    that must agree is the drift this module exists to prevent.
    ``fiscal_summaries`` holds 29 rows and every read site already materialises
    them, so the SQL form would buy nothing.
    """
    if not _has_page_locator(getattr(row, "page_ref", None)):
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

    Stricter than the audits gate because it can be: these cases are free-form
    JSON and can carry a page reference. See the module docstring's asymmetry
    note.

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


def county_pending_bills(loans: Iterable[Any]) -> Optional[float]:
    """A county's pending bills from SOURCED rows, or None if it has none.

    ``None`` means "not published", and the caller must render it as absence
    rather than as zero. The distinction is the whole point here: Narok did
    not submit pending-bills data for FY 2024/25 — the BROP says so in its own
    footnote, and prints an empty row for it — so Narok's pending bills are
    unknown. A zero would say the county owes nothing, which is a different
    claim and one nobody has made.

    Modelled rows are excluded rather than used as a fallback. A fallback
    chain whose every rung is the same fixture is not a fallback, and until
    this existed the county list served the modelled figure for ALL 47
    counties — 8.7x below the Treasury's published total, and 21.9x below it
    for Nairobi — while the real BROP figures sat unused in the same table.
    """
    total = 0.0
    found = False
    for loan in loans or []:
        category = getattr(loan, "debt_category", None)
        if getattr(category, "value", category) != "pending_bills":
            continue
        if loan_is_modelled_fixture(loan):
            continue
        amount = getattr(loan, "outstanding", None) or getattr(loan, "principal", None)
        if amount is None:
            continue
        total += float(amount)
        found = True
    return total if found else None


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
        if isinstance(value, str) and value.strip().lower().startswith("http"):
            url = value.strip()
            break
    if not url:
        return "no_source_url"

    # Strip scheme + host; whatever remains is the path to a document.
    remainder = url.split("://", 1)[-1]
    path = remainder.split("/", 1)[1] if "/" in remainder else ""
    path = path.split("?", 1)[0].split("#", 1)[0].strip("/")
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

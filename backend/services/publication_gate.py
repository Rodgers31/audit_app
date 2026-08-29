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
3. **No page locator is required for audits.** See the asymmetry note below.

ASYMMETRY WITH THE MISSING-FUNDS GATE — deliberate, and why
-----------------------------------------------------------
``missing_funds_provenance_failure`` requires *document + URL + page reference*.
``publishable_audit_criterion`` requires *document + URL* only. That is not an
oversight and not laziness:

* ``Audit`` has **no page column**. ``page_ref`` is defined on ``BudgetLine``
  (``models.py:202``), not on ``Audit``; ``Audit.provenance`` carries
  ``source_url``/``reference``/``audit_year`` but no page number.
* Requiring a page on audits today would withhold **audit id 902** — the single
  genuine extraction in the table (KES 592,062,382,245, traced to the live PDF
  ``AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf``, doc 2392).
  Withholding the one real row to satisfy a uniformity rule would be worse than
  the asymmetry.

The missing-funds cases *are* free-form JSON and *can* carry a page, so the
stricter check costs nothing there and is kept.

**Close this gap in Stage 1** by adding ``page_ref`` to ``audits`` alongside the
``publishable`` column, backfilling it during extraction, and then tightening
``publishable_audit_criterion`` to require it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

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


def publishable_audit_criterion():
    """SQL criterion: this finding resolves to a document a reader can open.

    Apply to **every** public query that reads ``audits``::

        db.query(...).filter(publishable_audit_criterion())

    25 of the 27 rows in ``audits`` hang off source_document 1836 — an
    authoritative-looking OAG title whose ``url`` and ``md5`` are both NULL and
    whose ``status`` is nevertheless ``AVAILABLE`` — contributing KES 3.313T of
    the KES 3.91T ``/audits`` headline (``AUDIT_FINDINGS`` F5.4).

    Because ``Audit.source_document_id`` is ``nullable=False`` and this is an
    ``IN (SELECT ...)``, the criterion already implies *the FK target exists*
    and *its URL is non-empty*. See the module docstring for what it does not
    imply.
    """
    return sa_and(
        Audit.source_document_id.in_(
            select(SourceDocument.id).where(
                SourceDocument.url.isnot(None),
                func.length(func.trim(SourceDocument.url)) > 0,
            )
        ),
        # Text integrity. Audit 902 — the row previously described as "the
        # single genuine extraction" — is 89.6% ``(cid:NN)`` glyph codes ending
        # in the report's VISION statement: the PDF's cover page, not a
        # finding, with an empty ``amount_involved``.
        #
        # A.4 quarantines text that is >20% ``(cid:``; expressing a ratio in
        # SQL is awkward, so this withholds a finding containing ANY such
        # token. That is deliberately stricter than A.4 and is the safe
        # direction while the OCR-retry path A.4 assumes does not yet exist
        # (Stage 2). Revisit when it does.
        sa_or(
            Audit.finding_text.is_(None),
            ~Audit.finding_text.contains("(cid:"),
        ),
    )


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
    published = session.execute(
        update(Audit)
        .where(crit)
        .values(publishable=True, quarantine_reason=None)
        .execution_options(synchronize_session=False)
    ).rowcount
    # Which clause failed? URL first (the commoner failure), then text
    # integrity — a row can fail both; the URL reason wins as the more
    # fundamental defect.
    no_url = ~Audit.source_document_id.in_(
        select(SourceDocument.id).where(
            SourceDocument.url.isnot(None),
            func.length(func.trim(SourceDocument.url)) > 0,
        )
    )
    session.execute(
        update(Audit)
        .where(no_url)
        .values(publishable=False, quarantine_reason="source_document_has_no_url")
        .execution_options(synchronize_session=False)
    )
    withheld_cid = session.execute(
        update(Audit)
        .where(~no_url, ~crit)
        .values(publishable=False, quarantine_reason="finding_text_unreadable_cid")
        .execution_options(synchronize_session=False)
    ).rowcount
    no_url_count = session.execute(
        select(func.count(Audit.id)).where(no_url)
    ).scalar_one()
    session.flush()
    stats = {"published": published, "withheld": no_url_count + withheld_cid}
    logger.info(
        "publishable backfill: %d published, %d withheld (%d no-url, %d cid)",
        stats["published"],
        stats["withheld"],
        no_url_count,
        withheld_cid,
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
    if case.get("page_ref") in (None, "") and case.get("page_number") in (None, ""):
        return "no_page_reference"
    return None


# --------------------------------------------------------------------------
# figures read from a static file rather than a fact table
# --------------------------------------------------------------------------

# A URL with no path beyond "/" is a publisher's homepage. It tells a reader
# who published something, never which document or which page, so it cannot
# support a figure. `apis/oag_national_audit_data.json` cites exactly this.
_DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx")


def file_source_provenance_failure(meta: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why a figure read from a static file may not be published, or None.

    Same rule as everywhere else — a figure needs a document and a page — but
    applied to a JSON file's own ``metadata`` block instead of a database row.

    ``apis/oag_national_audit_data.json`` holds 24 amounts summing to
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

    if all(meta.get(k) in (None, "") for k in ("page_ref", "page_number", "page")):
        return "no_page_reference"
    return None


def withheld_file_figure(reason: str) -> Dict[str, Any]:
    """The shape an unpublishable file-sourced figure takes in a response.

    Never ``0`` and never the stale string — a reader must be able to tell
    "not published" from "published as zero".
    """
    return {"value": None, "reason": reason}

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

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised implicitly by every import site
    from models import Audit, SourceDocument

    MODELS_AVAILABLE = True
except Exception:  # pragma: no cover
    Audit = None  # type: ignore[assignment]
    SourceDocument = None  # type: ignore[assignment]
    MODELS_AVAILABLE = False


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
    return Audit.source_document_id.in_(
        select(SourceDocument.id).where(
            SourceDocument.url.isnot(None),
            func.length(func.trim(SourceDocument.url)) > 0,
        )
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

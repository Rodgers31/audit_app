"""Own the ``Entity.meta['stalled_projects*']`` keys, and write COB's rows there.

Until issue #230 this writer copied 25 invented records from
``seeding/real_data/stalled_projects.json`` into four meta keys on 21
counties every night. What remains of them in production is removed here, by
the nightly, rather than by hand-run SQL, so the clean-up is reviewed,
repeatable and recorded in the ingestion log like any other write.

Ownership is by prefix: every meta key starting ``stalled_projects`` belongs
to this domain. A key another domain writes must not share it.

Shape written (``schema: 2``)::

    meta["stalled_projects"] = {
        "schema": 2,
        "source": {...edition: publisher, title, url, wpdmdl, sha256, as_of...},
        "rows": [...one per table row, each with source_url/source_page/as_of/
                 reported_by and the cells exactly as printed...],
        "summary": {...COB's sentence for this county, verbatim + parsed...},
        "statement": {...COB's words when the county reported nothing...},
        "table_2_6": {...this county's line in the national table...},
        "reconciliation": {...every comparison, agreeing or not...},
        "withheld_fields": [...money fields not published, and why...],
    }
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .cob_parser import MONEY_FIELDS, REPORTED_BY, normalise_county

logger = logging.getLogger(__name__)

OWNED_PREFIX = "stalled_projects"
SCHEMA = 2
PUBLISHER = "Office of the Controller of Budget"


def owned_keys(meta: dict | None) -> list[str]:
    return sorted(k for k in (meta or {}) if k.startswith(OWNED_PREFIX))


def _is_current(meta: dict | None) -> bool:
    value = (meta or {}).get(OWNED_PREFIX)
    return isinstance(value, dict) and value.get("schema") == SCHEMA


def _counties(db_session: Any):
    from models import Entity, EntityType

    return db_session.query(Entity).filter(Entity.type == EntityType.COUNTY)


@contextmanager
def _project_transaction(db_session: Any, dry_run: bool):
    """Read current JSON under ordered locks for the owned mutation.

    An unflushed Entity edit is ambiguous: refreshing would discard it, while
    autoflush could persist a stale whole-JSON before we acquire locks. Refuse
    it rather than silently choosing either beforeimage. Callers must finish
    their Entity work before entering this domain's transaction.
    """
    from models import Entity

    try:
        with db_session.no_autoflush:
            pending = set(db_session.new) | set(db_session.deleted) | {
                obj for obj in db_session.dirty if db_session.is_modified(obj)
            }
            if any(isinstance(obj, Entity) for obj in pending):
                raise ValueError("stalled_projects refuses pending Entity changes")
            query = _counties(db_session).order_by(Entity.id).populate_existing()
            if not dry_run:
                # Same ordering as the reference writer. populate_existing is
                # essential: FOR UPDATE alone reuses stale identity-map JSON.
                query = query.with_for_update()
            entities = query.all()
            for entity in entities:
                if entity.meta is not None and not isinstance(entity.meta, dict):
                    raise ValueError(f"Invalid county metadata for Entity {entity.id}")
            yield entities
        if not dry_run:
            db_session.commit()
    except BaseException:
        if not dry_run:
            # Roll back rather than assigning stale dictionaries back to ORM
            # objects. A fresh read after failure reflects durable authority.
            db_session.rollback()
        raise


def clear_owned_keys(db_session: Any, dry_run: bool = False, *, legacy_only: bool = False) -> dict:
    """Remove this domain's keys from every county's meta.

    ``legacy_only`` keeps a county's current (schema 2, COB-sourced) block
    and removes only what predates it — the invented fixture's list and its
    three summary keys. That is what a run that REFUSES does: the previous
    real edition stays published, the invented records never do.
    """
    entities = 0
    keys = 0
    with _project_transaction(db_session, dry_run) as counties:
        for entity in counties:
            stale = owned_keys(entity.meta)
            if legacy_only and _is_current(entity.meta):
                stale = [k for k in stale if k != OWNED_PREFIX]
            if not stale:
                continue
            entities += 1
            keys += len(stale)
            if dry_run:
                logger.info("[DRY RUN] would clear %s from %s", stale, entity.slug)
                continue
            # A new dict, not an in-place pop: JSONB columns are not
            # mutation-tracked, so mutating entity.meta would never be flushed.
            entity.meta = {k: v for k, v in entity.meta.items() if k not in stale}
    logger.info(
        "stalled_projects: cleared %d key(s) on %d county entit(y/ies)%s",
        keys,
        entities,
        " [dry run]" if dry_run else "",
    )
    return {"entities": entities, "keys": keys}


def published_edition(db_session: Any) -> Optional[Dict[str, Any]]:
    """The edition currently in the database, from any county that holds one."""
    for entity in _counties(db_session):
        if _is_current(entity.meta):
            return entity.meta[OWNED_PREFIX].get("source")
    return None


def _withheld_fields(county: Dict[str, Any]) -> List[Dict[str, str]]:
    """Money fields that must not be published for this county, and why.

    Not a judgement on COB's arithmetic — Kakamega's table total leaving out
    its own row 10 is published, mismatch and all. These are the cases where
    the TABLE cannot be read against its own header: the unit it declares is
    contradicted a thousand- or million-fold, its columns are shifted, or its
    rows do not line up with its header at all.
    """
    rec = county.get("reconciliation") or {}
    reasons: List[Dict[str, str]] = []
    if rec.get("unit_conflicts"):
        reasons += [
            {"field": f, "why": "unit_conflict", "detail": f"conflicts on {', '.join(rec['unit_conflicts'])}"}
            for f in MONEY_FIELDS
        ]
    elif rec.get("column_shift"):
        reasons += [{"field": f, "why": "column_shift", "detail": str(rec["column_shift"])} for f in MONEY_FIELDS]
    return reasons


def _scrub_rows_side(rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(rec, dict):
        return rec
    rec = dict(rec, estimated_value_kes_sum=None, amount_paid_kes_sum=None)
    checks = []
    for c in rec.get("checks", []):
        if c.get("check") != "count":
            c = dict(c, rows=None, agrees=None, withheld=True)
            if c.get("cob_source") == "table total row":
                c["cob"] = None  # read under the same contradicted header
        checks.append(c)
    rec["checks"] = checks
    return rec


def _scrub_total(total: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(total, dict):
        return total
    return {k: (None if k.endswith("_kes") else v) for k, v in total.items()}


def build_county_block(county: Dict[str, Any], edition: Dict[str, Any]) -> Dict[str, Any]:
    """The schema-2 block for one county."""
    summary = county.get("summary") or {}
    reporter = summary.get("reported_by") or REPORTED_BY
    withheld = _withheld_fields(county)
    withheld_names = {w["field"] for w in withheld}
    rows: List[Dict[str, Any]] = []
    for table in county.get("tables", []):
        for raw in table.get("rows", []):
            row = {
                "project_name": raw.get("project_name"),
                "row_no": raw.get("row_no"),
                "sector": raw.get("sector"),
                "location": raw.get("location"),
                "completion_pct": raw.get("completion_pct"),
                "reason": raw.get("reason"),
                "action": raw.get("action"),
                "group": raw.get("group"),
                "estimated_value_kes": raw.get("estimated_value_kes"),
                "amount_paid_kes": raw.get("amount_paid_kes"),
                "cells": raw.get("cells"),
                "flags": list(raw.get("flags") or []),
                # Evidence — what services/stalled_projects.py requires.
                "source_url": edition.get("url"),
                "source_page": raw.get("source_page"),
                "as_of": table.get("as_of") or edition.get("as_of"),
                # The caption names the assembly when the assembly reported
                # (Kisii Q1 FY2025/26); that outranks the county's sentence.
                "reported_by": table.get("reported_by") or reporter,
                "publisher": PUBLISHER,
                "table_caption": table.get("caption"),
                "table_no": table.get("table_no"),
            }
            for field in ("estimated_value", "amount_paid"):
                if field in withheld_names and row[f"{field}_kes"] is not None:
                    row[f"{field}_kes"] = None
                    row["flags"].append(f"{field}:withheld")
            rows.append(row)
    reconciliation = county.get("reconciliation")
    tables = county.get("tables", [])
    if withheld_names:
        # Nothing read against a contradicted header may reach a reader as
        # KES — not a row, not a total, not a reconciliation sum. Trans Nzoia
        # FY2025/26 otherwise showed "estimated_value_kes_sum: 874.0" (KSh
        # 874) for a project COB values at KSh 874 million.
        reconciliation = _scrub_rows_side(reconciliation)
        tables = [
            dict(t, total=_scrub_total(t.get("total")), rows=t.get("rows"))
            for t in tables
        ]
    return {
        "schema": SCHEMA,
        "source": {
            "publisher": PUBLISHER,
            "title": edition.get("title"),
            "fiscal_year": edition.get("fiscal_year"),
            "period": edition.get("period"),
            "published": edition.get("published"),
            "as_of": edition.get("as_of"),
            "url": edition.get("url"),
            "wpdmdl": edition.get("wpdmdl"),
            "sha256": edition.get("sha256"),
            "server_fingerprint": edition.get("server_fingerprint"),
            "reported_by": reporter,
        },
        "rows": rows,
        "summary": county.get("summary"),
        "statement": county.get("statement"),
        "table_2_6": county.get("table_2_6"),
        "tables": [
            {
                "caption": t.get("caption"),
                "caption_page": t.get("caption_page"),
                "county_as_printed": t.get("county_as_printed"),
                "total": t.get("total"),
                "layout": t.get("layout"),
                "skipped": t.get("skipped"),
                "notes": t.get("notes"),
            }
            for t in tables
        ],
        "reconciliation": reconciliation,
        "withheld_fields": withheld,
    }


def write(
    counties: List[Dict[str, Any]],
    edition: Dict[str, Any],
    db_session: Any,
    dry_run: bool = False,
) -> dict:
    """Replace every county's block with this edition's.

    Every county is cleared first, including ones the new edition says
    nothing about: a county that had a table last quarter and has none now
    must not keep last quarter's rows under this quarter's date.
    """
    # Matched on the county NAME, not the slug. Production's slugs are
    # "nairobi-county"; a freshly bootstrapped database's are "nairobi-047"
    # (bootstrap.py builds them from the county code). Keyed on slug, every
    # write to a new environment would have matched nothing, silently.
    by_name = {c["county"]: c for c in counties}
    written = 0
    rows = 0
    unmatched = set(by_name)
    with _project_transaction(db_session, dry_run) as entities:
        for entity in entities:
            name = normalise_county(entity.canonical_name or "") or normalise_county(
                (entity.slug or "").rsplit("-", 1)[0]
            )
            county = by_name.get(name) if name else None
            meta = {k: v for k, v in (entity.meta or {}).items() if not k.startswith(OWNED_PREFIX)}
            if county is not None:
                block = build_county_block(county, edition)
                meta[OWNED_PREFIX] = block
                if name in unmatched:
                    # Counted once per county. A stale duplicate entity gets the
                    # same block, but must not add rows: doubled counts covered
                    # for a county that matched no entity at all.
                    unmatched.discard(name)
                    written += 1
                    rows += len(block["rows"])
            if dry_run:
                continue
            if meta != (entity.meta or {}):
                entity.meta = meta
    if unmatched:
        logger.warning("stalled_projects: no county entity for %s", sorted(unmatched))
    logger.info(
        "stalled_projects: wrote %d county block(s), %d row(s)%s",
        written,
        rows,
        " [dry run]" if dry_run else "",
    )
    return {"counties": written, "rows": rows, "unmatched": sorted(unmatched)}

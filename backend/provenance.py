"""Derive the real vintage of served data from its SourceDocument provenance.

Endpoints historically reported ``datetime.now()`` as ``last_updated`` —
i.e. the *request* time — which manufactures false freshness for data that
may be months old (audit finding §2.9 / §3.7). These helpers resolve the
genuine vintage from the contributing ``SourceDocument`` rows:

  1. ``meta["publication_date"]`` — the source document's own publication
     date, when the seeding writer recorded it (preferred);
  2. ``fetch_date`` — when we last fetched the document (fallback).

Both are real, stable dates. ``None`` is returned when no vintage can be
resolved, so callers emit an honest null/"unknown" rather than the
request time. Schema-free on purpose (reads the existing ``metadata``
JSONB), so it works on the current ``create_all``-managed database without
a migration.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _parse_dt(value) -> Optional[_dt.datetime]:
    """Best-effort parse of an ISO datetime / date / 'YYYY' / 'YYYY-MM' string."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:  # plain "YYYY" or "YYYY-MM"
        parts = text.split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return _dt.datetime(year, month, day)
    except (ValueError, IndexError):
        return None


def doc_vintage(doc) -> Optional[_dt.datetime]:
    """Best available vintage for one SourceDocument.

    ``meta['publication_date']`` if present, else ``fetch_date``. Never the
    current request time.
    """
    if doc is None:
        return None
    meta = getattr(doc, "meta", None)
    if isinstance(meta, dict):
        pub = _parse_dt(meta.get("publication_date"))
        if pub is not None:
            return pub
    return getattr(doc, "fetch_date", None)


def _naive(value: _dt.datetime) -> _dt.datetime:
    """Drop tzinfo so aware/naive datetimes can be compared for max()."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def resolve_data_vintage(db, source_document_ids: Iterable) -> Optional[_dt.datetime]:
    """Most recent real vintage across the given source documents, or None.

    ``None`` means "no resolvable provenance" — the caller should then emit
    an explicit null/"unknown", NOT the request time.
    """
    ids = {i for i in (source_document_ids or []) if i}
    if not ids:
        return None
    try:
        from models import SourceDocument

        docs = (
            db.query(SourceDocument).filter(SourceDocument.id.in_(ids)).all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("resolve_data_vintage query failed: %s", exc)
        return None

    vintages = [v for v in (doc_vintage(d) for d in docs) if v is not None]
    if not vintages:
        return None
    return max(vintages, key=_naive)


def vintage_iso(db, source_document_ids) -> Optional[str]:
    """``resolve_data_vintage`` as an ISO string, or ``None`` (honest unknown).

    Convenience for endpoint response bodies so ``last_updated`` reports the
    real source vintage inline instead of ``datetime.now()``.
    """
    vintage = resolve_data_vintage(db, source_document_ids)
    return vintage.isoformat() if vintage else None

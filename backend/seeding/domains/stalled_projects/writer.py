"""Own, and clear, the ``Entity.meta['stalled_projects*']`` keys.

Until issue #230 this writer copied 25 invented records from
``seeding/real_data/stalled_projects.json`` into four meta keys on 21
counties every night. The fixture is gone; what remains in production is
removed here, by the nightly, rather than by hand-run SQL, so the clean-up is
reviewed, repeatable and recorded in the ingestion log like any other write.

Ownership is by prefix: every meta key starting ``stalled_projects`` belongs
to this domain (``stalled_projects``, ``_count``, ``_total_value``,
``_total_paid`` today). A key another domain writes must not share it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

OWNED_PREFIX = "stalled_projects"


def owned_keys(meta: dict | None) -> list[str]:
    return sorted(k for k in (meta or {}) if k.startswith(OWNED_PREFIX))


def clear_owned_keys(db_session: Any, dry_run: bool = False) -> dict:
    """Remove this domain's keys from every county's meta.

    Returns ``{"entities": n, "keys": m}`` — how many counties held any, and
    how many keys were (or in a dry run, would be) removed.
    """
    from models import Entity, EntityType

    entities = 0
    keys = 0
    for entity in db_session.query(Entity).filter(Entity.type == EntityType.COUNTY):
        stale = owned_keys(entity.meta)
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
    if not dry_run:
        db_session.commit()
    logger.info(
        "stalled_projects: cleared %d key(s) on %d county entit(y/ies)%s",
        keys,
        entities,
        " [dry run]" if dry_run else "",
    )
    return {"entities": entities, "keys": keys}

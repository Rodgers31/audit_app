"""Write stalled project records into Entity.meta['stalled_projects']."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def write(records: list[dict], db_session: Any, dry_run: bool = False) -> dict:
    """Merge stalled_projects list into each county Entity's meta JSONB."""
    from models import Entity, EntityType

    # Group by county slug
    by_county: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        slug = rec["county_slug"]
        by_county[slug].append(
            {
                "project_name": rec["project_name"],
                "sector": rec["sector"],
                "contracted_amount": rec["contracted_amount"],
                "amount_paid": rec.get("amount_paid", 0),
                "completion_pct": rec.get("completion_pct", 0),
                "start_year": rec.get("start_year"),
                "expected_completion": rec.get("expected_completion"),
                "status": rec["status"],
                "reason": rec.get("reason", ""),
                "oag_reference": rec.get("oag_reference", ""),
            }
        )

    updated = 0
    skipped = 0
    for slug, projects in by_county.items():
        entity = (
            db_session.query(Entity)
            .filter(Entity.type == EntityType.COUNTY, Entity.slug == slug)
            .first()
        )
        if not entity:
            logger.warning("County entity not found for slug=%s", slug)
            skipped += len(projects)
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would add %d stalled projects to %s", len(projects), slug
            )
            updated += len(projects)
            continue

        meta = dict(entity.meta or {})
        meta["stalled_projects"] = projects
        meta["stalled_projects_count"] = len(projects)
        meta["stalled_projects_total_value"] = sum(
            p["contracted_amount"] for p in projects
        )
        meta["stalled_projects_total_paid"] = sum(p["amount_paid"] for p in projects)
        entity.meta = meta
        db_session.merge(entity)
        updated += len(projects)
        logger.info("Added %d stalled projects to %s", len(projects), slug)

    if not dry_run:
        db_session.commit()

    logger.info("Stalled projects seeder: updated=%d, skipped=%d", updated, skipped)
    return {"updated": updated, "skipped": skipped}

"""Stalled projects seeder domain.

Publishes nothing until a live, citable source is wired (issue #230), and
removes the invented records earlier runs wrote into ``Entity.meta``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, writer

logger = logging.getLogger("seeding.stalled_projects")


@register_domain("stalled_projects")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    records = fetcher.fetch(settings)
    cleared = writer.clear_owned_keys(session, dry_run=context.dry_run)
    return DomainRunResult(
        domain="stalled_projects",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=len(records),
        items_created=0,
        items_updated=0,
        dry_run=context.dry_run,
        errors=["refused: no evidence-backed source for stalled projects (#230)"],
        metadata={"cleared_entities": cleared["entities"], "cleared_keys": cleared["keys"]},
    )

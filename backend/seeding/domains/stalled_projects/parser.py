"""Parse stalled project records — already clean, just validate."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {"county_slug", "project_name", "sector", "contracted_amount", "status"}


def parse(raw: list[dict], settings: Any | None = None) -> list[dict]:
    """Validate and return records grouped by county_slug."""
    valid = []
    for rec in raw:
        if not REQUIRED_KEYS.issubset(rec.keys()):
            logger.warning(
                "Skipping record missing required keys: %s",
                rec.get("project_name", "?"),
            )
            continue
        valid.append(rec)
    logger.info("Parsed %d valid stalled project records", len(valid))
    return valid

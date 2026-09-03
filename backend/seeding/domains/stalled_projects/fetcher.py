"""Fetch stalled projects data.

Stalled project data comes from OAG audit reports and county performance
audits. Since there is no public API for this data, we use the fixture
as the primary source and attempt to supplement with OAG PDF data when
live_pdf_fetch_enabled is True.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

logger = logging.getLogger(__name__)
_HERE = pathlib.Path(__file__).resolve().parent
_DEFAULT_PATH = _HERE.parents[1] / "real_data" / "stalled_projects.json"


def fetch(settings: Any | None = None) -> list[dict]:
    """Return raw project records from the fixture file."""
    path = _DEFAULT_PATH
    if settings:
        url = getattr(settings, "stalled_projects_url", None) or ""
        if url.startswith("file://"):
            path = pathlib.Path(url.removeprefix("file://"))
        elif url:
            path = pathlib.Path(url)
    # Provenance. Stalled-project records come from OAG audit reports and
    # county performance audits; there is no API and no extractor for them
    # yet, so this domain is fixture-backed by design. Recording that is what
    # separates "working as designed" from the silent fixture fallback that
    # kept three domains frozen for months — and if the fixture ever goes
    # missing, the reason slug says so instead of an empty list looking like
    # a quiet no-op.
    from ...freshness import mark_fixture

    if not path.exists():
        logger.warning("Stalled projects fixture not found at %s", path)
        mark_fixture(
            "stalled_projects",
            reason="fixture_missing",
            detail=f"no file at {path}; this run ingested NOTHING",
        )
        return []
    data = json.loads(path.read_text())
    projects = data.get("projects", data) if isinstance(data, dict) else data
    logger.info("Fetched %d stalled project records", len(projects))
    mark_fixture(
        "stalled_projects",
        reason="no_live_source",
        detail=(
            f"{len(projects)} record(s) from the in-repo fixture; source is "
            f"OAG audit reports, for which no extractor exists yet"
        ),
    )
    return projects

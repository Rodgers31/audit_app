"""Fetch stalled-project records.

There is no live source wired yet (issue #230). The records this used to
replay from ``seeding/real_data/stalled_projects.json`` were invented, so it
refuses rather than serve anything.
"""

from __future__ import annotations

from typing import Any

from ...freshness import mark_refused


def fetch(settings: Any | None = None) -> list[dict]:
    mark_refused(
        "stalled_projects",
        reason="no_evidence_backed_source",
        detail=(
            "no live source wired; the former fixture was invented (#230) and "
            "has been deleted — publishing nothing"
        ),
    )
    return []

"""Fetcher for learning hub question data."""

from __future__ import annotations

import logging
from typing import Any

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.learning_hub.fetcher")


def fetch_questions_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """
    Fetch educational questions from curated source or fixture.

    Args:
        client: HTTP client instance
        settings: Seeding configuration

    Returns:
        Parsed JSON payload with question records
    """
    payload = load_json_resource(
        url=settings.learning_hub_dataset_url,
        client=client,
        logger=logger,
        label="learning_hub",
    )

    # Provenance: this domain has NO publisher. The questions are curated
    # civic-education content held in-repo, so "fixture" is the permanent and
    # correct answer, not a degradation — and saying so explicitly is what
    # stops the nightly reporting "provenance unknown" for a domain that is
    # working exactly as designed. `no_live_source` is the reason slug the
    # staleness gate branches on.
    from ...freshness import mark_fixture

    count = len(payload.get("questions", payload)) if isinstance(payload, dict) else len(payload)
    mark_fixture(
        "learning_hub",
        reason="no_live_source",
        detail=(
            f"curated in-repo civic-education content ({count} item(s)); "
            f"there is no publisher to reach for this domain"
        ),
    )
    return payload

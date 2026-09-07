"""One way to ask "what is Kenya's population?".

`GET /budget/enhanced` reported `total_population: 907,025,674` — roughly
sixteen times the real figure — because it did:

    db.query(func.sum(PopulationData.total_population)).scalar()

`population_data` holds one row per county PER YEAR plus national rows, so that
sums 47 counties across every year they were seeded and adds the national totals
on top. Everything derived from it inherited the error: `per_capita_budget_kes`
came out at KES 6,048 against a true figure near KES 98,000.

The same shape sat in the county fallback on /economic/population/latest: it
summed county rows across all years while separately taking max(year), so the
year it reported and the population it reported came from different populations
of rows.

Scoping that sum to one year fixed the arithmetic but not the premise, and the
fallback has since been removed outright. Measured against production on
2026-09-07 (issue #190), it had no year in which it returned Kenya's
population:

  * ``entity_id IS NOT NULL`` is not "county". ``population_data`` holds two
    rows attributed to the National Government ENTITY (id 73) as well as the 47
    county rows, so at 2019 — the only year with a full county set — the sum was
    47,564,296 (the 47 counties) + 47,564,296 (id=64, the same national figure
    again) = 95,128,592. Exactly twice Kenya's population, from a year that
    covers every county.

  * ``MAX(year)`` was 2026, which is population_data id=69: National Government,
    total_population 82, no source document. The sum at that year was 82.
    Callers dividing by it would have produced per-capita figures roughly
    580,000,000x too large.

A "does this year cover a plausible number of counties?" guard was considered
and rejected: it waves the first case through, because 2019 does cover all 47.
Repairing the filter as well would give a fallback that is arithmetically
sound and still a second, unsourced derivation of a figure the primary series
already publishes with provenance — so absence is returned instead. Callers
must say why the figure is missing rather than substitute one; see
``routers/economic.py`` and ``main.py``'s ``/budget/enhanced``.

Credibility audit F29; issue #190.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from models import PopulationData

logger = logging.getLogger(__name__)


def latest_national_population(db) -> Tuple[Optional[int], Optional[int]]:
    """Kenya's population and the year it describes, or ``(None, None)``.

    The only source is the newest national row (``entity_id IS NULL``) — the
    series KNBS and the World Bank publish, which is what
    ``/api/v1/economic/population/latest`` serves.

    There is deliberately no fallback. Never returns 0 for "unknown", and now
    never returns a county sum either: a caller dividing by this must be able
    to tell absence from a measurement, and the sum was neither.
    """
    national = (
        db.query(PopulationData)
        .filter(PopulationData.entity_id.is_(None))
        .order_by(PopulationData.year.desc())
        .first()
    )
    if national and national.total_population:
        return int(national.total_population), national.year

    logger.warning(
        "No national population row (entity_id IS NULL) in population_data; "
        "reporting absence. Reseed with: python -m seeding.cli seed --domain population"
    )
    return None, None

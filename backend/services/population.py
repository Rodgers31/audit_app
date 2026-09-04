"""One way to ask "what is Kenya's population?".

`GET /budget/enhanced` reported `total_population: 907,025,674` — roughly
sixteen times the real figure — because it did:

    db.query(func.sum(PopulationData.total_population)).scalar()

`population_data` holds one row per county PER YEAR plus national rows, so that
sums 47 counties across every year they were seeded and adds the national totals
on top. Everything derived from it inherited the error: `per_capita_budget_kes`
came out at KES 6,048 against a true figure near KES 98,000.

The same shape sits in the county fallback on /economic/population/latest: it
sums county rows across all years while separately taking max(year), so the
year it reports and the population it reports come from different populations
of rows.

Both now go through this. Credibility audit F29.
"""

from __future__ import annotations

from typing import Optional, Tuple

from models import PopulationData
from sqlalchemy import func


def latest_national_population(db) -> Tuple[Optional[int], Optional[int]]:
    """Kenya's population and the year it describes, or ``(None, None)``.

    Preference:
      1. The newest national row (``entity_id IS NULL``) — what KNBS publishes.
      2. The sum of county rows FOR A SINGLE YEAR, newest year first. Summing
         across years is what produced the 907-million figure.

    Never returns 0 for "unknown": a caller dividing by this must be able to
    tell absence from a real zero.
    """
    national = (
        db.query(PopulationData)
        .filter(PopulationData.entity_id.is_(None))
        .order_by(PopulationData.year.desc())
        .first()
    )
    if national and national.total_population:
        return int(national.total_population), national.year

    latest_county_year = (
        db.query(func.max(PopulationData.year))
        .filter(PopulationData.entity_id.isnot(None))
        .scalar()
    )
    if latest_county_year is None:
        return None, None

    total = (
        db.query(func.sum(PopulationData.total_population))
        .filter(
            PopulationData.entity_id.isnot(None),
            PopulationData.year == latest_county_year,
        )
        .scalar()
    )
    if not total:
        return None, None
    return int(total), latest_county_year

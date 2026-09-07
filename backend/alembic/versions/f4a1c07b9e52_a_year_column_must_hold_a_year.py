"""a year column must hold a year

Revision ID: f4a1c07b9e52
Revises: ce6ed007f696
Create Date: 2026-09-07

Measured against production on 2026-09-07, which is stamped ``ce6ed007f696``.

``population_data`` holds 77 rows. Twelve were written from source_document
524, the KNBS "2024 Statistical Abstract - Samburu County", all attributed to
Samburu:

    id=5   year=2024  total_population=20,317,126
    id=6   year=130   total_population=129,696
    id=7   year=252   total_population=127,668
    id=8   year=621   total_population=137,852
    id=9   year=399   total_population=69,938
    id=10  year=220   total_population=67,912
    id=11  year=232   total_population=64,070
    id=12  year=335   total_population=31,068
    id=13  year=897   total_population=33,002
    id=14  year=531   total_population=55,446
    id=15  year=396   total_population=28,690
    id=16  year=135   total_population=26,754

Samburu's population is 310,327 (2019 census, source_document 2435, page
"p. 17"), which this table also holds, correctly, as id=42. The misparse
outranks it.

These were not withheld. Every county read path in ``main.py`` takes
``order_by(year.desc()).first()`` (:3299, :3600, :6011, :6295), so id=5's year
of 2024 beat the census row, and production served:

    www.auditgava.com/counties/25  ->  "20.32M residents"  (read in the browser)
    /api/v1/counties/25            ->  population 20317126
    /api/v1/counties/25/comprehensive
                                   ->  demographics.population 20317126,
                                       per_capita_budget 399.14
                                       (KES 26,131.72 on the census figure),
                                       data_sources.population labelled
                                       "KNBS Census 2019" - the very document
                                       that says 310,327
    /api/v1/economic/counties/28/profile
                                   ->  population_growth_rate 1289.4

The eleven non-year years reach no page: every read path takes the newest row
per entity, and nothing in the frontend fetches the series. They are served
raw by the public API, ``/api/v1/economic/population?entity_id=28``, which
returns all thirteen rows verbatim with "year": 897 among them.

Nothing filtered any of it. Population rows are never gated on ``publishable``
- all 77 rows carry ``publishable = False`` and the figures above were live
anyway - and ``routers/economic.py:316``'s ``min_confidence >= 0.7`` passes
them, because the broken parse wrote confidence 1.00.

WHAT THIS REMOVES, AND BY WHAT RULE
-----------------------------------
The rules are the invariants the parser now enforces, not the document id, so
this says what is wrong with the rows rather than where they came from:

1. ``year`` outside 1900-2100 is not a calendar year.
2. A county whose population exceeds MAX_COUNTY_POPULATION (6,000,000) is not
   reporting a county population. Kenya's largest county is Nairobi at
   4,397,073; the next figure above it in this table is id=5's 20,317,126.

Counted on production before writing this: rule 1 matches 11 rows and rule 2
matches 1, all twelve from doc 524, and the largest county row that survives is
Nairobi's 4,397,073. Samburu keeps id=42 and therefore keeps a figure - this
corrects a number, it does not blank one.

The CHECK constraint makes rule 1 structural. ``population_data`` has four
writers (bootstrap.py, seeding/domains/population/writer.py,
services/auto_seeder.py, seeding/domains/population/census_counties.py) plus
etl/database_loader.py, and a guard in one parser does not bind the others.
``year`` is NOT NULL, so the constraint is unconditional. It is deliberately
fail-closed: a writer that tries to store 130 as a year now raises instead of
publishing a figure no reader can place in time.

Replaying this on a fresh database finds nothing to delete, and the parser no
longer writes what it removes.

NOT FIXED HERE, and tracked separately: id=69 is National Government, year
2026, total_population 82. It passes both rules (its year is a year; it is not
a county) and survives. It is currently shadowed - ``latest_national_population``
prefers the ``entity_id IS NULL`` series - but it poisons that function's
fallback branch and ``main.py:10609``'s global ``MAX(year)``.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f4a1c07b9e52"
down_revision = "ce6ed007f696"
branch_labels = None
depends_on = None


#: Kept in step with etl/knbs_parser.MAX_COUNTY_POPULATION.
MAX_COUNTY_POPULATION = 6_000_000
MIN_DATA_YEAR = 1900
MAX_DATA_YEAR = 2100


def upgrade() -> None:
    bind = op.get_bind()

    not_a_year = sa.text(
        "DELETE FROM population_data WHERE year < :lo OR year > :hi"
    ).bindparams(lo=MIN_DATA_YEAR, hi=MAX_DATA_YEAR)
    removed_years = bind.execute(not_a_year).rowcount

    not_a_county_population = sa.text(
        """
        DELETE FROM population_data
        WHERE id IN (
            SELECT p.id FROM population_data p
            JOIN entities e ON e.id = p.entity_id
            WHERE e.type = 'COUNTY' AND p.total_population > :ceiling
        )
        """
    ).bindparams(ceiling=MAX_COUNTY_POPULATION)
    removed_totals = bind.execute(not_a_county_population).rowcount

    print(
        f"population_data: removed {removed_years} row(s) whose year was not a "
        f"calendar year and {removed_totals} county row(s) above "
        f"{MAX_COUNTY_POPULATION:,}"
    )

    op.create_check_constraint(
        "ck_population_data_year_is_a_calendar_year",
        "population_data",
        f"year BETWEEN {MIN_DATA_YEAR} AND {MAX_DATA_YEAR}",
    )


def downgrade() -> None:
    # The constraint comes off; the rows do not come back. They were a
    # misparse of a table this project can no longer read that way, and
    # restoring them would restore a published figure that was wrong by 65x.
    op.drop_constraint(
        "ck_population_data_year_is_a_calendar_year",
        "population_data",
        type_="check",
    )

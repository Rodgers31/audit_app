"""a national population of 82

Revision ID: a2f7c1b48d90
Revises: f4a1c07b9e52
Create Date: 2026-09-07

Measured against production on 2026-09-07, which is stamped ``f4a1c07b9e52``.

``population_data`` holds 66 rows after that migration: 47 county rows at 2019,
two attributed to the National Government ENTITY (id 73), and 17 with
``entity_id IS NULL`` carrying the World Bank series 2010-2025.

    id | entity_id | entity              | type     | year | total_population | doc
    64 | 73        | National Government | NATIONAL | 2019 |       47,564,296 | 1823
    69 | 73        | National Government | NATIONAL | 2026 |               82 | NULL

82 is not a population. ``f4a1c07b9e52`` left it deliberately — its year IS a
calendar year and it is not a county, so neither of that migration's two rules
touches it — and recorded it as tracked separately. This is that.

WHAT IT IS, AND WHAT CANNOT BE ESTABLISHED
-------------------------------------------
The row was written 2026-03-01 06:00:16 with ``confidence`` 1.00, no
``source_document_id``, no ``extraction_id``, no ``page_ref``, no ``basis`` and
``metadata`` ``{}``.

That fingerprint identifies its writer. ``population_data`` has five writers,
and only two attach a row to the National Government ENTITY rather than to
``entity_id IS NULL``: ``bootstrap.py``'s ``_upsert_population``, which
hardcodes year 2019 and stamps a source document with confidence 0.95 (that is
id=64), and ``services/auto_seeder.py:606``, which writes
``year=census_year``, ``confidence=1.0``, no source document and no metadata,
where ``census_year = population_data.get("census_year") or
datetime.now().year``. id=69's year equals the year it was created. The
auto-seeder defaults ON in production (``main.py:1571``,
``_default_seeder = "true" if ENVIRONMENT == "production"``).

WHAT 82 MEASURED IS NOT RECOVERABLE, and that is the finding rather than a gap
in it. The row cites no document, so there is nothing to check it against.
Its likeliest upstream is ``services/live_data_fetcher.py``'s
``_scrape_knbs_population``, the only source in that path that stamps the
current year unconditionally; it regex-matches a bare number next to the word
"population" on the KNBS homepage with no plausibility check. Run against
candidate strings, that expression yields 82 from "population: 82%", from
"urban population 82.5 per cent", from "population 82 of 100", and yields
82,491 from a correctly-formatted "population 82,491,000". Which of those the
homepage held on 2026-03-01 is gone. A figure that cannot be sourced should not
be published, so it is removed rather than corrected. Filed separately: the
homepage scrape as a data source at all.

WHAT THIS REMOVES, AND BY WHAT RULE
-----------------------------------
As in ``f4a1c07b9e52``, the rule is the invariant, not the row id:

    A population row that is national in scope — ``entity_id IS NULL``, or
    attached to an entity of type NATIONAL — below MIN_NATIONAL_POPULATION
    (5,000,000) is not a national population.

Kenya's first post-war census, 1948, counted 5.4 million. Nothing this table is
for can sit below that floor. County rows are untouched by construction: the
floor applies only to national-scope rows, and 47 of the 47 county rows on
production are below it — Lamu's 143,920 is the smallest.

Counted on production before writing this: the rule matches exactly one row,
id=69. The 17 ``entity_id IS NULL`` rows range 41,598,567 to 57,532,493 and all
survive. National Government keeps id=64, its 2019 census figure of 47,564,296
with source_document 1823 — so this corrects a number, it does not blank one,
and no page loses a figure.

WHAT IS AND IS NOT MADE STRUCTURAL
----------------------------------
The CHECK constraint covers the ``entity_id IS NULL`` half of the rule and
nothing else: a CHECK cannot join to ``entities`` to read ``type``, so the
NATIONAL-entity half cannot be expressed here. That half is enforced at the
writer that produced this row (``services/auto_seeder.py``), which is the only
one of the five that can reach it. The asymmetry is deliberate and worth
stating rather than papering over: a guard in one writer does not bind the
others, which is exactly why ``f4a1c07b9e52`` reached for a constraint.

Replaying this on a fresh database finds nothing to delete.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a2f7c1b48d90"
down_revision = "f4a1c07b9e52"
branch_labels = None
depends_on = None


#: Kept in step with services/auto_seeder.MIN_NATIONAL_POPULATION.
#: Kenya's 1948 census counted 5.4 million; the country has never been smaller
#: in any period this table covers.
MIN_NATIONAL_POPULATION = 5_000_000


def upgrade() -> None:
    bind = op.get_bind()

    not_a_national_population = sa.text(
        """
        DELETE FROM population_data
        WHERE id IN (
            SELECT p.id
            FROM population_data p
            LEFT JOIN entities e ON e.id = p.entity_id
            WHERE (p.entity_id IS NULL OR e.type = 'NATIONAL')
              AND p.total_population < :floor
        )
        """
    ).bindparams(floor=MIN_NATIONAL_POPULATION)
    removed = bind.execute(not_a_national_population).rowcount

    print(
        f"population_data: removed {removed} national-scope row(s) below "
        f"{MIN_NATIONAL_POPULATION:,}"
    )

    # Binds every writer of the entity_id IS NULL series — the one
    # `latest_national_population` reads. The NATIONAL-entity half of the rule
    # needs `entities.type` and so cannot be a CHECK; see the docstring.
    op.create_check_constraint(
        "ck_population_data_national_series_is_plausible",
        "population_data",
        f"entity_id IS NOT NULL OR total_population >= {MIN_NATIONAL_POPULATION}",
    )


def downgrade() -> None:
    # The constraint comes off; the row does not come back. It cited no
    # document, and nothing recorded what it counted.
    op.drop_constraint(
        "ck_population_data_national_series_is_plausible",
        "population_data",
        type_="check",
    )

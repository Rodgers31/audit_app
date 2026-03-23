"""Add indexes for economic data tables.

Covers population_data, gdp_data, economic_indicators, and poverty_indices
which were missing from the original performance indexes migration.
"""

from alembic import op

revision = "add_economic_indexes"
down_revision = "add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # Population data - queried by entity_id + year
    op.create_index(
        "ix_population_entity_year",
        "population_data",
        ["entity_id", "year"],
        unique=False,
        if_not_exists=True,
    )

    # GDP data - queried by entity_id + year
    op.create_index(
        "ix_gdp_entity_year",
        "gdp_data",
        ["entity_id", "year"],
        unique=False,
        if_not_exists=True,
    )

    # Economic indicators - queried by type + entity_id + date
    op.create_index(
        "ix_economic_indicators_type_entity",
        "economic_indicators",
        ["indicator_type", "entity_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_economic_indicators_date",
        "economic_indicators",
        ["indicator_date"],
        unique=False,
        if_not_exists=True,
    )

    # Poverty indices - queried by entity_id + year
    op.create_index(
        "ix_poverty_entity_year",
        "poverty_indices",
        ["entity_id", "year"],
        unique=False,
        if_not_exists=True,
    )

    # Audits - composite index for recurring findings detection
    op.create_index(
        "ix_audits_entity_querytype_year",
        "audits",
        ["entity_id", "query_type", "audit_year"],
        unique=False,
        if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_population_entity_year", table_name="population_data")
    op.drop_index("ix_gdp_entity_year", table_name="gdp_data")
    op.drop_index("ix_economic_indicators_type_entity", table_name="economic_indicators")
    op.drop_index("ix_economic_indicators_date", table_name="economic_indicators")
    op.drop_index("ix_poverty_entity_year", table_name="poverty_indices")
    op.drop_index("ix_audits_entity_querytype_year", table_name="audits")

"""add unique constraints to prevent duplicate seeding

Revision ID: a1b2c3d4e5f6
Revises: 54e9dab10c5f
Create Date: 2025-06-21

Adds database-level unique constraints to tables that previously relied
solely on application-level dedup in seed writers.  This is a safety net:
if a seeder is re-run or two runs overlap, PostgreSQL will reject the
duplicate row rather than silently doubling the data.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "54e9dab10c5f"
branch_labels = None
depends_on = None


def upgrade():
    # -- loans: one row per lender per issue date per entity
    op.create_unique_constraint(
        "uq_loans_entity_lender_date",
        "loans",
        ["entity_id", "lender", "issue_date"],
    )

    # -- fiscal_periods: one label per country
    op.create_unique_constraint(
        "uq_fiscal_period_country_label",
        "fiscal_periods",
        ["country_id", "label"],
    )

    # -- budget_lines: one row per entity+period+category+subcategory
    op.create_unique_constraint(
        "uq_budget_entity_period_cat_subcat",
        "budget_lines",
        ["entity_id", "period_id", "category", "subcategory"],
    )

    # -- population_data: one row per entity per year
    op.create_unique_constraint(
        "uq_population_entity_year",
        "population_data",
        ["entity_id", "year"],
    )

    # -- gdp_data: one row per entity per year per quarter
    op.create_unique_constraint(
        "uq_gdp_entity_year_quarter",
        "gdp_data",
        ["entity_id", "year", "quarter"],
    )

    # -- economic_indicators: one value per indicator type + date + entity
    op.create_unique_constraint(
        "uq_econ_type_date_entity",
        "economic_indicators",
        ["indicator_type", "indicator_date", "entity_id"],
    )

    # -- poverty_indices: one row per entity per year
    op.create_unique_constraint(
        "uq_poverty_entity_year",
        "poverty_indices",
        ["entity_id", "year"],
    )


def downgrade():
    op.drop_constraint("uq_poverty_entity_year", "poverty_indices", type_="unique")
    op.drop_constraint(
        "uq_econ_type_date_entity", "economic_indicators", type_="unique"
    )
    op.drop_constraint("uq_gdp_entity_year_quarter", "gdp_data", type_="unique")
    op.drop_constraint("uq_population_entity_year", "population_data", type_="unique")
    op.drop_constraint(
        "uq_budget_entity_period_cat_subcat", "budget_lines", type_="unique"
    )
    op.drop_constraint(
        "uq_fiscal_period_country_label", "fiscal_periods", type_="unique"
    )
    op.drop_constraint("uq_loans_entity_lender_date", "loans", type_="unique")

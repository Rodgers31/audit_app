"""add_imf_weo_observations

Creates the ``imf_weo_observations`` table that stores IMF World Economic
Outlook values for Kenya (and later other countries) with full vintage
history. Powers the ``/api/v1/debt/broader`` endpoint.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "imf_weo_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("indicator", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "is_projection", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("vintage", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="imf_datamapper",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "country_code",
            "indicator",
            "year",
            "vintage",
            name="uq_imf_weo_country_indicator_year_vintage",
        ),
    )
    # Hot lookup path: latest vintage for (country, indicator, year)
    op.create_index(
        "ix_imf_weo_country_indicator_year",
        "imf_weo_observations",
        ["country_code", "indicator", "year"],
    )


def downgrade():
    op.drop_index(
        "ix_imf_weo_country_indicator_year", table_name="imf_weo_observations"
    )
    op.drop_table("imf_weo_observations")

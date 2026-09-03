"""widen_imf_country_code

Widens ``imf_weo_observations.country_code`` from VARCHAR(3) to VARCHAR(16).

IMF's DataMapper REST API ignores the country filter in the URL and
returns the ENTIRE dataset — all ISO3 countries plus regional aggregate
codes like WEOWORLD (8 chars), ADVEC (5), EURO (4), EU (2). The parser
now filters those out, but the column was VARCHAR(3) and the seeder
crashed with ``StringDataRightTruncation`` on the first non-3-char code
before the filter fix landed.

Widening the column to VARCHAR(16) is defense-in-depth: if a parser
regression ever reintroduces aggregates, we get garbage rows rather
than a crashed seeding job.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-22
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "imf_weo_observations",
        "country_code",
        existing_type=sa.String(length=3),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade():
    # Only safe if all existing rows fit in VARCHAR(3); after the parser
    # filter fix they do (only "KEN"), but a future operator who has
    # somehow stored longer codes would need to clean up first.
    op.alter_column(
        "imf_weo_observations",
        "country_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=3),
        existing_nullable=False,
    )

"""add audit finding columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-19

Adds structured columns to the audits table:
  - query_type, amount, status, audit_opinion, audit_year,
    external_reference, management_response, follow_up_status
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audits", sa.Column("query_type", sa.String(100), nullable=True))
    op.add_column("audits", sa.Column("amount", sa.Numeric(15, 2), nullable=True))
    op.add_column("audits", sa.Column("status", sa.String(50), nullable=True))
    op.add_column("audits", sa.Column("audit_opinion", sa.String(50), nullable=True))
    op.add_column("audits", sa.Column("audit_year", sa.Integer(), nullable=True))
    op.add_column(
        "audits", sa.Column("external_reference", sa.String(200), nullable=True)
    )
    op.add_column(
        "audits", sa.Column("management_response", sa.Text(), nullable=True)
    )
    op.add_column(
        "audits", sa.Column("follow_up_status", sa.String(100), nullable=True)
    )


def downgrade():
    op.drop_column("audits", "follow_up_status")
    op.drop_column("audits", "management_response")
    op.drop_column("audits", "external_reference")
    op.drop_column("audits", "audit_year")
    op.drop_column("audits", "audit_opinion")
    op.drop_column("audits", "status")
    op.drop_column("audits", "amount")
    op.drop_column("audits", "query_type")

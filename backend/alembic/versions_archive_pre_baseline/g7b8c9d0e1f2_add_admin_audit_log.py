"""add_admin_audit_log

Creates the ``admin_audit_log`` table that backs the admin write-action
log. Every privileged mutation (role change, user delete, ETL trigger,
…) writes a row here so there's a "who did what, when" trail surfaced
in the new /admin/audit-log UI.

Append-only by convention — the only writer is
``backend.utils.audit.record_admin_action`` and there are no UPDATE
or DELETE paths in the API. Indexes match the filters the UI exposes
(actor_id, action, target_type, target_id, created_at).

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index(
        "ix_admin_audit_log_target_type", "admin_audit_log", ["target_type"]
    )
    op.create_index("ix_admin_audit_log_target_id", "admin_audit_log", ["target_id"])
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])


def downgrade():
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_target_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_target_type", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

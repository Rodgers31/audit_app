"""add user features tables (watchlist, alerts, newsletter)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-27

Adds:
  - New columns on users: display_name, email_verified, updated_at
  - watchlist_items table
  - data_alerts table
  - newsletter_subscribers table
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    # -- User table additions --
    op.add_column("users", sa.Column("display_name", sa.String(120), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "email_verified", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column("users", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # -- watchlist_items --
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("item_id", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("notify", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_watchlist_items_id", "watchlist_items", ["id"])
    op.create_index("ix_watchlist_user", "watchlist_items", ["user_id"])
    op.create_unique_constraint(
        "uq_watchlist_user_type_item",
        "watchlist_items",
        ["user_id", "item_type", "item_id"],
    )

    # -- data_alerts --
    op.create_table(
        "data_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("item_type", sa.String(30), nullable=True),
        sa.Column("item_id", sa.String(100), nullable=True),
        sa.Column("read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_data_alerts_id", "data_alerts", ["id"])
    op.create_index("ix_data_alerts_user", "data_alerts", ["user_id"])
    op.create_index("ix_data_alerts_unread", "data_alerts", ["user_id", "read"])

    # -- newsletter_subscribers --
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("confirmed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("subscribed_at", sa.DateTime(), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
    )
    op.create_index("ix_newsletter_subscribers_id", "newsletter_subscribers", ["id"])
    op.create_index(
        "ix_newsletter_email", "newsletter_subscribers", ["email"], unique=True
    )


def downgrade():
    op.drop_table("newsletter_subscribers")
    op.drop_table("data_alerts")
    op.drop_table("watchlist_items")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "display_name")

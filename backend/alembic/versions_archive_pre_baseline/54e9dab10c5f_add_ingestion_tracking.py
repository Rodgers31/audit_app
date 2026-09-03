"""add_ingestion_tracking

Revision ID: 54e9dab10c5f
Revises: add_validation_fields
Create Date: 2025-11-01 16:58:22.170566

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "54e9dab10c5f"
down_revision = "add_validation_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Check and create IngestionStatus enum only if it doesn't exist
    connection = op.get_bind()
    enum_check = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'ingestionstatus'")
    ).fetchone()

    if not enum_check:
        connection.execute(
            sa.text(
                "CREATE TYPE ingestionstatus AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')"
            )
        )

    # Check and create DocumentStatus enum only if it doesn't exist
    doc_status_check = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'documentstatus'")
    ).fetchone()

    if not doc_status_check:
        connection.execute(
            sa.text(
                "CREATE TYPE documentstatus AS ENUM ('AVAILABLE', 'ARCHIVED', 'FAILED')"
            )
        )

    # Create ingestion_jobs table
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "COMPLETED_WITH_ERRORS",
                "FAILED",
                name="ingestionstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("items_processed", sa.Integer(), nullable=False),
        sa.Column("items_created", sa.Integer(), nullable=False),
        sa.Column("items_updated", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_jobs_domain"), "ingestion_jobs", ["domain"], unique=False
    )
    op.create_index(
        op.f("ix_ingestion_jobs_id"), "ingestion_jobs", ["id"], unique=False
    )

    # Add status column to source_documents if it doesn't exist
    status_col_check = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='source_documents' AND column_name='status'"
        )
    ).fetchone()

    if not status_col_check:
        op.add_column(
            "source_documents",
            sa.Column(
                "status",
                postgresql.ENUM(
                    "AVAILABLE",
                    "ARCHIVED",
                    "FAILED",
                    name="documentstatus",
                    create_type=False,
                ),
                nullable=False,
                server_default="AVAILABLE",
            ),
        )

    # Add last_seen_at column to source_documents if it doesn't exist
    last_seen_check = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='source_documents' AND column_name='last_seen_at'"
        )
    ).fetchone()

    if not last_seen_check:
        op.add_column(
            "source_documents",
            sa.Column(
                "last_seen_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    # Add source_hash column to budget_lines if it doesn't exist
    hash_col_check = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='budget_lines' AND column_name='source_hash'"
        )
    ).fetchone()

    if not hash_col_check:
        op.add_column(
            "budget_lines",
            sa.Column("source_hash", sa.String(length=64), nullable=True),
        )


def downgrade():
    # Remove columns
    op.drop_column("budget_lines", "source_hash")
    op.drop_column("source_documents", "last_seen_at")
    op.drop_column("source_documents", "status")

    # Drop ingestion_jobs table
    op.drop_index(op.f("ix_ingestion_jobs_id"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_domain"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    # Drop enums
    sa.Enum(name="ingestionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="documentstatus").drop(op.get_bind(), checkfirst=True)

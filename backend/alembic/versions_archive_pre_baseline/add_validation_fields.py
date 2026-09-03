"""Add validation fields for data quality tracking

Revision ID: add_validation_fields
Revises: add_performance_indexes
Create Date: 2024-01-15 10:00:00.000000

This migration adds validation-related fields to budget_lines and audits tables
to support Week 1 Task 2: Data Quality improvements.

Fields added:
- confidence_score: DECIMAL(3,2) - Stores validation confidence (0.00 to 1.00)
- validation_warnings: JSONB - Stores array of warning messages from validators

Also creates validation_failures table to track rejected records for review.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "add_validation_fields"
down_revision = "add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add validation fields to existing tables and create validation_failures table."""

    # Add validation fields to budget_lines table
    op.add_column(
        "budget_lines",
        sa.Column(
            "confidence_score",
            sa.DECIMAL(precision=3, scale=2),
            nullable=True,
            comment="Validation confidence score (0.00 to 1.00)",
        ),
    )
    op.add_column(
        "budget_lines",
        sa.Column(
            "validation_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Array of validation warning messages",
        ),
    )

    # Add validation fields to audits table
    op.add_column(
        "audits",
        sa.Column(
            "confidence_score",
            sa.DECIMAL(precision=3, scale=2),
            nullable=True,
            comment="Validation confidence score (0.00 to 1.00)",
        ),
    )
    op.add_column(
        "audits",
        sa.Column(
            "validation_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Array of validation warning messages",
        ),
    )

    # Create validation_failures table for tracking rejected records
    op.create_table(
        "validation_failures",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            nullable=True,
            comment="Reference to source document",
        ),
        sa.Column(
            "data_type",
            sa.String(50),
            nullable=False,
            comment="Type of data: budget, audit, etc.",
        ),
        sa.Column(
            "confidence_score",
            sa.DECIMAL(precision=3, scale=2),
            nullable=False,
            comment="Validation confidence that caused rejection",
        ),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Array of validation error messages",
        ),
        sa.Column(
            "validation_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Array of validation warning messages",
        ),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Original data that failed validation",
        ),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Timestamp when record was rejected",
        ),
        sa.Column(
            "reviewed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this failure has been manually reviewed",
        ),
        sa.Column(
            "reviewed_by",
            sa.String(255),
            nullable=True,
            comment="User who reviewed this failure",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the review occurred",
        ),
        sa.Column(
            "resolution",
            sa.Text(),
            nullable=True,
            comment="Notes on how this failure was resolved",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Additional metadata about the validation failure",
        ),
    )

    # Create indexes for performance
    op.create_index(
        "ix_validation_failures_document_id", "validation_failures", ["document_id"]
    )
    op.create_index(
        "ix_validation_failures_data_type", "validation_failures", ["data_type"]
    )
    op.create_index(
        "ix_validation_failures_reviewed", "validation_failures", ["reviewed"]
    )
    op.create_index(
        "ix_validation_failures_rejected_at", "validation_failures", ["rejected_at"]
    )

    # Create partial index for unreviewed failures (for review queue)
    op.execute(
        """
        CREATE INDEX ix_validation_failures_unreviewed 
        ON validation_failures (rejected_at DESC) 
        WHERE reviewed = false
    """
    )

    print("✓ Added confidence_score and validation_warnings to budget_lines")
    print("✓ Added confidence_score and validation_warnings to audits")
    print("✓ Created validation_failures table with indexes")


def downgrade() -> None:
    """Remove validation fields and validation_failures table."""

    # Drop validation_failures table and its indexes
    op.drop_index("ix_validation_failures_unreviewed", table_name="validation_failures")
    op.drop_index(
        "ix_validation_failures_rejected_at", table_name="validation_failures"
    )
    op.drop_index("ix_validation_failures_reviewed", table_name="validation_failures")
    op.drop_index("ix_validation_failures_data_type", table_name="validation_failures")
    op.drop_index(
        "ix_validation_failures_document_id", table_name="validation_failures"
    )
    op.drop_table("validation_failures")

    # Remove validation fields from audits table
    op.drop_column("audits", "validation_warnings")
    op.drop_column("audits", "confidence_score")

    # Remove validation fields from budget_lines table
    op.drop_column("budget_lines", "validation_warnings")
    op.drop_column("budget_lines", "confidence_score")

    print("✓ Removed validation fields and validation_failures table")

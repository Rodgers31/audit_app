"""Database migration to add indexes for performance optimization.

Covers columns frequently used in WHERE, JOIN, GROUP BY, and ORDER BY clauses.
Uses if_not_exists=True so the migration is safe to re-run.
"""

from alembic import op

revision = "add_performance_indexes"
down_revision = "63ca92d190e7"  # Previous migration
branch_labels = None
depends_on = None


def upgrade():
    """Add indexes for better query performance."""

    # ── Audits ──────────────────────────────────────────────────────────
    op.create_index(
        "ix_audits_entity_period",
        "audits",
        ["entity_id", "period_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_audits_severity", "audits", ["severity"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_audits_source_doc", "audits", ["source_document_id"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_audits_audit_year", "audits", ["audit_year"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_audits_query_type", "audits", ["query_type"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_audits_audit_opinion", "audits", ["audit_opinion"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_audits_status", "audits", ["status"],
        unique=False, if_not_exists=True,
    )

    # ── Budget Lines ────────────────────────────────────────────────────
    op.create_index(
        "ix_budget_lines_entity_period",
        "budget_lines",
        ["entity_id", "period_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_budget_lines_category", "budget_lines", ["category"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_budget_lines_source_doc", "budget_lines", ["source_document_id"],
        unique=False, if_not_exists=True,
    )

    # ── Entities ────────────────────────────────────────────────────────
    op.create_index(
        "ix_entities_type", "entities", ["type"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_entities_country", "entities", ["country_id"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_entities_canonical_name", "entities", ["canonical_name"],
        unique=False, if_not_exists=True,
    )

    # ── Loans ───────────────────────────────────────────────────────────
    op.create_index(
        "ix_loans_entity", "loans", ["entity_id"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_loans_lender", "loans", ["lender"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_loans_debt_category", "loans", ["debt_category"],
        unique=False, if_not_exists=True,
    )

    # ── Source Documents ────────────────────────────────────────────────
    op.create_index(
        "ix_source_documents_country", "source_documents", ["country_id"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_source_documents_type", "source_documents", ["doc_type"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_source_documents_fetch_date", "source_documents", ["fetch_date"],
        unique=False, if_not_exists=True,
    )

    # ── Extractions ─────────────────────────────────────────────────────
    op.create_index(
        "ix_extractions_source_doc", "extractions", ["source_document_id"],
        unique=False, if_not_exists=True,
    )

    # ── Fiscal Periods ──────────────────────────────────────────────────
    op.create_index(
        "ix_fiscal_periods_country", "fiscal_periods", ["country_id"],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        "ix_fiscal_periods_dates", "fiscal_periods", ["start_date", "end_date"],
        unique=False, if_not_exists=True,
    )


def downgrade():
    """Remove indexes."""

    # Audits
    op.drop_index("ix_audits_entity_period", table_name="audits")
    op.drop_index("ix_audits_severity", table_name="audits")
    op.drop_index("ix_audits_source_doc", table_name="audits")
    op.drop_index("ix_audits_audit_year", table_name="audits")
    op.drop_index("ix_audits_query_type", table_name="audits")
    op.drop_index("ix_audits_audit_opinion", table_name="audits")
    op.drop_index("ix_audits_status", table_name="audits")

    # Budget Lines
    op.drop_index("ix_budget_lines_entity_period", table_name="budget_lines")
    op.drop_index("ix_budget_lines_category", table_name="budget_lines")
    op.drop_index("ix_budget_lines_source_doc", table_name="budget_lines")

    # Entities
    op.drop_index("ix_entities_type", table_name="entities")
    op.drop_index("ix_entities_country", table_name="entities")
    op.drop_index("ix_entities_canonical_name", table_name="entities")

    # Loans
    op.drop_index("ix_loans_entity", table_name="loans")
    op.drop_index("ix_loans_lender", table_name="loans")
    op.drop_index("ix_loans_debt_category", table_name="loans")

    # Source Documents
    op.drop_index("ix_source_documents_country", table_name="source_documents")
    op.drop_index("ix_source_documents_type", table_name="source_documents")
    op.drop_index("ix_source_documents_fetch_date", table_name="source_documents")

    # Extractions
    op.drop_index("ix_extractions_source_doc", table_name="extractions")

    # Fiscal Periods
    op.drop_index("ix_fiscal_periods_country", table_name="fiscal_periods")
    op.drop_index("ix_fiscal_periods_dates", table_name="fiscal_periods")

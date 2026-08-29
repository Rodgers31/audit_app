"""Database migration to add indexes for performance optimization.

Covers columns frequently used in WHERE, JOIN, GROUP BY, and ORDER BY clauses.

``if_not_exists=True`` makes each statement safe to RE-run, but it guards the
wrong thing: it checks whether the *index* exists, not whether the *column*
does. Four of the indexes below target columns that migration ``c3d4e5f6a7b8``
adds five revisions LATER (``audit_year``, ``query_type``, ``audit_opinion``,
``status``), so a fresh database failed here with::

    UndefinedColumn: column "audit_year" does not exist
    [SQL: CREATE INDEX IF NOT EXISTS ix_audits_audit_year ON audits (audit_year)]

Production never hit it because ``database.py`` calls
``Base.metadata.create_all()``, which creates every column in ``models.py``
before migrations run — so the chain has never been replayable from scratch,
and no new environment could be built from it.

``_create_index_if_columns_exist`` skips an index whose columns are not present
yet and logs the skip; ``c3d4e5f6a7b8`` now creates those four itself, next to
the columns it adds. Already-migrated databases are unaffected — this revision
does not re-run for them.
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "add_performance_indexes"
down_revision = "63ca92d190e7"  # Previous migration
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _create_index_if_columns_exist(name, table, columns, **kw):
    """Create an index only when every target column already exists.

    A skip is logged, never swallowed silently: a missing index that nobody
    mentions is how a query plan quietly regresses.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        logger.warning("skipping index %s — table %s does not exist yet", name, table)
        return
    present = {c["name"] for c in inspector.get_columns(table)}
    missing = [c for c in columns if c not in present]
    if missing:
        logger.warning(
            "skipping index %s on %s — column(s) not present yet: %s "
            "(a later revision adds them and creates the index there)",
            name,
            table,
            ", ".join(missing),
        )
        return
    op.create_index(name, table, columns, **kw)


def upgrade():
    """Add indexes for better query performance."""

    # ── Audits ──────────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_audits_entity_period",
        "audits",
        ["entity_id", "period_id"],
        unique=False,
        if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_severity", "audits", ["severity"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_source_doc", "audits", ["source_document_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_audit_year", "audits", ["audit_year"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_query_type", "audits", ["query_type"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_audit_opinion", "audits", ["audit_opinion"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_audits_status", "audits", ["status"],
        unique=False, if_not_exists=True,
    )

    # ── Budget Lines ────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_budget_lines_entity_period",
        "budget_lines",
        ["entity_id", "period_id"],
        unique=False,
        if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_budget_lines_category", "budget_lines", ["category"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_budget_lines_source_doc", "budget_lines", ["source_document_id"],
        unique=False, if_not_exists=True,
    )

    # ── Entities ────────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_entities_type", "entities", ["type"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_entities_country", "entities", ["country_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_entities_canonical_name", "entities", ["canonical_name"],
        unique=False, if_not_exists=True,
    )

    # ── Loans ───────────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_loans_entity", "loans", ["entity_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_loans_lender", "loans", ["lender"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_loans_debt_category", "loans", ["debt_category"],
        unique=False, if_not_exists=True,
    )

    # ── Source Documents ────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_source_documents_country", "source_documents", ["country_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_source_documents_type", "source_documents", ["doc_type"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_source_documents_fetch_date", "source_documents", ["fetch_date"],
        unique=False, if_not_exists=True,
    )

    # ── Extractions ─────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_extractions_source_doc", "extractions", ["source_document_id"],
        unique=False, if_not_exists=True,
    )

    # ── Population Data ─────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_population_data_entity", "population_data", ["entity_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_population_data_entity_year", "population_data", ["entity_id", "year"],
        unique=False, if_not_exists=True,
    )

    # ── GDP Data ─────────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_gdp_data_entity", "gdp_data", ["entity_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_gdp_data_entity_year", "gdp_data", ["entity_id", "year"],
        unique=False, if_not_exists=True,
    )

    # ── Pending Bills ────────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_pending_bills_entity", "pending_bills", ["entity_id"],
        unique=False, if_not_exists=True,
    )

    # ── Fiscal Periods ──────────────────────────────────────────────────
    _create_index_if_columns_exist(
        "ix_fiscal_periods_country", "fiscal_periods", ["country_id"],
        unique=False, if_not_exists=True,
    )
    _create_index_if_columns_exist(
        "ix_fiscal_periods_dates", "fiscal_periods", ["start_date", "end_date"],
        unique=False, if_not_exists=True,
    )


def downgrade():
    """Remove indexes."""

    # Audits
    op.drop_index("ix_audits_entity_period", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_severity", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_source_doc", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_audit_year", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_query_type", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_audit_opinion", table_name="audits", if_exists=True)
    op.drop_index("ix_audits_status", table_name="audits", if_exists=True)

    # Budget Lines
    op.drop_index("ix_budget_lines_entity_period", table_name="budget_lines", if_exists=True)
    op.drop_index("ix_budget_lines_category", table_name="budget_lines", if_exists=True)
    op.drop_index("ix_budget_lines_source_doc", table_name="budget_lines", if_exists=True)

    # Entities
    op.drop_index("ix_entities_type", table_name="entities", if_exists=True)
    op.drop_index("ix_entities_country", table_name="entities", if_exists=True)
    op.drop_index("ix_entities_canonical_name", table_name="entities", if_exists=True)

    # Loans
    op.drop_index("ix_loans_entity", table_name="loans", if_exists=True)
    op.drop_index("ix_loans_lender", table_name="loans", if_exists=True)
    op.drop_index("ix_loans_debt_category", table_name="loans", if_exists=True)

    # Source Documents
    op.drop_index("ix_source_documents_country", table_name="source_documents", if_exists=True)
    op.drop_index("ix_source_documents_type", table_name="source_documents", if_exists=True)
    op.drop_index("ix_source_documents_fetch_date", table_name="source_documents", if_exists=True)

    # Extractions
    op.drop_index("ix_extractions_source_doc", table_name="extractions", if_exists=True)

    # Population Data
    op.drop_index("ix_population_data_entity", table_name="population_data", if_exists=True)
    op.drop_index("ix_population_data_entity_year", table_name="population_data", if_exists=True)

    # GDP Data
    op.drop_index("ix_gdp_data_entity", table_name="gdp_data", if_exists=True)
    op.drop_index("ix_gdp_data_entity_year", table_name="gdp_data", if_exists=True)

    # Pending Bills
    op.drop_index("ix_pending_bills_entity", table_name="pending_bills", if_exists=True)

    # Fiscal Periods
    op.drop_index("ix_fiscal_periods_country", table_name="fiscal_periods", if_exists=True)
    op.drop_index("ix_fiscal_periods_dates", table_name="fiscal_periods", if_exists=True)

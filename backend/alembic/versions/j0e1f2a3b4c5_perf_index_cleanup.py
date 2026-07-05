"""perf_index_cleanup

Phase 2 (performance) for the Supabase advisor findings:
  * "Duplicate Index" on national_entities and parliament_source_documents
  * "Unindexed foreign keys" on 14 tables (15 FK columns)

DUPLICATE INDEXES
-----------------
Both tables declared a column as ``unique=True, index=True`` AND a named
``UniqueConstraint`` on the same column, producing two unique indexes:
  * national_entities.entity_id  -> ix_national_entities_entity_id  (dup of uq_national_entity)
  * parliament_source_documents.source_document_id -> ix_parliament_source_documents_source_document_id (dup of uq_parliament_src_doc)
We drop the redundant ``ix_*`` index and keep the named UniqueConstraint (which
still provides both the uniqueness guarantee and the index for FK lookups). The
matching models.py change removes ``unique=True, index=True`` from those columns
so create_all() does not recreate the duplicate on a fresh database.

UNINDEXED FOREIGN KEYS
----------------------
Add a btree index on each FK column that is not already the leading column of an
index (verified against the live catalog). Follows the existing convention in
add_performance_indexes.py: performance indexes live in migrations, not as
column-level index=True in models.py.

Idempotent + guarded (CREATE INDEX IF NOT EXISTS behind a to_regclass check) so
it is safe to re-run and safe on environments where a create_all()-only table
does not yet exist. On the live/prod database every table exists, so all 15
indexes are created when CI runs `alembic upgrade head`.

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-07-05
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "j0e1f2a3b4c5"
down_revision = "i9d0e1f2a3b4"
branch_labels = None
depends_on = None


# (index_name, table, column) — one btree index per unindexed FK column.
FK_INDEXES = [
    ("ix_annotations_user_id", "annotations", "user_id"),
    ("ix_audits_period_id", "audits", "period_id"),
    ("ix_budget_lines_period_id", "budget_lines", "period_id"),
    ("ix_debt_timeline_source_document_id", "debt_timeline", "source_document_id"),
    ("ix_economic_indicators_source_document_id", "economic_indicators", "source_document_id"),
    ("ix_fiscal_summaries_source_document_id", "fiscal_summaries", "source_document_id"),
    ("ix_gdp_data_source_document_id", "gdp_data", "source_document_id"),
    ("ix_loans_source_document_id", "loans", "source_document_id"),
    ("ix_national_entities_parent_ministry_entity_id", "national_entities", "parent_ministry_entity_id"),
    ("ix_pending_bills_source_document_id", "pending_bills", "source_document_id"),
    ("ix_population_data_source_document_id", "population_data", "source_document_id"),
    ("ix_poverty_indices_source_document_id", "poverty_indices", "source_document_id"),
    ("ix_revenue_by_source_source_document_id", "revenue_by_source", "source_document_id"),
    ("ix_user_question_answers_question_id", "user_question_answers", "question_id"),
    ("ix_user_question_answers_user_id", "user_question_answers", "user_id"),
]

# (redundant_index_name, table) — dropped; the named UniqueConstraint remains.
DUP_INDEXES = [
    ("ix_national_entities_entity_id", "national_entities"),
    ("ix_parliament_source_documents_source_document_id", "parliament_source_documents"),
]


def upgrade() -> None:
    for idx, tbl, col in FK_INDEXES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{tbl}') IS NOT NULL THEN
                    EXECUTE 'CREATE INDEX IF NOT EXISTS {idx} ON public.{tbl} ({col})';
                END IF;
            END $$;
            """
        )
    for idx, _tbl in DUP_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS public.{idx};")


def downgrade() -> None:
    # Recreate the (unique) duplicate indexes that were dropped.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_national_entities_entity_id "
        "ON public.national_entities (entity_id);"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_parliament_source_documents_source_document_id "
        "ON public.parliament_source_documents (source_document_id);"
    )
    for idx, _tbl, _col in FK_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS public.{idx};")

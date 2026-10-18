"""Neutral report baseline/release state; no rollout or acceptance is seeded."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'a708b15a0001'
down_revision = 'a706b15a0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_source_cursors', sa.Column('report_state', JSONB(), nullable=True))
    # A definer view exposes only identities and a SHA-256 witness. The worker
    # never receives SELECT on the application/financial tables beneath it.
    # Include mutable eligibility, requested lineage, actual retained receipt
    # rows, date authority and county/report cohort; absent/deleted inputs must
    # change the witness even when generation is disabled or a hook refuses.
    # Exclude job telemetry and unrelated acquisition entries, which do not
    # establish the exact ingestion under review. Source changes are handled
    # conservatively: a changed witness requires fresh human review.
    source_select = '''
        SELECT b.id AS record_id, j.id AS ingestion_id,
          encode(sha256(convert_to(jsonb_build_array(
            to_jsonb(b)-'provenance'-'created_at'-'updated_at', lineage.entry,
            to_jsonb(e), to_jsonb(p), to_jsonb(d),
            jsonb_build_array(j.id,j.domain,j.status,j.dry_run,j.started_at,j.finished_at,j.errors,j.metadata->>'source_mode'),
            to_jsonb(dated), receipts.items, cohort.items
          )::text,'UTF8')),'hex') AS authority_fingerprint
        FROM budget_lines b
        JOIN entities e ON e.id=b.entity_id
        JOIN fiscal_periods p ON p.id=b.period_id
        JOIN source_documents d ON d.id=b.source_document_id
        CROSS JOIN LATERAL jsonb_array_elements(
          CASE WHEN jsonb_typeof(b.provenance)='array' THEN b.provenance ELSE '[]'::jsonb END) lineage(entry)
        JOIN ingestion_jobs j ON j.id::text=lineage.entry->>'ingestion_job_id'
        LEFT JOIN extractions dated ON dated.id::text=d.metadata->'publication_date_evidence'->>'extraction_id'
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(to_jsonb(x) ORDER BY x.id) AS items FROM extractions x
          WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(lineage.entry->'source_evidence')='array'
              THEN lineage.entry->'source_evidence' ELSE '[]'::jsonb END) evidence
            WHERE x.id::text=evidence->'receipt'->>'extraction_id')
        ) receipts ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_array(c.id,c.source_document_id,c.period_id) ORDER BY c.id) AS items
          FROM budget_lines c WHERE c.entity_id=b.entity_id
            AND c.provenance @> jsonb_build_array(jsonb_build_object('ingestion_job_id',j.id))
        ) cohort ON true
    '''
    op.execute('CREATE VIEW social_report_source_authority_snapshot WITH (security_barrier=true) AS '+source_select)
    # The producer remains REPEATABLE READ READ ONLY. Admission additionally
    # holds SHARE locks on the same rows until its durable permit commits, so
    # a source withdrawal cannot commit between the witness read and permit.
    locked_select = source_select.replace('to_jsonb(dated)', 'dated.item').replace(
        "LEFT JOIN extractions dated ON dated.id::text=d.metadata->'publication_date_evidence'->>'extraction_id'",
        """LEFT JOIN LATERAL (SELECT to_jsonb(locked_date) AS item FROM (
          SELECT x.* FROM extractions x
          WHERE x.id::text=d.metadata->'publication_date_evidence'->>'extraction_id'
          FOR SHARE OF x) locked_date) dated ON true""").replace(
        'AS items FROM extractions x\n          WHERE EXISTS',
        'AS items FROM (SELECT x.* FROM extractions x\n          WHERE EXISTS').replace(
        "WHERE x.id::text=evidence->'receipt'->>'extraction_id')",
        "WHERE x.id::text=evidence->'receipt'->>'extraction_id') FOR SHARE OF x) x").replace(
        'FROM budget_lines c WHERE c.entity_id=b.entity_id',
        'FROM (SELECT c.* FROM budget_lines c WHERE c.entity_id=b.entity_id').replace(
        "AND c.provenance @> jsonb_build_array(jsonb_build_object('ingestion_job_id',j.id))",
        "AND c.provenance @> jsonb_build_array(jsonb_build_object('ingestion_job_id',j.id)) FOR SHARE OF c) c")
    # Entity UPDATE conflicts with a new county BudgetLine's foreign-key
    # KEY SHARE lock, preventing a conflicting cohort phantom during admission.
    op.execute('CREATE VIEW social_report_source_authority WITH (security_barrier=true) AS '+locked_select+' FOR SHARE OF b,p,d,j FOR UPDATE OF e')
    op.execute('REVOKE ALL ON social_report_source_authority, social_report_source_authority_snapshot FROM PUBLIC')


def downgrade():
    # Discarding a report baseline could reclassify retained releases as new.
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT 1 FROM social_source_cursors WHERE report_state IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Retain report release history before downgrade')
    op.execute('DROP VIEW social_report_source_authority, social_report_source_authority_snapshot')
    op.drop_column('social_source_cursors', 'report_state')

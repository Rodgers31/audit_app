"""708 digest port under an actual ephemeral restricted login on owned55412."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from test_report_postgres import pg, enabled, ingest


@pytest.fixture
def report_worker(pg, monkeypatch):
    factory, owner = pg
    enabled(factory, monkeypatch)
    from social.models import SocialControls
    with factory.begin() as db: db.add(SocialControls(id=1, publishing_enabled=False))
    role = 'report_worker_' + uuid4().hex
    with owner.begin() as conn:
        conn.execute(text('CREATE ROLE '+role+" LOGIN PASSWORD 'inert-local-only' NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2"))
    worker = create_engine(owner.url.set(username=role, password='inert-local-only'), pool_size=2, max_overflow=0)
    try:
        install_worker_role(owner, role)
        verify_worker_role(worker, role)
        yield factory, owner, worker, role
    finally:
        worker.dispose()
        with owner.begin() as conn:
            conn.execute(text('DROP OWNED BY '+role))
            conn.execute(text('DROP ROLE '+role))


def test_digest_port_actual_login_exposes_no_financial_rows(report_worker, tmp_path):
    factory, owner, worker, role = report_worker
    ingest(factory, tmp_path)
    with worker.begin() as conn:
        rows = conn.execute(text('SELECT * FROM social_report_source_authority')).mappings().all()
        assert rows and all(set(row)=={'record_id','ingestion_id','authority_fingerprint'} for row in rows)
        assert all(len(row['authority_fingerprint']) == 64 for row in rows)
    for sql in ['SELECT * FROM budget_lines', 'SELECT * FROM source_documents', 'SELECT * FROM extractions',
                "UPDATE social_report_source_authority SET authority_fingerprint=repeat('a',64)",
                'DELETE FROM social_report_source_authority', 'SELECT * FROM ingestion_jobs', 'SELECT * FROM social_report_source_authority_snapshot']:
        with pytest.raises(Exception) as error:
            with worker.begin() as conn: conn.execute(text(sql))
        assert error.value.orig.pgcode in ('42501','55000')
    with worker.connect() as conn:
        assert conn.scalar(text("SELECT NOT has_table_privilege(current_user,'social_report_source_authority','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"))
    verify_worker_role(worker, role)


@pytest.mark.parametrize('drift', ['definition', 'columns', 'options', 'owner', 'rewrite', 'grant_option', 'unrelated_view', 'missing', 'literal'])
def test_digest_view_drift_refuses_readiness_and_install(report_worker, drift):
    _, owner, worker, role = report_worker
    other = 'report_other_' + uuid4().hex
    with owner.begin() as conn:
        original = conn.scalar(text("SELECT pg_get_viewdef('social_report_source_authority'::regclass,true)"))
    snapshot_original = None
    try:
        with owner.begin() as conn:
            if drift == 'literal':
                snapshot_original = conn.scalar(text("SELECT pg_get_viewdef('social_report_source_authority_snapshot'::regclass,true)"))
                for name, definition in [('social_report_source_authority',original), ('social_report_source_authority_snapshot',snapshot_original)]:
                    altered = definition.replace("'source_mode'", "'public.source_mode'")
                    assert altered != definition
                    conn.execute(text('CREATE OR REPLACE VIEW '+name+' WITH (security_barrier=true) AS '+altered))
            if drift == 'definition':
                conn.execute(text("CREATE OR REPLACE VIEW social_report_source_authority AS SELECT 1 AS record_id,1 AS ingestion_id,repeat('a',64) AS authority_fingerprint"))
            if drift == 'columns': conn.execute(text('ALTER VIEW social_report_source_authority RENAME COLUMN record_id TO wrong_id'))
            if drift == 'options': conn.execute(text('ALTER VIEW social_report_source_authority SET (security_invoker=true)'))
            if drift == 'owner':
                conn.execute(text('CREATE ROLE '+other))
                conn.execute(text('ALTER VIEW social_report_source_authority OWNER TO '+other))
            if drift == 'rewrite': conn.execute(text('CREATE RULE unexpected AS ON UPDATE TO social_report_source_authority DO INSTEAD NOTHING'))
            if drift == 'grant_option': conn.execute(text('GRANT SELECT ON social_report_source_authority TO '+role+' WITH GRANT OPTION'))
            if drift == 'unrelated_view':
                conn.execute(text('CREATE VIEW unrelated_authority AS SELECT 1 AS value'))
                conn.execute(text('GRANT SELECT ON unrelated_authority TO '+role))
            if drift == 'missing': conn.execute(text('ALTER VIEW social_report_source_authority RENAME TO hidden_report_authority'))
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role)
        with pytest.raises(WorkerRoleError): install_worker_role(owner, role)
    finally:
        with owner.begin() as conn:
            if drift == 'literal':
                for name, definition in [('social_report_source_authority',original), ('social_report_source_authority_snapshot',snapshot_original)]:
                    conn.execute(text('CREATE OR REPLACE VIEW '+name+' WITH (security_barrier=true) AS '+definition))
            if drift == 'missing': conn.execute(text('ALTER VIEW hidden_report_authority RENAME TO social_report_source_authority'))
            if drift == 'columns': conn.execute(text('ALTER VIEW social_report_source_authority RENAME COLUMN wrong_id TO record_id'))
            if drift == 'definition': conn.execute(text('CREATE OR REPLACE VIEW social_report_source_authority WITH (security_barrier=true) AS '+original))
            if drift == 'options': conn.execute(text('ALTER VIEW social_report_source_authority RESET (security_invoker)'))
            if drift == 'owner':
                conn.execute(text('ALTER VIEW social_report_source_authority OWNER TO postgres'))
                conn.execute(text('DROP ROLE '+other))
            if drift == 'rewrite': conn.execute(text('DROP RULE unexpected ON social_report_source_authority'))
            if drift == 'grant_option': conn.execute(text('REVOKE GRANT OPTION FOR SELECT ON social_report_source_authority FROM '+role))
            if drift == 'unrelated_view': conn.execute(text('DROP VIEW unrelated_authority'))
        verify_worker_role(worker, role)


@pytest.mark.parametrize('source', ['record', 'entity', 'period', 'document', 'date_receipt', 'qualification', 'job'])
def test_restricted_admission_holds_source_locks_until_permit_transaction_ends(report_worker, tmp_path, source):
    from models import BudgetLine, SourceDocument
    from sqlalchemy import select
    factory, owner, worker, _ = report_worker
    job = ingest(factory, tmp_path)
    with factory() as db:
        row = db.scalar(select(BudgetLine).order_by(BudgetLine.id))
        doc = db.get(SourceDocument, row.source_document_id)
        proof = doc.meta['publication_date_evidence']['extraction_id']
        qualification = row.provenance[-1]['source_evidence'][0]['receipt']['extraction_id']
        updates = {
            'record': ('budget_lines','publishable=false',row.id),
            'entity': ('entities',"canonical_name='changed during admission'",row.entity_id),
            'period': ('fiscal_periods',"label='changed during admission'",row.period_id),
            'document': ('source_documents',"publisher='changed during admission'",doc.id),
            'date_receipt': ('extractions',"extractor='changed during admission'",proof),
            'qualification': ('extractions',"extractor='changed during admission'",qualification),
            'job': ('ingestion_jobs',"errors='[\"changed during admission\"]'::jsonb",job),
        }
        record_id = row.id
    table, value, identity = updates[source]
    update = text('UPDATE '+table+' SET '+value+' WHERE id=:id')
    with worker.begin() as admission:
        witness = admission.scalar(text('SELECT authority_fingerprint FROM social_report_source_authority WHERE record_id=:record AND ingestion_id=:job'), {'record':record_id,'job':job})
        assert witness
        with pytest.raises(Exception) as blocked:
            with owner.begin() as writer:
                writer.execute(text("SET LOCAL lock_timeout='100ms'"))
                writer.execute(update, {'id':identity})
        assert blocked.value.orig.pgcode == '55P03'
    with owner.begin() as writer:
        writer.execute(text("SET LOCAL lock_timeout='100ms'"))
        assert writer.execute(update, {'id':identity}).rowcount == 1
    with worker.begin() as admission:
        changed = admission.scalar(text('SELECT authority_fingerprint FROM social_report_source_authority WHERE record_id=:record AND ingestion_id=:job'), {'record':record_id,'job':job})
        assert changed != witness

"""Reviewed optional digest-view DDL. Importing creates no object or grant."""


def _id(value):
    # Bigint accommodates every at-most-ten-digit candidate without overflow.
    return f"CASE WHEN ({value}) ~ '^[1-9][0-9]{{0,9}}$' THEN ({value})::bigint END"


def _branch(domain, *, financial, locked):
    kind = 'financial' if financial else 'report'
    table = {'national_budget':'budget_lines', 'revenue_by_source':'revenue_by_source', 'pending_bills':'loans'}.get(domain)
    root = table if financial else 'extractions'
    binding = f"d.value->'metadata'->'native_report_authority_v1'->'{domain}'"
    row_lock = ' FOR SHARE OF b' if locked else ''
    source_lock = ' FOR UPDATE OF s' if locked else ''
    share = lambda alias: ' FOR SHARE OF '+alias if locked else ''
    data = "(to_jsonb(b)-'created_at'-'updated_at')" if financial else 'to_jsonb(b)'
    extras = (',b.entity_id' if financial and domain != 'revenue_by_source' else '')
    extras += ',b.period_id' if financial and domain == 'national_budget' else ''
    business = f'(SELECT b.id,b.source_document_id,{data} AS value{extras} FROM {root} b{row_lock}) b'
    entity = fiscal = "'null'::jsonb"
    joins = ''
    if financial and domain != 'revenue_by_source':
        joins += f' JOIN LATERAL (SELECT to_jsonb(e) AS value FROM entities e WHERE e.id=b.entity_id{share("e")}) e ON true'
        entity = 'e.value'
    if financial and domain == 'national_budget':
        joins += f' JOIN LATERAL (SELECT to_jsonb(p) AS value FROM fiscal_periods p WHERE p.id=b.period_id{share("p")}) p ON true'
        fiscal = 'p.value'
    entries = "b.value->'metadata'" if domain == 'revenue_by_source' else "b.value->'provenance'"
    entries = f"CASE WHEN jsonb_typeof({entries})='array' THEN {entries} ELSE jsonb_build_array({entries}) END"
    references = f"jsonb_path_query_array({entries}, '$[*].source_evidence[*].receipt.extraction_id')" if financial else "'[]'::jsonb"
    report_identity = _id(binding+"->>'extraction_id'")
    job_identity = _id(binding+"->>'ingestion_id'")
    return f'''
      SELECT '{kind}'::text AS source_kind,'{domain}'::text AS native_domain,
        b.id AS record_id,j.id AS ingestion_id,
        encode(sha256(convert_to(jsonb_build_array('native-worker-witness-v1','{kind}','{domain}',
          b.value,d.value,c.value,{entity},{fiscal},r.value,
          jsonb_build_array(j.id,j.domain,j.status,j.dry_run,j.started_at,j.finished_at,j.errors,
            j.metadata->'source_mode',j.metadata->'native_report_records'),receipts.items,origins.items)::text,'UTF8')),'hex') AS authority_fingerprint
      FROM {business}
      JOIN LATERAL (SELECT s.id,s.country_id,to_jsonb(s) AS value FROM source_documents s
        WHERE s.id=b.source_document_id{source_lock}) d ON true
      JOIN LATERAL (SELECT x.id,to_jsonb(x) AS value FROM extractions x
        WHERE x.id={report_identity}{share('x')}) r ON true
      JOIN LATERAL (SELECT j.id,j.domain,j.status,j.dry_run,j.started_at,j.finished_at,j.errors,j.metadata
        FROM ingestion_jobs j WHERE j.id={job_identity} AND j.domain='{domain}'{share('j')}) j ON true
      JOIN LATERAL (SELECT to_jsonb(c) AS value FROM countries c WHERE c.id=d.country_id{share('c')}) c ON true
      {joins}
      LEFT JOIN LATERAL (
        SELECT jsonb_agg(x.value ORDER BY x.id) AS items,
          jsonb_agg(x.value#>'{{extracted_json,response_receipt,retained_pdf_validation,origin_extraction_id}}') AS origin_ids
        FROM (SELECT x.id,jsonb_build_object('id',x.id,'source_document_id',x.source_document_id,
          'extractor',x.extractor,'extracted_json',jsonb_build_object('response_receipt',x.extracted_json->'response_receipt')) AS value
          FROM extractions x WHERE x.id IN (
            SELECT {_id("v#>>'{}'")} FROM jsonb_array_elements({references}) v UNION SELECT r.id
          ){share('x')}) x
      ) receipts ON true
      LEFT JOIN LATERAL (
        SELECT jsonb_agg(x.value ORDER BY x.id) AS items FROM (
          SELECT x.id,jsonb_build_object('id',x.id,'source_document_id',x.source_document_id,'extractor',x.extractor,
            'receipt',(x.extracted_json->'response_receipt')-'observations') AS value
          FROM extractions x WHERE x.id IN (SELECT {_id("v#>>'{}'")}
            FROM jsonb_array_elements(COALESCE(receipts.origin_ids,'[]'::jsonb)) v){share('x')}) x
      ) origins ON true
      WHERE r.value->>'extractor'='native-report-authority-v1'
        {'AND b.id=r.id' if not financial else ''}
        AND NOT EXISTS (SELECT 1 FROM ingestion_jobs newer WHERE newer.domain=j.domain AND newer.id>j.id
          AND newer.dry_run=false AND newer.status::text IN ('COMPLETED','COMPLETED_WITH_ERRORS')
          AND newer.metadata->>'source_mode' IN ('live','partial')
          AND ('{domain}'<>'audits' OR newer.metadata->'native_report_series' ?
            (r.value#>>'{{extracted_json,response_receipt,observations,0,scope_key}}')))
    '''


def definition(*, locked):
    branches = [_branch(domain, financial=False, locked=locked) for domain in
                ('national_budget','revenue_by_source','audits','pending_bills')]
    branches += [_branch(domain, financial=True, locked=locked) for domain in
                 ('national_budget','revenue_by_source','pending_bills')]
    return ' UNION ALL '.join('('+branch+')' for branch in branches)


def create_views(conn):
    """Called only by the explicit operator installer, inside its transaction."""
    for suffix,locked in [('_snapshot',False),('',True)]:
        name='social_native_source_authority'+suffix
        conn.exec_driver_sql('CREATE VIEW public.'+name+' WITH (security_barrier=true) AS '+definition(locked=locked))
        conn.exec_driver_sql('REVOKE ALL ON public.'+name+' FROM PUBLIC')


def install_native_authority(engine, role, schema='public'):
    """Explicit additive operator action; same login, one digest-only SELECT.

    Existing unexpected authority or DDL drift refuses the whole transaction.
    No role, function, model table, password, policy or activation is created.
    """
    from sqlalchemy import text
    from sqlalchemy.engine import Engine
    from .role_contract import _require,_scope,_limits,_verify,_views,_quoted,WorkerRoleError
    try:
        _scope(role,schema)
        _require(schema=='public' and isinstance(engine,Engine))
        with engine.begin() as conn:
            _limits(conn)
            # Existing grants and policies must already be the accepted role.
            # A repeated complete installation is safe and creates no new ACL.
            exists=conn.scalar(text("SELECT to_regclass('public.social_native_source_authority') IS NOT NULL"))
            _verify(conn,role,schema,current=False)
            if not exists:
                conn.execute(text('SET LOCAL search_path=pg_catalog,public,pg_temp'))
                create_views(conn)
                conn.execute(text('SET LOCAL search_path=pg_catalog,pg_temp'))
                _views(conn,schema)
                conn.execute(text('GRANT SELECT ON public.social_native_source_authority TO '+_quoted(conn,role)))
            _verify(conn,role,schema,current=False)
    except Exception:
        raise WorkerRoleError('WORKER_ROLE_UNAVAILABLE') from None

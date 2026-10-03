-- REVIEW ONLY. Root refreshes/approves inputs and prerequisites. Default ROLLBACK.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TEMP TABLE source_disposition_plan(payload jsonb) ON COMMIT DROP;
INSERT INTO source_disposition_plan VALUES ($source_disposition_319${"capture_canonical_sha256": "75be5b82e0a00680aca5c19e12d7e10665b169be45cd763235c7911f182a2f01", "captured_utc": "2026-10-03T14:47:50.079456+00:00", "changes": [{"after": {"content_type": null, "country_id": 1, "created_at": "2025-11-02T03:04:49.328928", "doc_type": "BUDGET", "fetch_date": "2025-11-02T03:04:49.328928", "file_path": null, "http_status": null, "id": 1707, "last_seen_at": "2025-11-02T03:04:49.328928", "last_verified_at": null, "md5": null, "metadata": {"dataset_id": "fixture-budgets", "disposition": {"historical_git_commit": "ec7706c8395d8ccf4dc86e9a9af7a1c0d9cc0777", "issue": 319, "original_publisher": "Controller of Budget", "original_status": "AVAILABLE", "reason": "Retained app artefact; excluded from public publisher inventory."}, "source_classification": "test_fixture"}, "publisher": "AuditGava (test fixture)", "status": "ARCHIVED", "title": "County Budget Execution Summary", "url": "https://fixtures.example/budgets"}, "before": {"content_type": null, "country_id": 1, "created_at": "2025-11-02T03:04:49.328928", "doc_type": "BUDGET", "fetch_date": "2025-11-02T03:04:49.328928", "file_path": null, "http_status": null, "id": 1707, "last_seen_at": "2025-11-02T03:04:49.328928", "last_verified_at": null, "md5": null, "metadata": {"dataset_id": "fixture-budgets"}, "publisher": "Controller of Budget", "status": "AVAILABLE", "title": "County Budget Execution Summary", "url": "https://fixtures.example/budgets"}, "id": 1707}, {"after": {"content_type": null, "country_id": 1, "created_at": "2025-11-09T21:39:32.113397", "doc_type": "BUDGET", "fetch_date": "2025-11-09T21:39:32.113397", "file_path": null, "http_status": null, "id": 1718, "last_seen_at": "2026-04-20T03:29:19.60125", "last_verified_at": null, "md5": null, "metadata": {"data_quality": "estimated", "disposition": {"historical_git_commit": "ec7706c8395d8ccf4dc86e9a9af7a1c0d9cc0777", "issue": 319, "original_publisher": "Controller of Budget", "original_status": "AVAILABLE", "reason": "Retained app artefact; excluded from public publisher inventory."}, "source_classification": "modelled_estimate", "source_label": "Estimated based on CRA Equitable Share FY 2023/24"}, "publisher": "AuditGava (modelled estimate)", "status": "ARCHIVED", "title": "Estimated based on CRA Equitable Share FY 2023/24", "url": "https://www.crakenya.org/county-allocations/"}, "before": {"content_type": null, "country_id": 1, "created_at": "2025-11-09T21:39:32.113397", "doc_type": "BUDGET", "fetch_date": "2025-11-09T21:39:32.113397", "file_path": null, "http_status": null, "id": 1718, "last_seen_at": "2026-04-20T03:29:19.60125", "last_verified_at": null, "md5": null, "metadata": {"data_quality": "estimated", "source_label": "Estimated based on CRA Equitable Share FY 2023/24"}, "publisher": "Controller of Budget", "status": "AVAILABLE", "title": "Estimated based on CRA Equitable Share FY 2023/24", "url": "https://www.crakenya.org/county-allocations/"}, "id": 1718}], "foreign_keys": [{"conname": "audits_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "audits", "to_table": "source_documents"}, {"conname": "budget_lines_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "budget_lines", "to_table": "source_documents"}, {"conname": "debt_instruments_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "debt_instruments", "to_table": "source_documents"}, {"conname": "debt_timeline_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "debt_timeline", "to_table": "source_documents"}, {"conname": "economic_indicators_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE SET NULL", "from_table": "economic_indicators", "to_table": "source_documents"}, {"conname": "extractions_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "extractions", "to_table": "source_documents"}, {"conname": "fiscal_summaries_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "fiscal_summaries", "to_table": "source_documents"}, {"conname": "gdp_data_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE SET NULL", "from_table": "gdp_data", "to_table": "source_documents"}, {"conname": "loans_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "loans", "to_table": "source_documents"}, {"conname": "parliament_source_documents_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "parliament_source_documents", "to_table": "source_documents"}, {"conname": "population_data_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE SET NULL", "from_table": "population_data", "to_table": "source_documents"}, {"conname": "poverty_indices_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE SET NULL", "from_table": "poverty_indices", "to_table": "source_documents"}, {"conname": "revenue_by_source_source_document_id_fkey", "definition": "FOREIGN KEY (source_document_id) REFERENCES source_documents(id)", "from_table": "revenue_by_source", "to_table": "source_documents"}], "logical_scan_columns": [{"column": "payload", "table": "admin_audit_log"}, {"column": "provenance", "table": "audits"}, {"column": "validation_warnings", "table": "audits"}, {"column": "provenance", "table": "budget_lines"}, {"column": "validation_warnings", "table": "budget_lines"}, {"column": "metadata", "table": "countries"}, {"column": "metadata", "table": "debt_instruments"}, {"column": "metadata", "table": "debt_timeline"}, {"column": "metadata", "table": "economic_indicators"}, {"column": "alt_names", "table": "entities"}, {"column": "metadata", "table": "entities"}, {"column": "extracted_json", "table": "extractions"}, {"column": "metadata", "table": "fiscal_summaries"}, {"column": "metadata", "table": "gdp_data"}, {"column": "errors", "table": "ingestion_jobs"}, {"column": "metadata", "table": "ingestion_jobs"}, {"column": "provenance", "table": "loans"}, {"column": "metadata", "table": "newsletter_subscribers"}, {"column": "metadata", "table": "parliament_source_documents"}, {"column": "metadata", "table": "population_data"}, {"column": "metadata", "table": "poverty_indices"}, {"column": "tags", "table": "quick_questions"}, {"column": "metadata", "table": "revenue_by_source"}, {"column": "metadata", "table": "source_documents"}, {"column": "roles", "table": "users"}, {"column": "metadata", "table": "validation_failures"}, {"column": "raw_data", "table": "validation_failures"}, {"column": "validation_errors", "table": "validation_failures"}, {"column": "validation_warnings", "table": "validation_failures"}, {"column": "metadata", "table": "watchlist_items"}], "schema": "source_disposition_plan/v1"}$source_disposition_319$::jsonb);
-- Coordinated writer window required. Lock every public table inspected by the
-- logical-reference guard, so new JSON references cannot enter during review.
DO $guard$ DECLARE t record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LOOP
  EXECUTE format('LOCK TABLE public.%I IN SHARE ROW EXCLUSIVE MODE', t.tablename);
 END LOOP;
END $guard$;
CREATE TEMP VIEW disposition_changes AS SELECT x FROM source_disposition_plan, jsonb_array_elements(payload->'changes') x;
CREATE FUNCTION pg_temp.disposition_logical_ref(v jsonb, key text DEFAULT '') RETURNS boolean LANGUAGE plpgsql AS $guard$
DECLARE item record; child jsonb; scalar text;
BEGIN
 IF jsonb_typeof(v)='object' THEN
  FOR item IN SELECT * FROM jsonb_each(v) LOOP
   IF pg_temp.disposition_logical_ref(item.value, item.key) THEN RETURN true; END IF;
  END LOOP;
 ELSIF jsonb_typeof(v)='array' THEN
  FOR child IN SELECT * FROM jsonb_array_elements(v) LOOP
   IF pg_temp.disposition_logical_ref(child, key) THEN RETURN true; END IF;
  END LOOP;
 ELSIF jsonb_typeof(v) IN ('number','string') THEN
  scalar := btrim(v #>> '{}');
  IF key IN ('source_document_id','source_document_ids','source_id','document_id','doc_id') AND scalar ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN
   IF scalar::numeric IN (1707,1718) THEN RETURN true; END IF;
  END IF;
  IF jsonb_typeof(v)='string' AND (position('https://fixtures.example/budgets' IN scalar)>0 OR position('https://www.crakenya.org/county-allocations/' IN scalar)>0) THEN RETURN true; END IF;
 END IF;
 RETURN false;
END $guard$;
DO $guard$ DECLARE actual jsonb; t record; found boolean; BEGIN
 SELECT coalesce(jsonb_agg(jsonb_build_object('table',table_name,'column',column_name) ORDER BY table_name,column_name),'[]'::jsonb) INTO actual FROM information_schema.columns WHERE table_schema='public' AND data_type IN ('json','jsonb');
 IF actual IS DISTINCT FROM (SELECT payload->'logical_scan_columns' FROM source_disposition_plan) THEN RAISE EXCEPTION 'Logical column catalogue drift'; END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace WHERE c.contype='f' AND c.confrelid='public.source_documents'::regclass AND n.nspname<>'public') THEN RAISE EXCEPTION 'Source FK outside reviewed public scope'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('conname',c.conname,'definition',pg_get_constraintdef(c.oid),'from_table',cl.relname,'to_table','source_documents') ORDER BY c.conname), '[]'::jsonb)
 INTO actual FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
 WHERE c.contype='f' AND c.confrelid='public.source_documents'::regclass AND n.nspname='public';
 IF actual IS DISTINCT FROM (SELECT payload->'foreign_keys' FROM source_disposition_plan) THEN RAISE EXCEPTION 'Source FK catalogue drift'; END IF;
 FOR t IN SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND column_name='source_document_id' LOOP
  EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE %I IN (1707,1718))',t.table_schema,t.table_name,t.column_name) INTO found;
  IF found THEN RAISE EXCEPTION 'Source dependency present: %',t.table_name; END IF;
 END LOOP;
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LOOP
  IF t.tablename='source_documents' THEN
   EXECUTE 'SELECT EXISTS(SELECT 1 FROM public.source_documents d WHERE d.id NOT IN (1707,1718) AND pg_temp.disposition_logical_ref(to_jsonb(d)))' INTO found;
  ELSE
   EXECUTE format('SELECT EXISTS(SELECT 1 FROM public.%I d WHERE pg_temp.disposition_logical_ref(to_jsonb(d)))',t.tablename) INTO found;
  END IF;
  IF found THEN RAISE EXCEPTION 'Logical source reference present: %',t.tablename; END IF;
 END LOOP;
END $guard$;
DO $guard$ BEGIN
 IF EXISTS(SELECT 1 FROM disposition_changes p LEFT JOIN public.source_documents d ON d.id=(p.x->>'id')::int WHERE d.id IS NULL OR to_jsonb(d) IS DISTINCT FROM p.x->'after') THEN
  RAISE EXCEPTION 'Complete source before-image drift: refresh and review';
 END IF;
END $guard$;
UPDATE public.source_documents d SET
 publisher=p.x->'before'->>'publisher',
 status=(jsonb_populate_record(NULL::public.source_documents,p.x->'before')).status,
 metadata=p.x->'before'->'metadata'
FROM disposition_changes p WHERE d.id=(p.x->>'id')::int RETURNING d.id;
DO $guard$ BEGIN
 IF EXISTS(SELECT 1 FROM disposition_changes p LEFT JOIN public.source_documents d ON d.id=(p.x->>'id')::int WHERE d.id IS NULL OR to_jsonb(d) IS DISTINCT FROM p.x->'before') THEN
  RAISE EXCEPTION 'Complete source after-image mismatch';
 END IF;
END $guard$;
-- Review exact returned IDs1707/1718; all other row columns retained.
ROLLBACK;

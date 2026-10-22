-- Supplement only: READ ONLY; no application function executes and no role is assumed.
-- Run on source within root's bounded freeze and locally on the restored target.
-- Keep complete output private; compare exact per-role privilege hashes.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD'; SET LOCAL extra_float_digits=3;
SELECT json_build_object('kind','effective_privileges','server_version',current_setting('server_version'),
 'rows',(SELECT json_agg(json_build_array(r.rolname,
  has_database_privilege(r.oid,current_database(),'CONNECT'),has_database_privilege(r.oid,current_database(),'CREATE'),has_database_privilege(r.oid,current_database(),'TEMP'),
  (SELECT encode(sha256(convert_to(coalesce(string_agg(row_text,'' ORDER BY row_text),''),'UTF8')),'hex') FROM (
   SELECT json_build_array('schema',n.nspname,has_schema_privilege(r.oid,n.oid,'USAGE'),has_schema_privilege(r.oid,n.oid,'CREATE'))::text row_text FROM pg_namespace n WHERE n.nspname !~ '^pg_temp_[0-9]+$' AND n.nspname !~ '^pg_toast_temp_[0-9]+$'
   UNION ALL
   SELECT json_build_array('relation',n.nspname,c.relname,p,has_table_privilege(r.oid,c.oid,p))::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) p WHERE c.relkind IN ('r','v','m','f','p') AND n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
   UNION ALL
   SELECT json_build_array('column',n.nspname,c.relname,a.attname,p,has_column_privilege(r.oid,c.oid,a.attnum,p))::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) p WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','v','m','f','p') AND n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
   UNION ALL
   SELECT json_build_array('sequence',n.nspname,c.relname,p,has_sequence_privilege(r.oid,c.oid,p))::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN unnest(ARRAY['SELECT','UPDATE','USAGE']) p WHERE c.relkind='S' AND n.nspname !~ '^pg_'
   UNION ALL
   SELECT json_build_array('routine',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),has_function_privilege(r.oid,p.oid,'EXECUTE'))::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
   UNION ALL
   SELECT json_build_array('type',n.nspname,t.typname,has_type_privilege(r.oid,t.oid,'USAGE'))::text FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
   UNION ALL
   SELECT json_build_array('role',x.rolname,p,pg_has_role(r.oid,x.oid,p))::text FROM pg_roles x CROSS JOIN unnest(ARRAY['USAGE','MEMBER','SET']) p
  ) matrix)) ORDER BY r.rolname) FROM pg_roles r));
ROLLBACK;

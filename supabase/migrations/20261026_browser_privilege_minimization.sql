-- Auth-project follow-up to the effective B90/B91 catalog review (#789).
-- Run as postgres against the verified project that owns the user tables.
-- No records, RLS policies, role memberships or existing server grants change.
BEGIN;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

DO $guard$
DECLARE relation regclass;
BEGIN
  IF current_user <> 'postgres' THEN
    RAISE EXCEPTION 'Privilege repair requires the reviewed postgres owner';
  END IF;
  FOREACH relation IN ARRAY ARRAY[
    'public.profiles'::regclass,
    'public.watchlist_items'::regclass,
    'public.data_alerts'::regclass
  ] LOOP
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_class
      WHERE oid=relation AND relkind='r' AND relrowsecurity
        AND relowner=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres')) THEN
      RAISE EXCEPTION 'User table ownership/RLS differs from the reviewed profile';
    END IF;
  END LOOP;
END;
$guard$;

-- These operations are outside row-level policy enforcement. Retain the
-- existing SELECT/INSERT/UPDATE/DELETE privileges used by RLS-governed UI flows.
REVOKE TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
  ON public.profiles, public.watchlist_items, public.data_alerts
  FROM PUBLIC, anon, authenticated;

-- Table REFERENCES revocation does not clear possible column-level grants.
DO $columns$
DECLARE column_record record;
BEGIN
  FOR column_record IN
    SELECT c.relname,a.attname FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
    WHERE n.nspname='public'
      AND c.relname IN ('profiles','watchlist_items','data_alerts')
      AND a.attnum>0 AND NOT a.attisdropped
  LOOP
    EXECUTE format('REVOKE REFERENCES (%I) ON public.%I FROM PUBLIC, anon, authenticated',
                   column_record.attname,column_record.relname);
  END LOOP;
END;
$columns$;

-- Internal trigger helpers and audit identity are not browser RPCs. Preserve
-- the existing audit_log_reader identity grant and all service/owner grants.
-- Audit helpers may be absent on an auth-only project; do not create them.
DO $functions$
DECLARE name text; function_oid regprocedure;
BEGIN
  FOREACH name IN ARRAY ARRAY['audit_log_capture','audit_log_immutable',
    'audit_log_identity','handle_new_user','set_updated_at','protect_profile_roles']
  LOOP
    function_oid := pg_catalog.to_regprocedure(format('public.%I()',name));
    IF function_oid IS NOT NULL THEN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_proc WHERE oid=function_oid
        AND proowner=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres')) THEN
        RAISE EXCEPTION 'Helper ownership differs from the reviewed profile';
      END IF;
      EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon, authenticated',function_oid);
    END IF;
  END LOOP;
END;
$functions$;

-- Application migrations use postgres. Its public tables already default to
-- owner/service-only in the observed project. Future internal functions and
-- sequences must also require intentional browser grants. Per-schema REVOKE
-- alone cannot remove PostgreSQL's built-in global PUBLIC function EXECUTE.
-- This global change affects FUTURE postgres-created functions only; existing
-- functions and the managed supabase_admin/storage/auth defaults are untouched.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- An inherited/column grant cannot silently defeat the scoped revocations.
DO $verify$
DECLARE browser_role text; relation regclass; name text; function_oid regprocedure;
BEGIN
  FOREACH browser_role IN ARRAY ARRAY['anon','authenticated'] LOOP
    FOREACH relation IN ARRAY ARRAY['public.profiles'::regclass,
      'public.watchlist_items'::regclass,'public.data_alerts'::regclass] LOOP
      IF pg_catalog.has_table_privilege(browser_role,relation,
          'TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        OR pg_catalog.has_any_column_privilege(browser_role,relation,'REFERENCES') THEN
        RAISE EXCEPTION 'Browser retains inherited table-wide authority';
      END IF;
    END LOOP;
    FOREACH name IN ARRAY ARRAY['audit_log_capture','audit_log_immutable',
      'audit_log_identity','handle_new_user','set_updated_at','protect_profile_roles'] LOOP
      function_oid := pg_catalog.to_regprocedure(format('public.%I()',name));
      IF function_oid IS NOT NULL
        AND pg_catalog.has_function_privilege(browser_role,function_oid,'EXECUTE') THEN
        RAISE EXCEPTION 'Browser retains inherited helper execution';
      END IF;
    END LOOP;
  END LOOP;
END;
$verify$;

COMMIT;

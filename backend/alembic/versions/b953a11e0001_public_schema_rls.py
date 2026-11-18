"""Reconcile Alembic and deployed public table and sequence permissions (#953)."""

from alembic import op

revision = "b953a11e0001"
down_revision = "a756b20a0001"
branch_labels = None
depends_on = None

# Tables missing RLS in a clean replay of the parent revision. The deployed
# database already protects most of them. Existing policies remain in place.
_TABLES = (
    "alembic_version",
    "annotations",
    "audits",
    "budget_lines",
    "countries",
    "county_debt_instruments",
    "county_debt_observations",
    "data_alerts",
    "debt_instruments",
    "debt_timeline",
    "economic_indicators",
    "entities",
    "extractions",
    "fiscal_periods",
    "fiscal_summaries",
    "gdp_data",
    "imf_weo_observations",
    "ingestion_jobs",
    "loans",
    "newsletter_subscribers",
    "parliament_source_documents",
    "population_data",
    "poverty_indices",
    "quick_questions",
    "revenue_by_source",
    "source_documents",
    "user_question_answers",
    "users",
    "watchlist_items",
)


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return

    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    names = ", ".join(f"'{table}'" for table in _TABLES)
    op.execute(f"""
        DO $migration$
        DECLARE
            target regclass;
            table_name text;
            browser_role text;
            grantee text;
            table_privileges text;
            column_privileges text;
            columns text;
            watchlist_sequence text;
            maintenance_privilege text := CASE
                WHEN current_setting('server_version_num')::integer >= 170000 THEN ', MAINTAIN'
                ELSE '' END;
            table_operations text[] := ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE',
                                              'TRUNCATE', 'REFERENCES', 'TRIGGER'];
            unexpected record;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[{names}] LOOP
                target := format('public.%I', table_name)::regclass;
                IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid = target) THEN
                    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
                END IF;
            END LOOP;
            IF EXISTS (SELECT FROM pg_catalog.pg_class
                       WHERE oid = pg_catalog.to_regclass('public.profiles') AND NOT relrowsecurity) THEN
                ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
            END IF;

            -- profiles belongs to the optional Supabase Auth schema. Keep
            -- each existing authenticated user policy and its required grants.
            FOREACH browser_role IN ARRAY ARRAY['PUBLIC', 'anon', 'authenticated'] LOOP
                IF browser_role <> 'PUBLIC' AND NOT EXISTS (
                    SELECT FROM pg_catalog.pg_roles WHERE rolname = browser_role
                ) THEN
                    CONTINUE;
                END IF;
                grantee := CASE WHEN browser_role = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(browser_role) END;
                FOREACH table_name IN ARRAY ARRAY[{names}, 'profiles'] LOOP
                    target := pg_catalog.to_regclass(format('public.%I', table_name));
                    IF target IS NULL THEN
                        CONTINUE;
                    END IF;
                    table_privileges := 'ALL PRIVILEGES';
                    column_privileges := 'ALL PRIVILEGES';
                    IF browser_role = 'authenticated' THEN
                        CASE table_name
                            WHEN 'profiles' THEN
                                table_privileges := 'DELETE, TRUNCATE, REFERENCES, TRIGGER' || maintenance_privilege;
                                column_privileges := 'REFERENCES';
                            WHEN 'data_alerts' THEN
                                table_privileges := 'INSERT, DELETE, TRUNCATE, REFERENCES, TRIGGER' || maintenance_privilege;
                                column_privileges := 'INSERT, REFERENCES';
                            WHEN 'watchlist_items' THEN
                                table_privileges := 'TRUNCATE, REFERENCES, TRIGGER' || maintenance_privilege;
                                column_privileges := 'REFERENCES';
                            ELSE NULL;
                        END CASE;
                    END IF;
                    EXECUTE format('REVOKE %s ON TABLE public.%I FROM %s', table_privileges, table_name, grantee);
                    SELECT string_agg(quote_ident(attname), ', ' ORDER BY attnum) INTO columns
                    FROM pg_catalog.pg_attribute
                    WHERE attrelid = target AND attnum > 0 AND NOT attisdropped;
                    IF columns IS NOT NULL THEN
                        -- A list of privileges needs its own column list on each privilege.
                        EXECUTE format('REVOKE %s (%s) ON TABLE public.%I FROM %s',
                            replace(column_privileges, ', ', ' (' || columns || '), '),
                            columns, table_name, grantee);
                    END IF;
                END LOOP;
                EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %s', grantee);
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM %s',
                    current_user, grantee);
            END LOOP;

            -- Only the legacy serial watchlist ID needs nextval permission.
            -- An identity column needs INSERT on the table and no sequence grant.
            IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticated')
               AND pg_catalog.has_any_column_privilege('authenticated', 'public.watchlist_items', 'INSERT')
               AND EXISTS (
                   SELECT FROM pg_catalog.pg_attribute
                   WHERE attrelid = 'public.watchlist_items'::regclass AND attname = 'id' AND attidentity = ''
               )
            THEN
                watchlist_sequence := pg_catalog.pg_get_serial_sequence('public.watchlist_items', 'id');
                IF EXISTS (SELECT FROM pg_catalog.pg_class
                           WHERE oid = watchlist_sequence::regclass AND relnamespace = 'public'::regnamespace) THEN
                    EXECUTE format('GRANT USAGE ON SEQUENCE %s TO authenticated', watchlist_sequence);
                END IF;
            END IF;

            -- Effective privileges can still arrive from a role membership.
            -- Abort the migration instead of changing shared role memberships.
            IF maintenance_privilege <> '' THEN
                table_operations := array_append(table_operations, 'MAINTAIN');
            END IF;
            SELECT r.rolname, c.relname, p.operation INTO unexpected
            FROM pg_catalog.pg_roles AS r
            CROSS JOIN pg_catalog.pg_class AS c
            CROSS JOIN unnest(table_operations) AS p(operation)
            WHERE r.rolname IN ('anon', 'authenticated')
              AND c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p', 'f')
              AND (
                  r.rolbypassrls OR NOT c.relrowsecurity
                  OR pg_catalog.has_table_privilege(r.oid, c.oid, p.operation || ' WITH GRANT OPTION')
                  OR CASE WHEN p.operation IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')
                          THEN pg_catalog.has_any_column_privilege(r.oid, c.oid, p.operation || ' WITH GRANT OPTION')
                          ELSE false END
                  OR (
                      NOT (r.rolname = 'authenticated' AND (
                          (c.relname = 'profiles' AND p.operation IN ('SELECT', 'INSERT', 'UPDATE'))
                          OR (c.relname = 'data_alerts' AND p.operation IN ('SELECT', 'UPDATE'))
                          OR (c.relname = 'watchlist_items' AND p.operation IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE'))
                      ))
                      AND (pg_catalog.has_table_privilege(r.oid, c.oid, p.operation)
                           OR CASE WHEN p.operation IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')
                                   THEN pg_catalog.has_any_column_privilege(r.oid, c.oid, p.operation)
                                   ELSE false END)
                  )
              )
            LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION 'Unexpected public table boundary for % on % (%)',
                    unexpected.rolname, unexpected.relname, unexpected.operation;
            END IF;

            SELECT r.rolname, c.relname INTO unexpected
            FROM pg_catalog.pg_roles AS r
            CROSS JOIN pg_catalog.pg_class AS c
            WHERE r.rolname IN ('anon', 'authenticated')
              AND c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
              AND (pg_catalog.has_sequence_privilege(r.oid, c.oid, 'SELECT, UPDATE, USAGE WITH GRANT OPTION')
                   OR (pg_catalog.has_sequence_privilege(r.oid, c.oid, 'USAGE')
                       AND NOT (r.rolname = 'authenticated'
                                AND c.oid IS NOT DISTINCT FROM watchlist_sequence::regclass)))
            LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION 'Unexpected public sequence permission for % on %',
                    unexpected.rolname, unexpected.relname;
            END IF;

            -- A global default cannot be overridden by a schema REVOKE.
            -- Do not silently change sequence defaults in auth/storage schemas.
            IF EXISTS (
                SELECT FROM pg_catalog.pg_default_acl AS d
                CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) AS acl
                CROSS JOIN pg_catalog.pg_roles AS r
                WHERE d.defaclrole = current_user::regrole AND d.defaclnamespace = 0 AND d.defaclobjtype = 'S'
                  AND r.rolname IN ('anon', 'authenticated')
                  AND CASE WHEN acl.grantee = 0 THEN true
                           ELSE pg_catalog.pg_has_role(r.oid, acl.grantee, 'USAGE') END
            ) THEN
                RAISE EXCEPTION 'Global sequence defaults grant browser access';
            END IF;
        END;
        $migration$;
    """)


def downgrade():
    # The parent's ACLs and RLS flags differ across existing installations.
    # Leave the tighter settings in place when rolling back the app revision.
    pass

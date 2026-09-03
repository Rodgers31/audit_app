"""enable_rls_and_security_hardening

Closes the Supabase security-advisor "RLS Disabled in Public" criticals plus the
two function findings ("Function Search Path Mutable", "Public/Signed-In Can
Execute SECURITY DEFINER Function").

WHY THIS IS NEEDED
------------------
These tables are created by ``Base.metadata.create_all()`` (backend/database.py),
which creates the table but never enables Row Level Security. Meanwhile Supabase's
default privileges auto-GRANT full DML to the ``anon`` and ``authenticated`` roles
on every new ``public`` table. Result: any anonymous user holding the *public*
anon key (shipped in the browser bundle) can read AND write these tables directly
through PostgREST (https://<ref>.supabase.co/rest/v1/<table>), bypassing FastAPI.
Verified empirically on 2026-07-05: anon read live rows from countries/audits/
ingestion_jobs/imf_weo_observations; anon holds SELECT/INSERT/UPDATE/DELETE/
TRUNCATE on all of them.

WHY THIS IS SAFE
----------------
* The backend, Alembic, and the seeding job all connect as the ``postgres`` role
  (DB_USER=postgres.<ref>), which has rolbypassrls=true — RLS is invisible to it.
* The frontend uses supabase-js on ONLY profiles/watchlist_items/data_alerts/
  newsletter_subscribers (all already RLS-enabled). Every core data table is
  fetched through FastAPI (NEXT_PUBLIC_API_URL), never PostgREST.
* Enabling RLS with NO policy = deny-all for anon/authenticated via REST, while
  the postgres-role backend keeps full access. Nothing in the app breaks.

This migration ALSO revokes the existing anon/authenticated grants (defense in
depth) and fixes the default privileges so future create_all() tables do not
silently regress to world-writable.

NOTE: newsletter_subscribers RLS-policy tightening is handled separately in the
next migration (it requires a companion frontend change) so this critical fix can
be applied on its own via ``alembic upgrade h8c9d0e1f2a3``.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-07-05
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


# The 30 public tables flagged "RLS Disabled in Public" by the Supabase advisor.
# (The four user-facing tables — profiles, watchlist_items, data_alerts,
#  newsletter_subscribers — already have RLS enabled and are intentionally
#  excluded here.)
RLS_TABLES = [
    "admin_audit_log",
    "alembic_version",
    "annotations",
    "audits",
    "budget_lines",
    "constituencies",
    "countries",
    "county_org_units",
    "debt_timeline",
    "economic_indicators",
    "entities",
    "extractions",
    "fiscal_periods",
    "fiscal_summaries",
    "fiscal_years",
    "gdp_data",
    "imf_weo_observations",
    "ingestion_jobs",
    "loans",
    "national_entities",
    "parliament_source_documents",
    "pending_bills",
    "population_data",
    "poverty_indices",
    "quick_questions",
    "revenue_by_source",
    "source_documents",
    "user_question_answers",
    "users",
    "validation_failures",
]


def _tbl_array_sql() -> str:
    return "ARRAY[" + ", ".join(f"'{t}'" for t in RLS_TABLES) + "]"


def upgrade() -> None:
    # 1) Enable RLS on every flagged table + revoke the anon/authenticated grants.
    #    Guarded so it is safe on any environment (table/role may be absent) and
    #    idempotent (ENABLE ROW LEVEL SECURITY is a no-op if already on).
    op.execute(
        f"""
        DO $$
        DECLARE
            t text;
            has_anon boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon');
            has_auth boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated');
        BEGIN
            FOREACH t IN ARRAY {_tbl_array_sql()}
            LOOP
                IF to_regclass('public.' || t) IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
                    IF has_anon THEN
                        EXECUTE format('REVOKE ALL ON public.%I FROM anon', t);
                    END IF;
                    IF has_auth THEN
                        EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', t);
                    END IF;
                END IF;
            END LOOP;
        END $$;
        """
    )

    # 2) Stop the regression at the source: prevent Supabase's default privileges
    #    from auto-granting anon/authenticated on FUTURE tables created by postgres
    #    (i.e. anything create_all() makes from here on).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated';
            END IF;
        END $$;
        """
    )

    # 3) Function hardening.
    #    - set_updated_at: pin search_path (fixes "Function Search Path Mutable").
    #    - handle_new_user: revoke EXECUTE from public/anon/authenticated. It is a
    #      trigger function on auth.users (fired only by Supabase Auth); no client
    #      should be able to call it directly.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regprocedure('public.set_updated_at()') IS NOT NULL THEN
                EXECUTE $q$ALTER FUNCTION public.set_updated_at() SET search_path = ''$q$;
            END IF;

            IF to_regprocedure('public.handle_new_user()') IS NOT NULL THEN
                EXECUTE 'REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC';
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE 'REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE 'REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM authenticated';
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Faithful reversal — WARNING: this restores the insecure, world-writable
    # state (RLS off + anon/authenticated granted full DML). Kept only so the
    # migration is technically reversible.
    op.execute(
        f"""
        DO $$
        DECLARE
            t text;
            has_anon boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon');
            has_auth boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated');
        BEGIN
            FOREACH t IN ARRAY {_tbl_array_sql()}
            LOOP
                IF to_regclass('public.' || t) IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
                    IF has_anon THEN
                        EXECUTE format('GRANT ALL ON public.%I TO anon', t);
                    END IF;
                    IF has_auth THEN
                        EXECUTE format('GRANT ALL ON public.%I TO authenticated', t);
                    END IF;
                END IF;
            END LOOP;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO authenticated';
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regprocedure('public.set_updated_at()') IS NOT NULL THEN
                EXECUTE 'ALTER FUNCTION public.set_updated_at() RESET search_path';
            END IF;
            IF to_regprocedure('public.handle_new_user()') IS NOT NULL THEN
                EXECUTE 'GRANT EXECUTE ON FUNCTION public.handle_new_user() TO PUBLIC';
            END IF;
        END $$;
        """
    )

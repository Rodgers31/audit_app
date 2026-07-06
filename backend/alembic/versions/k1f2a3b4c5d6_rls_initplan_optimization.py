"""rls_initplan_optimization

Fixes the Supabase advisor "Auth RLS Initialization Plan" (auth_rls_initplan)
warnings on the user-scoped tables profiles, data_alerts and watchlist_items.

THE ISSUE
---------
Each RLS policy calls auth.uid() directly, e.g. ``USING (auth.uid() = user_id)``.
Postgres re-evaluates that function for every row scanned. Wrapping it as
``(select auth.uid())`` turns it into an InitPlan that is evaluated once per
query, which the advisor recommends for tables that can return many rows.

This is a PURELY PERFORMANCE change — ``(select auth.uid())`` is semantically
identical to ``auth.uid()``, so the access rules (users can only see/modify
their own rows) are unchanged. The frontend uses all three tables via
supabase-js and is unaffected.

Recreates the 5 existing policies verbatim except for the wrapped call:
  * data_alerts     "Users can read own alerts"      SELECT
  * data_alerts     "Users can update own alerts"    UPDATE
  * profiles        "Users can read own profile"     SELECT
  * profiles        "Users can update own profile"   UPDATE
  * watchlist_items "Users can manage own watchlist" ALL

Guarded with to_regclass so it is safe where a table is absent (these tables are
created by supabase/migrations, not alembic).

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-07-05
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "k1f2a3b4c5d6"
down_revision = "j0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # data_alerts
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.data_alerts') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can read own alerts" ON public.data_alerts';
                EXECUTE 'CREATE POLICY "Users can read own alerts" ON public.data_alerts
                         FOR SELECT USING ((select auth.uid()) = user_id)';
                EXECUTE 'DROP POLICY IF EXISTS "Users can update own alerts" ON public.data_alerts';
                EXECUTE 'CREATE POLICY "Users can update own alerts" ON public.data_alerts
                         FOR UPDATE USING ((select auth.uid()) = user_id)
                         WITH CHECK ((select auth.uid()) = user_id)';
            END IF;
        END $$;
        """
    )
    # profiles
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.profiles') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can read own profile" ON public.profiles';
                EXECUTE 'CREATE POLICY "Users can read own profile" ON public.profiles
                         FOR SELECT USING ((select auth.uid()) = id)';
                EXECUTE 'DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles';
                EXECUTE 'CREATE POLICY "Users can update own profile" ON public.profiles
                         FOR UPDATE USING ((select auth.uid()) = id)
                         WITH CHECK ((select auth.uid()) = id)';
            END IF;
        END $$;
        """
    )
    # watchlist_items
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.watchlist_items') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can manage own watchlist" ON public.watchlist_items';
                EXECUTE 'CREATE POLICY "Users can manage own watchlist" ON public.watchlist_items
                         FOR ALL USING ((select auth.uid()) = user_id)
                         WITH CHECK ((select auth.uid()) = user_id)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Restore the original un-wrapped policies.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.data_alerts') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can read own alerts" ON public.data_alerts';
                EXECUTE 'CREATE POLICY "Users can read own alerts" ON public.data_alerts
                         FOR SELECT USING (auth.uid() = user_id)';
                EXECUTE 'DROP POLICY IF EXISTS "Users can update own alerts" ON public.data_alerts';
                EXECUTE 'CREATE POLICY "Users can update own alerts" ON public.data_alerts
                         FOR UPDATE USING (auth.uid() = user_id)
                         WITH CHECK (auth.uid() = user_id)';
            END IF;
            IF to_regclass('public.profiles') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can read own profile" ON public.profiles';
                EXECUTE 'CREATE POLICY "Users can read own profile" ON public.profiles
                         FOR SELECT USING (auth.uid() = id)';
                EXECUTE 'DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles';
                EXECUTE 'CREATE POLICY "Users can update own profile" ON public.profiles
                         FOR UPDATE USING (auth.uid() = id)
                         WITH CHECK (auth.uid() = id)';
            END IF;
            IF to_regclass('public.watchlist_items') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS "Users can manage own watchlist" ON public.watchlist_items';
                EXECUTE 'CREATE POLICY "Users can manage own watchlist" ON public.watchlist_items
                         FOR ALL USING (auth.uid() = user_id)
                         WITH CHECK (auth.uid() = user_id)';
            END IF;
        END $$;
        """
    )

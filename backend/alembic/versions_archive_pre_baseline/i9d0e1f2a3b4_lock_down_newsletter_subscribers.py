"""lock_down_newsletter_subscribers

Fixes the Supabase advisor "RLS Policy Always True" findings on
public.newsletter_subscribers.

THE PROBLEM
-----------
newsletter_subscribers has RLS enabled, but its policies are permissive to the
``public`` role:
  * SELECT  USING (true)               -> ANY anon can dump the entire email list
  * UPDATE  USING (true) WITH CHECK (true) -> ANY anon can unsubscribe/alter any row
  * INSERT  WITH CHECK (true)          -> ANY anon can insert
Verified on 2026-07-05: an anonymous request with the public anon key retrieved
every subscriber email. This is a PII leak (email harvesting).

THE FIX
-------
The backend already exposes the correct server-side path (postgres role, bypasses
RLS): POST /api/v1/newsletter/{subscribe,unsubscribe}. Once the frontend routes
through those endpoints, the browser needs NO direct table access, so we drop the
permissive anon policies entirely and revoke the grants. Backend keeps working
because the postgres role bypasses RLS.

⚠️ SHIP TOGETHER WITH THE FRONTEND CHANGE
-----------------------------------------
This migration MUST be released together with the companion patch to
frontend/lib/api/auth.ts (subscribeNewsletter / unsubscribeNewsletter switched
from supabase.from('newsletter_subscribers') to apiClient.post('/newsletter/*')).
If this migration is applied while the browser still calls PostgREST directly,
newsletter subscribe/unsubscribe from the site will start failing.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-07-05
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "i9d0e1f2a3b4"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.newsletter_subscribers') IS NOT NULL THEN
                DROP POLICY IF EXISTS "Anyone can subscribe to newsletter"     ON public.newsletter_subscribers;
                DROP POLICY IF EXISTS "Subscribers can manage own subscription" ON public.newsletter_subscribers;
                DROP POLICY IF EXISTS "Service role can read all subscribers"   ON public.newsletter_subscribers;

                -- RLS stays ENABLED (already on). With no anon/authenticated
                -- policy, PostgREST denies them; the postgres/service_role
                -- backend bypasses RLS and continues to work.
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE 'REVOKE ALL ON public.newsletter_subscribers FROM anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE 'REVOKE ALL ON public.newsletter_subscribers FROM authenticated';
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Restore the original permissive policies + grants.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.newsletter_subscribers') IS NOT NULL THEN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON public.newsletter_subscribers TO anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON public.newsletter_subscribers TO authenticated';
                END IF;

                CREATE POLICY "Anyone can subscribe to newsletter"
                    ON public.newsletter_subscribers FOR INSERT
                    WITH CHECK (true);
                CREATE POLICY "Subscribers can manage own subscription"
                    ON public.newsletter_subscribers FOR UPDATE
                    USING (true) WITH CHECK (true);
                CREATE POLICY "Service role can read all subscribers"
                    ON public.newsletter_subscribers FOR SELECT
                    USING (true);
            END IF;
        END $$;
        """
    )

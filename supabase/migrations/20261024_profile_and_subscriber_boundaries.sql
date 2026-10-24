-- Auth-project hardening. Review and apply to the project that owns profiles;
-- backend Alembic migrations may target a different database. No grants change.
BEGIN;

CREATE OR REPLACE FUNCTION public.protect_profile_roles()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  -- The database role, not a mutable profile or request claim, is authority.
  -- Server-side service_role/owner operations retain their existing behavior.
  IF current_user IN ('anon', 'authenticated') THEN
    IF (TG_OP = 'INSERT' AND NEW.roles IS DISTINCT FROM ARRAY['citizen']::text[])
       OR (TG_OP = 'UPDATE' AND NEW.roles IS DISTINCT FROM OLD.roles) THEN
      RAISE EXCEPTION 'Profile authorization roles are managed by the server'
        USING ERRCODE = '42501';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_protect_roles ON public.profiles;
CREATE TRIGGER profiles_protect_roles
  BEFORE INSERT OR UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.protect_profile_roles();

-- Newsletter writes already go through the verified backend flow. A
-- restrictive policy also denies browser access when older permissive
-- policies remain on an independently managed auth project.
ALTER TABLE public.newsletter_subscribers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS newsletter_browser_deny ON public.newsletter_subscribers;
CREATE POLICY newsletter_browser_deny
  ON public.newsletter_subscribers AS RESTRICTIVE
  FOR ALL TO anon, authenticated
  USING (false) WITH CHECK (false);

COMMIT;

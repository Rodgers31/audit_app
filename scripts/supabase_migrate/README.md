# Supabase region migration — Mumbai → Frankfurt

Scripts + playbook for moving the project's Postgres + Auth data off
`ap-south-1` onto `eu-central-1`, co-located with the Render backend.

Follows [Supabase's official migration guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore) —
`supabase db dump`, single-transaction restore, `session_replication_role = replica`
to disable triggers during data load.

## What this does

- `01_dump.sh` — uses `supabase db dump` to export roles, schema, data
  (storage vector tables excluded per official guidance) and the
  `supabase_migrations` history. Writes to `./dumps/`.
- `02_restore.sh` — loads those dumps into a fresh Supabase project in
  the target region, in a single transaction with triggers disabled.
- `03_verify.sh` — row-count diff between old and new. Exit code 0 if
  everything matches.

## Prereqs

```bash
# Postgres client tools (psql)
brew install libpq
brew link --force libpq

# Supabase CLI (wraps pg_dump with Supabase-specific flags)
brew install supabase/tap/supabase

# Docker Desktop — the Supabase CLI shells out to it for pg_dump
# so it must be RUNNING (not just installed) when you run 01_dump.sh
open -a Docker
```

## One-time: create the new project

1. Dashboard → **New Project** → Region: `Europe Central (Frankfurt)`.
2. Use the **same DB password** as the old project if you want the
   connection strings to be structurally identical.
3. Wait ~2 min for the project to come up.
4. Enable any non-default extensions you had on the old project
   (`pg_stat_statements` is on by default; `pgvector`/`pgsodium` if
   you added them). You are not using pgvector or pgsodium, so skip.

## Get your connection strings

For each project: **Dashboard → Connect → Session pooler → URI**.

**Critical:** use the **session pooler (port 5432)**, not the transaction
pooler (6543). `pg_dump` needs real sessions. Shape:

```
postgresql://postgres.<REF>:<PW>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
```

For the app's runtime (Render `DATABASE_URL`) you still want the
**transaction pooler (6543)** — that's a different string.

## Run the migration

The scripts need two env vars: `OLD_DB` + `NEW_DB` (both session-pooler
URIs from Supabase dashboard). Either export them each time, or put
them in a local `.env.migration` file (gitignored) so the scripts pick
them up automatically.

### Option A (recommended): `.env.migration` file

```bash
cd scripts/supabase_migrate
cp .env.migration.example .env.migration
# Edit .env.migration and fill in both URIs from Supabase dashboard
# (Connect → Session pooler → URI). This file is gitignored.
```

### Option B: ad-hoc exports in your shell

```bash
cd scripts/supabase_migrate
export OLD_DB='postgresql://postgres.<OLD_REF>:<OLD_PW>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres'
export NEW_DB='postgresql://postgres.<NEW_REF>:<NEW_PW>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres'
```

### Then run, in order:

```bash
# Docker Desktop must be running
./01_dump.sh      # ~30s, writes ./dumps/
./02_restore.sh   # 1–5 min depending on data size
./03_verify.sh    # row-count diff
```

If `03_verify.sh` prints any `DIFF` lines, don't switch env vars yet.

## Update env vars (after verify passes)

Three places to update. Keep the OLD values around in case you need to
roll back.

### Render (backend)

Dashboard → your service → **Environment** → edit:

```
DATABASE_URL=postgresql://postgres.<NEW_REF>:<NEW_PW>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Save → **Manual Deploy** to pick it up.

### Vercel (frontend)

Dashboard → **Project Settings → Environment Variables** → update for
Production (and Preview if you use it):

```
NEXT_PUBLIC_SUPABASE_URL=https://<NEW_REF>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<NEW anon key from Settings → API>
SUPABASE_SERVICE_ROLE_KEY=<NEW service_role key>
```

Trigger a **Redeploy**.

### Local `.env.local`

Same three values in `frontend/.env.local`, plus root `.env`:

```
DATABASE_URL=postgresql://postgres.<NEW_REF>:<NEW_PW>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require
```

## Smoke-test

With the new env live:

- [ ] Sign in with an **existing** user account — should work with the
      old password (auth.users migrated with `encrypted_password`).
- [ ] Load `/counties` → the ranking table populates.
- [ ] Load `/transparency` → waterfall renders.
- [ ] Watchlist / alerts (any write endpoint) → persists.
- [ ] Sign up a new user → confirms new project's auth is wired.

## Post-restore checks (from Supabase docs)

These only matter if you use the feature — ignore if not:

- **Realtime publications**: if you subscribe to DB changes via Realtime,
  re-enable publications for the relevant tables in the new project:
  Dashboard → Database → Publications.
- **Database Webhooks**: if any were configured on the old project,
  re-enable them in the new project.
- **Column encryption (pgsodium)**: not used in this app, skip.
- **Custom role passwords**: only if you added custom DB roles. You did
  not, so skip.

## Rollback (if something breaks)

Two minutes to flip back:

1. Revert the three env-var files/dashboards to the OLD values.
2. Redeploy Render + Vercel.
3. Old project is still live, no data lost.

## When to delete the old project

Leave the old (Mumbai) project running **at least a week**. It costs
nothing on Free tier. After a week of the new project being stable:
Dashboard → old project → Settings → General → Delete project.

## Gotchas

- **RLS policies** come through in `schema.sql`. Spot-check a few in
  the new project's SQL editor after restore.
- **Alembic migrations** — don't re-run them against the new project;
  the schema dump already has everything applied.
- **Sessions invalidate**: all users get kicked out (JWTs were signed
  by the OLD project's signing key). One-time re-login, not a password
  reset.
- **`supabase_admin` ownership errors** during restore: comment out any
  `ALTER ... OWNER TO "supabase_admin"` lines in `dumps/schema.sql`
  before re-running `02_restore.sh`.
- **`cli_login_postgres` grant errors**: comment out any
  `GRANT "postgres" TO "cli_login_postgres"` line in `dumps/roles.sql`.

## File layout

```
scripts/supabase_migrate/
├── 01_dump.sh
├── 02_restore.sh
├── 03_verify.sh
├── README.md
├── _list_tables.sql            # used by verify
└── dumps/                      # git-ignored — local only
    ├── roles.sql
    ├── schema.sql
    ├── data.sql
    ├── history_schema.sql
    └── history_data.sql
```

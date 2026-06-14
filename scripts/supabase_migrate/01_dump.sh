#!/usr/bin/env bash
#
# 01_dump.sh — export from the OLD Supabase project using the official
# supabase-db-dump flow (supabase.com/docs/guides/platform/migrating-
# within-supabase/backup-restore). Produces four files in ./dumps/:
#
#   roles.sql              — custom DB roles
#   schema.sql             — full schema (public + auth + storage + ...)
#   data.sql               — data only, excluding storage vector tables
#   history_schema.sql     — supabase_migrations schema (optional)
#   history_data.sql       — supabase_migrations data (optional)
#
# Prereqs: `supabase` CLI on PATH, Docker Desktop running, `psql` on PATH.
# OLD_DB must be exported — see README for the connection string shape.

set -euo pipefail

cd "$(dirname "$0")"
# Auto-load .env.migration if it exists — lets the user put OLD_DB and
# NEW_DB in a file instead of exporting each time. The file is
# gitignored so passwords never reach the repo.
if [[ -f .env.migration ]]; then
  # shellcheck disable=SC1091
  set -a; source .env.migration; set +a
fi

: "${OLD_DB:?Set OLD_DB — either export it or fill in .env.migration}"

mkdir -p dumps

echo "▶ Checking prereqs…"
command -v supabase >/dev/null || { echo "❌ Install Supabase CLI: brew install supabase/tap/supabase"; exit 1; }
command -v psql >/dev/null || { echo "❌ Install psql: brew install libpq && brew link --force libpq"; exit 1; }
docker info >/dev/null 2>&1 || { echo "❌ Docker Desktop must be running (the supabase CLI shells out to Docker for pg_dump)"; exit 1; }

echo
echo "▶ Dumping roles (1/3)…"
supabase db dump --db-url "$OLD_DB" -f dumps/roles.sql --role-only
echo "  $(wc -l < dumps/roles.sql) lines written"

echo
echo "▶ Dumping schema (2/3)…"
supabase db dump --db-url "$OLD_DB" -f dumps/schema.sql
echo "  $(wc -l < dumps/schema.sql) lines written"

echo
echo "▶ Dumping data (3/3)…"
# --use-copy is faster + correct for large tables.
# Storage vector tables are excluded per Supabase docs — they are
# regenerated on the new project and copying them causes conflicts.
supabase db dump --db-url "$OLD_DB" \
  -f dumps/data.sql \
  --use-copy --data-only \
  -x storage.buckets_vectors \
  -x storage.vector_indexes
echo "  $(wc -l < dumps/data.sql) lines written"

echo
echo "▶ (optional) Dumping supabase_migrations history…"
supabase db dump --db-url "$OLD_DB" -f dumps/history_schema.sql \
  --schema supabase_migrations 2>/dev/null || true
supabase db dump --db-url "$OLD_DB" -f dumps/history_data.sql \
  --use-copy --data-only --schema supabase_migrations 2>/dev/null || true
if [[ -s dumps/history_schema.sql ]]; then
  echo "  migration history captured"
else
  echo "  no supabase_migrations schema present (fine — you use alembic)"
fi

echo
echo "✅ Dump complete. Files in ./dumps/:"
ls -lh dumps/

#!/usr/bin/env bash
#
# 02_restore.sh — load the dumps into the NEW Supabase project using
# the official flow: single transaction, roles first, then schema,
# then data with session_replication_role=replica (disables triggers
# so encryption/auth/user-creation triggers do not fire twice on
# migrated rows).

set -euo pipefail

cd "$(dirname "$0")"
if [[ -f .env.migration ]]; then
  # shellcheck disable=SC1091
  set -a; source .env.migration; set +a
fi

: "${NEW_DB:?Set NEW_DB — either export it or fill in .env.migration}"

for f in roles.sql schema.sql data.sql; do
  [[ -f "dumps/$f" ]] || { echo "❌ dumps/$f missing — run 01_dump.sh first."; exit 1; }
done

echo "▶ Restoring roles + schema + data in a single transaction…"
# One transaction, rolls back the whole thing on any error. The
# session_replication_role = replica is the key bit: it turns off
# triggers during the data restore so auth.users INSERT triggers
# (which e.g. create a public.users row) do not fire again on rows
# we are already migrating in.
psql \
  --single-transaction \
  --variable ON_ERROR_STOP=1 \
  --file dumps/roles.sql \
  --file dumps/schema.sql \
  --command 'SET session_replication_role = replica' \
  --file dumps/data.sql \
  --dbname "$NEW_DB" \
  > /tmp/restore_main.log 2>&1
echo "  done (log: /tmp/restore_main.log)"

echo
if [[ -s dumps/history_schema.sql ]]; then
  echo "▶ Restoring supabase_migrations history…"
  psql \
    --single-transaction \
    --variable ON_ERROR_STOP=1 \
    --file dumps/history_schema.sql \
    --file dumps/history_data.sql \
    --dbname "$NEW_DB" \
    > /tmp/restore_history.log 2>&1
  echo "  done"
fi

echo
echo "✅ Restore complete. Next:"
echo "   1. ./03_verify.sh              # row-count diff"
echo "   2. If you use Realtime, re-enable publications in the new"
echo "      project Dashboard → Database → Publications."
echo "   3. Update env vars in Render / Vercel / .env.local (see README)."

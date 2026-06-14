#!/usr/bin/env bash
#
# 03_verify.sh — compare row counts in every public table + auth.users
# and auth.identities between the OLD and NEW projects. Exits non-zero
# if any row count differs.

set -euo pipefail

cd "$(dirname "$0")"
if [[ -f .env.migration ]]; then
  # shellcheck disable=SC1091
  set -a; source .env.migration; set +a
fi

: "${OLD_DB:?Set OLD_DB — either export it or fill in .env.migration}"
: "${NEW_DB:?Set NEW_DB — either export it or fill in .env.migration}"

TABLES=$(psql "$NEW_DB" -Atq -f _list_tables.sql)
TABLES="$TABLES
auth.users
auth.identities"

printf "%-40s %12s %12s %8s\n" "TABLE" "OLD" "NEW" "DIFF"
printf -- "-%.0s" {1..76}; echo
mismatches=0
for t in $TABLES; do
  [[ -z "$t" ]] && continue
  old_count=$(psql "$OLD_DB" -Atq -c "SELECT COUNT(*) FROM $t" 2>/dev/null || echo ERR)
  new_count=$(psql "$NEW_DB" -Atq -c "SELECT COUNT(*) FROM $t" 2>/dev/null || echo ERR)
  diff_str="ok"
  if [[ "$old_count" != "$new_count" ]]; then
    diff_str="DIFF"
    mismatches=$((mismatches + 1))
  fi
  printf "%-40s %12s %12s %8s\n" "$t" "$old_count" "$new_count" "$diff_str"
done

echo
if [[ $mismatches -eq 0 ]]; then
  echo "✅ All table row counts match."
  exit 0
else
  echo "❌ $mismatches table(s) had row-count differences."
  exit 1
fi

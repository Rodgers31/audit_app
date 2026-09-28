#!/usr/bin/env python3
"""Deliberate, bounded, read-only production connection inventory.

This is separate from scripts/local_dev.py and is never called by it.
Use a database role whose grants are SELECT-only as well as this read-only
transaction. A filename or application_name alone grants no protection.
"""

import os
import sys


def main():
    url = os.environ.get("PRODUCTION_DIAGNOSTIC_DATABASE_URL")
    if not url:
        raise SystemExit("Set PRODUCTION_DIAGNOSTIC_DATABASE_URL explicitly for this invocation")

    import psycopg2

    with psycopg2.connect(
        url, application_name="auditgava-production-diagnostic", connect_timeout=5,
    ) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '8s'")
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise RuntimeError("Server did not accept a read-only transaction")
            cursor.execute("""
                SELECT application_name, count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                GROUP BY application_name
                ORDER BY application_name
            """)
            for app_name, count in cursor.fetchall():
                print(f"{app_name or '(unidentified)'}\t{count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Diagnostic failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None

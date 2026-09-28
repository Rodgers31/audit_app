#!/usr/bin/env python3
"""Deliberate, bounded, read-only production connection inventory.

This is separate from scripts/local_dev.py and is never called by it.
Use a database role whose grants are SELECT-only as well as this read-only
transaction. A filename or application_name alone grants no protection.
"""

import os
import sys
from urllib.parse import parse_qs, urlsplit


def connection_options(url):
    """Validate the destination and pin TLS before libpq can use environment defaults."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or parsed.fragment:
        raise ValueError("Diagnostic requires an explicit PostgreSQL TCP URL")
    options = parse_qs(parsed.query, keep_blank_values=True)
    if any(name in options for name in ("host", "hostaddr", "service", "servicefile")):
        raise ValueError("Diagnostic URL cannot override its host with connection options")
    modes = options.get("sslmode", [])
    if len(modes) > 1:
        raise ValueError("Diagnostic URL must specify sslmode once")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        # A libpq PGHOSTADDR environment value must not redirect the local exception.
        return {"hostaddr": "::1" if parsed.hostname == "::1" else "127.0.0.1"}
    if not modes or modes[0] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Remote diagnostic URL requires sslmode=require or stronger")
    return {"sslmode": modes[0]}


def main():
    url = os.environ.get("PRODUCTION_DIAGNOSTIC_DATABASE_URL")
    if not url:
        raise SystemExit("Set PRODUCTION_DIAGNOSTIC_DATABASE_URL explicitly for this invocation")
    options = connection_options(url)

    import psycopg2

    with psycopg2.connect(
        url, application_name="auditgava-production-diagnostic", connect_timeout=5,
        **options,
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

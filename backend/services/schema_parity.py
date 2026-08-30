"""Does the deployed database actually have the columns the models declare?

WHY THIS EXISTS
---------------
Found 2026-08-30. ``public.users`` in production had 6 of the 9 columns
``models.User`` declares, so every Supabase-authenticated request raised
``column users.display_name does not exist`` from
``supabase_auth.get_current_user``. It went unnoticed for months because that
table holds 0 rows — the failure only fires on a real sign-in.

Nothing in the pipeline could have caught it:

* the test suite builds its database with ``Base.metadata.create_all()``, so
  the schema matches the models **by construction** — a parity assertion there
  can never fail, which is the definition of a check that is not a check;
* ``alembic upgrade head`` reported success every night, because it was a
  no-op against the revision production was stamped at;
* ``alembic stamp --purge <baseline>`` ASSERTS that the database matches the
  baseline. It does not verify it. Any table that had already drifted stays
  drifted, silently, forever.

So the check has to run against the REAL deployed database, after migrating,
and it has to fail the deploy. That is what this module is for.

It deliberately reports only MISSING columns — columns the ORM will select and
the database does not have, i.e. guaranteed runtime errors. Extra columns in
the database are not a defect (Supabase adds its own, and hand-tuned tables
carry columns the models do not map), and flagging them would produce noise
nobody acts on.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger("schema_parity")


def find_missing_columns(
    live_columns: Dict[str, Iterable[str]],
    model_columns: Dict[str, Iterable[str]],
    *,
    ignore_tables: Optional[Iterable[str]] = None,
) -> Dict[str, List[str]]:
    """``{table: [columns the models declare and the database lacks]}``.

    Pure — takes two plain mappings so it is testable without a database, and
    so the caller decides where "live" comes from (an inspector, a fixture, a
    dump). A table the database does not have at all is reported with its full
    column list, because that is the same failure with a bigger blast radius.
    """
    skip = set(ignore_tables or ())
    missing: Dict[str, List[str]] = {}
    for table, wanted in model_columns.items():
        if table in skip:
            continue
        have = set(live_columns.get(table, ()))
        gap = sorted(set(wanted) - have)
        if gap:
            missing[table] = gap
    return missing


def check_database(engine, metadata, *, ignore_tables: Optional[Iterable[str]] = None):
    """Run :func:`find_missing_columns` against a live engine.

    Returns the same mapping; empty means every mapped column exists.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    live = {
        name: [c["name"] for c in inspector.get_columns(name)]
        for name in inspector.get_table_names()
    }
    model = {
        name: [c.name for c in table.columns] for name, table in metadata.tables.items()
    }
    return find_missing_columns(live, model, ignore_tables=ignore_tables)


def format_report(missing: Dict[str, List[str]]) -> str:
    if not missing:
        return "schema parity OK — every mapped column exists in the database"
    lines = ["SCHEMA DRIFT — the ORM will select columns the database does not have:"]
    for table in sorted(missing):
        lines.append(f"  {table}: {', '.join(missing[table])}")
    lines.append(
        "Every query touching these tables raises UndefinedColumn at runtime. "
        "Add a migration; do not stamp past it."
    )
    return "\n".join(lines)


__all__ = ["check_database", "find_missing_columns", "format_report"]

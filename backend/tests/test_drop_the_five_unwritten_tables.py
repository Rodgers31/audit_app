"""Migration ``ea1645a4c0b5`` drops the five unwritten tables, and only them.

Issue #137 P6. The decisions are unit-tested here with a stubbed connection:
which tables go, that a table holding a row stops the whole migration, and
that the downgrade puts back every table it took. The migration's behaviour
against real PostgreSQL (drop, schema parity, a byte-identical round trip of
the full ``pg_dump -s``) was rehearsed on a production clone; see the PR.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import types

import pytest

_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "ea1645a4c0b5_drop_the_five_tables_nothing_wrote.py"
)
FIVE = {"pending_bills", "fiscal_years", "county_org_units", "constituencies", "national_entities"}


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Bind:
    """Answers ``to_regclass`` and ``count(*)`` from a {table: rows} dict."""

    def __init__(self, tables):
        self.tables = tables

    def execute(self, statement, params=None):
        sql = str(statement)
        if "to_regclass" in sql:
            name = params["t"].split(".", 1)[1]
            return _Result(name if name in self.tables else None)
        m = re.search(r"count\(\*\) FROM public\.(\w+)", sql)
        if m:
            return _Result(self.tables[m.group(1)])
        raise AssertionError(f"unexpected query: {sql}")


class _Op:
    def __init__(self, tables):
        self.bind = _Bind(tables)
        self.executed = []

    def get_bind(self):
        return self.bind

    def execute(self, sql):
        self.executed.append(str(sql))


def _migration(op):
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = op
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = fake_alembic
    try:
        spec = importlib.util.spec_from_file_location("_mig_ea1645a4c0b5", _PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["alembic"] = saved
        else:
            del sys.modules["alembic"]
    return module


def _dropped(executed):
    return {m.group(1) for s in executed if (m := re.match(r"DROP TABLE public\.(\w+)", s))}


def test_it_drops_exactly_the_five_empty_tables_and_their_enum():
    op = _Op({t: 0 for t in FIVE})
    _migration(op).upgrade()
    assert _dropped(op.executed) == FIVE
    assert "DROP TYPE IF EXISTS public.billtype" in op.executed
    assert not any("CASCADE" in s.upper() for s in op.executed)


def test_parliament_source_documents_is_never_touched():
    """497 rows, written by etl/parliament_pipeline.py:405 — not dead.

    Even offered as present and empty, it is neither counted nor dropped.
    """
    tables = {t: 0 for t in FIVE}
    tables["parliament_source_documents"] = 0
    op = _Op(tables)
    module = _migration(op)
    module.upgrade()
    assert "parliament_source_documents" not in module.TABLES
    assert not any("parliament_source_documents" in s for s in op.executed)


def test_a_single_row_anywhere_stops_everything():
    tables = {t: 0 for t in FIVE}
    tables["constituencies"] = 1
    op = _Op(tables)
    with pytest.raises(RuntimeError, match="constituencies=1"):
        _migration(op).upgrade()
    assert op.executed == [], "nothing may be dropped once a row is found"


def test_an_already_missing_table_is_skipped_not_an_error():
    tables = {t: 0 for t in FIVE - {"fiscal_years"}}
    op = _Op(tables)
    _migration(op).upgrade()
    assert _dropped(op.executed) == FIVE - {"fiscal_years"}


def test_the_downgrade_recreates_every_table_it_dropped_with_rls():
    op = _Op({})
    _migration(op).downgrade()
    created = {m.group(1) for s in op.executed if (m := re.match(r"CREATE TABLE public\.(\w+)", s))}
    rls = {
        m.group(1)
        for s in op.executed
        if (m := re.match(r"ALTER TABLE public\.(\w+) ENABLE ROW LEVEL SECURITY", s))
    }
    assert created == FIVE
    assert rls == FIVE
    assert any(s.startswith("CREATE TYPE public.billtype") for s in op.executed)

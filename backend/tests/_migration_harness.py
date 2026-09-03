"""Drive a migration's ``upgrade``/``downgrade`` without a database.

A migration's *decision* — which columns it adds, which it drops — is
ordinary logic and deserves an ordinary unit test. Standing up Postgres to
assert "this downgrade should not drop a column it did not add" is slow
enough that the assertion never gets written, which is how the same defect
landed twice: once as ``confidence_score`` in ``b3d8ab47bf3b`` and again as
the ``users`` columns in ``d1a7c9e40b12``.

``op`` is replaced with a recorder and ``op.get_bind()`` with a stub whose
``information_schema`` query returns whatever the caller says the database
has, so the test states the starting schema and reads back the operations.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from typing import Iterable, List, Set

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


class _RecordingOp:
    """Stand-in for ``alembic.op`` that records instead of executing."""

    def __init__(self, existing: Set[str]):
        self._existing = set(existing)
        self.added: List[str] = []
        self.dropped: List[str] = []
        self.executed: List[str] = []

    # -- the operations these migrations actually use ------------------
    def add_column(self, table, column):
        self.added.append(column.name)
        self._existing.add(column.name)

    def drop_column(self, table, name):
        self.dropped.append(name)
        self._existing.discard(name)

    def execute(self, sql):
        self.executed.append(str(sql))

    def get_bind(self):
        return _StubBind(self._existing)


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return list(self._rows)


class _StubBind:
    """Answers the ``information_schema.columns`` probe and nothing else."""

    def __init__(self, existing: Set[str]):
        self._existing = existing

    def execute(self, statement, params=None):
        text = str(statement).lower()
        if "information_schema.columns" in text:
            return _StubResult([(name,) for name in sorted(self._existing)])
        return _StubResult([])


def _load(module_stem: str, recorder: _RecordingOp):
    path = _VERSIONS / f"{module_stem}.py"
    spec = importlib.util.spec_from_file_location(f"_mig_{module_stem}", path)
    module = importlib.util.module_from_spec(spec)

    # The migration does `from alembic import op`; give it the recorder.
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = recorder
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = fake_alembic
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["alembic"] = saved
        else:
            del sys.modules["alembic"]
    module.op = recorder
    return module


def run_migration_downgrade(
    module_stem: str, *, existing_columns: Iterable[str]
) -> List[str]:
    """Return the column names ``downgrade()`` would drop."""
    recorder = _RecordingOp(set(existing_columns))
    _load(module_stem, recorder).downgrade()
    return list(recorder.dropped)


def run_migration_upgrade(
    module_stem: str, *, existing_columns: Iterable[str]
) -> List[str]:
    """Return the column names ``upgrade()`` would add."""
    recorder = _RecordingOp(set(existing_columns))
    module = _load(module_stem, recorder)
    module.upgrade()
    return list(recorder.added)


__all__ = ["run_migration_downgrade", "run_migration_upgrade"]

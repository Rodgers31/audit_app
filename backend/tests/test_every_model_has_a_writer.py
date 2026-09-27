"""Every ORM model is written by something, or says why it is not yet.

Issue #137 P6. Five tables sat in ``models.py`` — and in production, RLS on,
0 rows each — with no code anywhere that ever put a row in them:
``pending_bills``, ``fiscal_years``, ``county_org_units``, ``constituencies``
and ``national_entities``. One of them was worse than empty: two
``/api/v1/pending-bills`` endpoints queried ``pending_bills`` first and fell
back to ``loans`` when it was empty, so a whole response branch (aging
buckets, eligible/ineligible totals) was reachable only from test fixtures,
and the live response carried a note telling readers to "Seed pending_bills
table for richer data" — a table no seeder writes.

The rule: a model is WRITTEN when some non-test code under ``backend/``,
``etl/`` or ``scripts/`` constructs it (``X(...)``), inserts into it
(``insert(X)``, ``X.__table__.insert()``, ``bulk_insert_mappings(X, ...)``),
or names its table in an ``INSERT INTO``. Anything else must be listed in
:data:`NO_WRITER_YET` with the reason, so an unwritten table is a decision
somebody recorded rather than a leftover nobody noticed.

Limit, stated rather than hidden: this is a source scan. It proves a writer
EXISTS, not that it runs — ``parliament_source_documents``' writer is behind
``PARLIAMENT_PIPELINE_ENABLED`` and passes here on the strength of the code
alone. It also cannot see a table written by something outside this repo.
"""

from __future__ import annotations

import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_MODELS = _REPO / "backend" / "models.py"
_SKIP_PARTS = {"tests", "venv", ".venv", ".venv313", "site-packages", "node_modules"}

# Models with no writer in this repo, each with the reason it is allowed to
# stay. Both hold 0 rows in production (pg_dump clone, 2026-09-26) and are
# read by user-facing code that expects a writer that was never built.
NO_WRITER_YET = {
    "Annotation": (
        "user annotations on budget lines; read via relationships on "
        "BudgetLine/User, no create endpoint exists — reported on #137"
    ),
    "DataAlert": (
        "per-user data alerts; routers/user_features.py lists, marks read "
        "and deletes them, nothing creates one — reported on #137"
    ),
}


def _models() -> dict:
    """``{class name: table name}`` for every declarative model."""
    tree = ast.parse(_MODELS.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(getattr(b, "id", None) == "Base" for b in node.bases):
            continue
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and getattr(stmt.targets[0], "id", None) == "__tablename__"
            ):
                out[node.name] = stmt.value.value
    return out


def _name(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _written_models(models: dict) -> dict:
    """``{class name: first file that writes it}``."""
    written: dict = {}
    sources = [
        p
        for top in ("backend", "etl", "scripts")
        for p in (_REPO / top).rglob("*.py")
        if not (_SKIP_PARTS & set(p.relative_to(_REPO).parts))
        and p != _MODELS
        and not p.name.startswith("conftest")
    ]
    for path in sources:
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(_REPO))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = _name(node.func)
            # X(...)
            if called in models:
                written.setdefault(called, rel)
            # insert(X) / pg_insert(X) / bulk_insert_mappings(X, ...)
            if called in {"insert", "pg_insert", "sqlite_insert", "bulk_insert_mappings"} and node.args:
                target = _name(node.args[0])
                if target in models:
                    written.setdefault(target, rel)
            # X.__table__.insert()
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "insert"
                and isinstance(f.value, ast.Attribute)
                and f.value.attr == "__table__"
                and _name(f.value.value) in models
            ):
                written.setdefault(_name(f.value.value), rel)
        upper = src.upper()
        for cls, table in models.items():
            if f"INSERT INTO {table}".upper() in upper or f"INSERT INTO PUBLIC.{table}".upper() in upper:
                written.setdefault(cls, rel)
    return written


def test_every_model_has_a_writer_or_a_recorded_reason():
    models = _models()
    written = _written_models(models)
    unwritten = sorted(m for m in models if m not in written and m not in NO_WRITER_YET)
    assert unwritten == [], (
        f"model(s) {unwritten} have no writer anywhere in backend/, etl/ or "
        "scripts/. Build the writer, drop the table (with a migration), or "
        "add it to NO_WRITER_YET with the reason."
    )


def test_the_allowlist_is_not_stale():
    """An entry that gained a writer, or lost its model, must leave the list."""
    models = _models()
    written = _written_models(models)
    assert set(NO_WRITER_YET) <= set(models), "allowlisted model no longer exists"
    assert not (set(NO_WRITER_YET) & set(written)), (
        f"{sorted(set(NO_WRITER_YET) & set(written))} now have a writer — "
        "remove them from NO_WRITER_YET"
    )


def test_the_scan_sees_each_write_shape():
    """Positive control, one per write shape the scan claims to recognise.

    If any of these went unseen the main test could pass by having looked at
    nothing. Receipts: ``Loan(`` in ``seeding/domains/pending_bills/writer.py``;
    ``PovertyIndex.__table__.insert()`` in ``seeding/domains/national_gdp``;
    ``ParliamentSourceDocument(`` in ``etl/parliament_pipeline.py``.
    """
    written = _written_models(_models())
    assert "Loan" in written
    assert written.get("PovertyIndex", "").startswith("backend/seeding/domains/national_gdp")
    assert written.get("ParliamentSourceDocument") == "etl/parliament_pipeline.py"

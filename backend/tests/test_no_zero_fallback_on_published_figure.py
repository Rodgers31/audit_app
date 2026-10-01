"""No Python module may publish ``0`` where a figure is absent — the Python half
of ``local/no-zero-fallback-on-published-figure``.

A zero is a claim. ``"total_missing_funds": 0`` says the counties are missing
no money; it does not say "we have no figure". Commit 7b5d366 made that rule a
build gate — as an ESLint rule, so it bound the frontend and nothing else.
Issue #207 is the proof of what that left open. ``apis/county_analytics_api.py``
served::

    "total_counties": 47,
    "total_county_budgets": summary.get("total_county_budgets", 0),
    "total_missing_funds": summary.get("total_missing_funds", 0),
    "average_financial_health": summary.get("average_financial_health", 0),

and the file it reads carries no ``analytics_summary`` at all, so all three
were zero on every call. The ESLint rule could not see a ``.py`` file; nothing
else was looking.

THE RULE. A zero fallback may not be the value that is published. Three
fallback shapes, each optionally wrapped in ``float``/``int``/``round``/
``abs``/``Decimal``:

* ``mapping.get("key", 0)``
* ``getattr(obj, "key", 0)``
* ``value or 0``

Two publishing positions:

* the value of a string-keyed entry in a dict literal — the response payload,
  a record handed to a writer;
* a keyword argument — ``CountySummary(loans_received=...)``, a model built
  for the response.

and only where the published key OR the field it reads names a figure. The
vocabulary is the ESLint rule's ``PUBLISHED_FIELD`` list, plus ``funds``,
``loan(s)``, ``budgets``, ``average``, ``mean``, ``median``, ``score`` and
``health``. Those were added because ESLint's list does not contain
``average_financial_health``, one of the three sites this gate exists for.

The fix is the shape ``/budget/national`` already uses: publish ``None`` and a
reason (``budget_split_absent_reason``), so a reader can tell "measured, and it
was zero" from "not measured".

WHAT THIS CANNOT SEE — stated so that a green run does not imply more:

* Two steps. ``x = row.amount or 0`` on one line and ``{"amount": x}`` on the
  next is the same defect, and only the second line is a publishing position.
* Reducers. ``sum(float(b.amount or 0) for b in rows)`` turns a missing row
  into a partial total. That is a real defect, but a different one (a total
  that is quietly incomplete), and it has a different fix.
* ``a / b if b else 0`` — a divide-by-zero guard that publishes 0%. Measured
  on this tree it mixes a real defect with ``len(x) if x else 0`` counts, and
  the shape cannot tell them apart.
* ``return value or 0``, function defaults, and model field defaults
  (``missing_funds: float = 0``).
* Any figure whose key and source are both outside the vocabulary.

ESCAPE HATCH, as for every guard beside this one: a zero that really is
correct gets a written reason. Put

    # zero-fallback-ok: <why zero is the true value here>

on the line the fallback opens, or the line above it.

SCOPE is the whole tree, minus the written exclusions in
``tests/_repo_tree.py`` (issue #206).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests._repo_tree import REPO_ROOT, python_modules, rel as _rel

SUPPRESSION = "zero-fallback-ok:"

# ``frontend/eslint-rules/no-zero-fallback-on-published-figure.js``
# PUBLISHED_FIELD, plus the additions named in the module docstring.
PUBLISHED_FIELD = re.compile(
    r"(^|_)("
    r"amount|amounts|budget|budgets|revenue|spending|spend|spent|allocated|"
    r"allocation|borrowing|debt|debt_service|cost|ratio|rate|pct|percentage|"
    r"share|total|count|findings|flagged|questioned|outstanding|principal|"
    r"population|gdp"
    r"|funds|loan|loans|average|mean|median|score|health"
    r")($|_)",
    re.IGNORECASE,
)

# Wrapping a fallback in a coercion does not change what it publishes.
COERCIONS = ("float", "int", "round", "abs", "Decimal")


def _snake(name: str) -> str:
    """camelCase -> snake_case, as the ESLint rule's normaliseFieldName does."""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()


def _names_a_figure(name: str | None) -> bool:
    if not name or name.startswith("_"):
        return False
    return bool(PUBLISHED_FIELD.search(_snake(name)))


def _is_zero(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and type(node.value) in (int, float)  # not False, which == 0
        and node.value == 0
    )


def _unwrap(node: ast.AST) -> ast.AST:
    while (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in COERCIONS
        and node.args
    ):
        node = node.args[0]
    return node


def _field_of(node: ast.AST) -> str | None:
    """The field a value is read from: ``r.x``, ``x``, ``d["x"]``, ``d.get("x")``."""
    node = _unwrap(node)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return node.slice.value if isinstance(node.slice.value, str) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def _zero_fallback(value: ast.AST) -> tuple[str | None, str] | None:
    """``(source field, shape)`` if ``value`` falls back to zero, else None."""
    node = _unwrap(value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 2
        and _is_zero(node.args[1])
    ):
        key = node.args[0]
        field = key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
        return field, ".get(key, 0)"
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) == 3
        and _is_zero(node.args[2])
    ):
        attr = node.args[1]
        field = attr.value if isinstance(attr, ast.Constant) and isinstance(attr.value, str) else None
        return field, "getattr(obj, key, 0)"
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and _is_zero(node.values[-1]):
        return _field_of(node.values[-2]), "... or 0"
    return None


def _suppressed(lines: list[str], node: ast.AST) -> bool:
    """True if a ``zero-fallback-ok:`` comment WITH A REASON covers node."""
    start = max(1, node.lineno - 1)
    end = getattr(node, "end_lineno", None) or node.lineno
    for lineno in range(start, end + 1):
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        if SUPPRESSION in line and line.split(SUPPRESSION, 1)[1].strip():
            return True
    return False


def find_zero_fallbacks(source: str, where: str = "<source>") -> list[str]:
    """Every published zero fallback in ``source``, one line per site.

    Empty list means clean. The tests below are thin wrappers around this —
    over the real tree, over the #207 payload, and over code that must stay
    legal.
    """
    tree = ast.parse(source, filename=where)
    lines = source.splitlines()
    published: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    published.append((key.value, value))
        elif isinstance(node, ast.Call):
            published.extend((kw.arg, kw.value) for kw in node.keywords if kw.arg)

    findings = []
    for label, value in published:
        hit = _zero_fallback(value)
        if hit is None:
            continue
        field, shape = hit
        if not (_names_a_figure(label) or _names_a_figure(field)):
            continue
        if _suppressed(lines, value):
            continue
        text = lines[value.lineno - 1].strip()
        if len(text) > 90:
            text = text[:87] + "..."
        findings.append(
            f"{where}:{value.lineno}:{value.col_offset}: {label!r} <- "
            f"{shape} [{field}]: {text}"
        )
    return sorted(set(findings))


SCANNED_MODULES = python_modules()

# Modules that carry this defect and are NOT this change's to fix. Each entry
# is a ratchet, not a pardon: the count is pinned, so adding a site fails, and
# ``test_quarantined_modules_still_carry_their_debt`` fails if a site is fixed
# without the count coming down. Nothing may be added here without an issue
# that owns it. Every site is listed in that issue.
QUARANTINE_ISSUE = "#240"
QUARANTINE: dict[str, int] = {
    "main_comprehensive.py": 2,
    "main_enterprise.py": 2,
}


def test_the_sweep_is_not_empty():
    scanned = {_rel(m) for m in SCANNED_MODULES}
    assert "backend/main.py" in scanned, "the sweep does not reach the shipping API"
    # apis/county_analytics_api.py, the #207 file, was withdrawn with its
    # routes (#278); the sweep must still reach the apis/ layer it lived in.
    assert any(p.startswith("apis/") for p in scanned), (
        "the sweep misses apis/, where the #207 fallbacks lived"
    )


def test_the_detector_catches_the_payload_it_was_written_for():
    """Positive control: ``apis/county_analytics_api.py`` as it stood (#207)."""
    known_bad = '''
summary = county_data.get("analytics_summary", {})
payload = {
    "total_counties": 47,
    "total_county_budgets": summary.get("total_county_budgets", 0),
    "total_missing_funds": summary.get("total_missing_funds", 0),
    "average_financial_health": summary.get("average_financial_health", 0),
}
row = CountySummary(loans_received=data.get("loans_received", 0))
'''
    findings = find_zero_fallbacks(known_bad, "known_bad.py")
    blob = "\n".join(findings)
    assert len(findings) == 4, findings
    for label in (
        "total_county_budgets",
        "total_missing_funds",
        # not in the ESLint rule's vocabulary — the reason for the additions
        "average_financial_health",
        "loans_received",
    ):
        assert f"'{label}'" in blob, f"{label} slipped through: {findings}"


def test_every_fallback_shape_and_position_is_seen():
    shapes = '''
out = {
    "principal": float(loan.principal or 0),
    "outstanding": round(getattr(loan, "outstanding", 0.0), 2),
    "totalBudget": budget_2025 or 0,
    "published_as": row.get("amount_kes", 0),
}
record = Model(total_pending=total_val or 0, gdp_value=int(gdp or 0))
'''
    findings = find_zero_fallbacks(shapes, "shapes.py")
    assert len(findings) == 6, findings

    # The rule reads the published key OR the source field: renaming one of
    # them does not get past it.
    renamed_key = 'x = {"field_a": row.get("allocated_amount", 0)}'
    renamed_source = 'x = {"allocated_amount": row.get("field_a", 0)}'
    assert find_zero_fallbacks(renamed_key, "a.py")
    assert find_zero_fallbacks(renamed_source, "b.py")

    # An empty suppression buys nothing.
    unreasoned = 'x = {"total": d.get("total", 0)}  # zero-fallback-ok:'
    assert find_zero_fallbacks(unreasoned, "c.py"), "an empty suppression bought silence"


def test_the_detector_leaves_absence_and_machinery_alone():
    """Negative control. These publish no zero, or no figure."""
    legal = '''
out = {
    "total": summary.get("total"),
    "total_absent_reason": None if "total" in summary else "not_in_source",
    "principal": float(loan.principal) if loan.principal is not None else None,
    "retries": opts.get("retries", 0),
    "offset": params.get("offset", 0),
    "page": page or 0,
    "is_flagged": row.get("flagged", False),
    "label": row.get("amount_label", ""),
    "total_rows": 1 + 1,
}
running = sum(float(b.amount or 0) for b in rows)
total = row.amount or 0
call(timeout=cfg.get("timeout", 0), _private_total=x or 0)
'''
    assert not find_zero_fallbacks(legal, "legal.py"), find_zero_fallbacks(legal, "legal.py")

    signed = (
        "x = {\n"
        "    # zero-fallback-ok: a Counter; an agency with no documents has 0\n"
        '    "document_count": by_agency.get(agency, 0),\n'
        "}\n"
    )
    assert not find_zero_fallbacks(signed, "signed.py"), "a written reason must be honoured"


@pytest.mark.parametrize(
    "relative_path,expected",
    sorted(QUARANTINE.items()),
    ids=sorted(QUARANTINE),
)
def test_quarantined_modules_still_carry_their_debt(relative_path: str, expected: int):
    """The reverse ratchet. A quarantine that outlives its debt is a lie."""
    module = REPO_ROOT / relative_path
    if not module.is_file():
        pytest.fail(f"{relative_path} is gone but still quarantined. Delete its entry.")
    findings = find_zero_fallbacks(module.read_text(encoding="utf-8"), relative_path)
    assert len(findings) == expected, "\n".join(
        [
            f"{relative_path} was quarantined under {QUARANTINE_ISSUE} with "
            f"{expected} site(s) and now has {len(findings)}.",
            "  If you fixed one, lower the count (or delete the entry at 0). "
            "If you added one, do not.",
            *findings,
        ]
    )


@pytest.mark.parametrize(
    "module",
    [m for m in SCANNED_MODULES if _rel(m) not in QUARANTINE],
    ids=[_rel(m) for m in SCANNED_MODULES if _rel(m) not in QUARANTINE],
)
def test_no_module_publishes_a_zero_for_an_absent_figure(module: Path):
    findings = find_zero_fallbacks(module.read_text(encoding="utf-8"), _rel(module))
    assert not findings, "\n".join(
        [
            "a zero published where the figure is absent — publish None and a "
            "reason, as /budget/national does with budget_split_absent_reason:",
            *findings,
        ]
    )

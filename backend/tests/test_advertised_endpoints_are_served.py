"""A module may not advertise an HTTP endpoint that nothing in this repo serves.

Issue #196 §B. ``extractors/government/comprehensive_government_extractor.py``
closes every run by publishing this alongside the counts it actually made::

    "api_integration": {
        "ready_for_ui": True,
        "endpoints_available": [
            "/counties/{name} - Individual county data",
            "/audit/queries - County audit queries",
            "/national/issues - National government issues",
            "/national/ministries - Ministry performance",
            "/national/debt - National debt analysis",
            "/analytics/summary - Overall transparency metrics",
        ],
    },

``/national/issues``, ``/national/ministries`` and ``/national/debt`` were the
three routes PR #191 deleted when it withdrew the six methods that typed in the
national debt. The extractor kept advertising them. The other three resolve:
``/counties/{county_name}`` at ``apis/modernized_api.py:228``,
``/audit/queries`` at ``apis/modernized_api.py:286``, ``/analytics/summary`` at
``apis/county_analytics_api.py:371``.

WHY THIS NEEDS A RULE OF ITS OWN. #195 removed the ``coverage_analysis`` block
from the same file — "Complete - All 47 counties covered", ``transparency_score:
95`` — and the figure guard caught the score because ``transparency_score`` is
on its list of measured quantities. Nothing caught the sentence beside it, and
nothing catches this: a path is a string, not a figure, and it names no county.
The three guards this one sits beside would all stay green on a module
advertising a hundred routes that do not exist.

The defect is the same one the chain has been withdrawing, in its plainest
form: a statement published about the world that nobody checked. The
difference here is that it is trivially checkable — either a route exists or it
does not — and a check that cheap has no excuse for being absent.

THE RULE. Every string under a key containing ``endpoint`` that begins with
``/`` names a path. That path, with its parameters flattened, must match a
route some module in this repo registers with a FastAPI/Flask-style decorator
(``@app.get("/x")``, ``@router.post("/y")``). Text after the path is free —
these entries are ``"/path - description"`` — and only the leading token is
read.

PARAMETER NAMES ARE NOT PART OF THE PATH. ``/counties/{name}`` is served by
``@app.get("/counties/{county_name}")``. Both flatten to ``/counties/{}``. A
rule that compared parameter names would report a defect where the only
difference is what the author called the variable.

WHAT IS NOT CHECKED, deliberately. ``ready_for_ui: True`` in the block above is
a literal that cannot become False whatever the run found, and it is the last
of the self-assessment #195 was withdrawing. It goes with the block, but there
is no rule here for it: a rule barring ``True`` under keys like ``ready_*`` or
``is_*`` would have to distinguish a self-assessment from an ordinary
configuration flag, and it cannot, so it would be a vocabulary that rots. This
guard checks the one claim in that block that is mechanically decidable. If
somebody restores ``ready_for_ui: True`` on its own, nothing here will catch
it, and saying so is better than pretending otherwise.

ESCAPE HATCH, following the three guards beside this file: a suppression must
carry a written reason. Put

    # endpoint-ok: <why this path need not resolve here>

on the line the string sits on, or the line above it. A path served by another
service is a legitimate reason; writing it down is the point.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where a route may be REGISTERED. Wider than where advertisements are read,
# because ``backend/main.py`` serves most of what ships.
ROUTE_ROOTS = (
    REPO_ROOT / "apis",
    REPO_ROOT / "analysis",
    REPO_ROOT / "extractors",
    REPO_ROOT / "backend",
)
# Where an advertisement may be MADE — the three roots the sibling guards scan.
SCANNED_ROOTS = (
    REPO_ROOT / "apis",
    REPO_ROOT / "analysis",
    REPO_ROOT / "extractors",
)

SUPPRESSION = "endpoint-ok:"

HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "route", "api_route"}
)

# The leading path token of an advertisement string: "/national/debt - blah".
LEADING_PATH = re.compile(r"^(/[A-Za-z0-9_\-{}/.]*)")

EXCLUDED_DIRS = frozenset({".venv", ".venv313", "node_modules", "site-packages", "__pycache__"})


def flatten(path: str) -> str:
    """``/counties/{county_name}`` and ``/counties/{name}`` both to ``/counties/{}``."""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/")) or "/"


def _modules(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        m for m in root.rglob("*.py") if not (EXCLUDED_DIRS & set(m.parts))
    )


def _parse(module: Path) -> ast.AST | None:
    try:
        return ast.parse(module.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError):
        return None


def find_registered_routes(source: str, where: str = "<source>") -> set[str]:
    """Flattened paths registered by decorator in ``source``."""
    tree = ast.parse(source, filename=where)
    routes: set[str] = set()
    for node in ast.walk(tree):
        for decorator in getattr(node, "decorator_list", []):
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS):
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if first.value.startswith("/"):
                    routes.add(flatten(first.value))
    return routes


def _suppressed(source_lines: list[str], node: ast.AST) -> bool:
    """True if an ``endpoint-ok:`` comment WITH A REASON covers node."""
    start = max(1, getattr(node, "lineno", 1) - 1)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    for lineno in range(start, end + 1):
        line = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
        if SUPPRESSION in line:
            reason = line.split(SUPPRESSION, 1)[1].strip()
            if reason:
                return True
    return False


def find_advertised_paths(source: str, where: str = "<source>") -> list[tuple[str, int]]:
    """Every ``(path, lineno)`` advertised under an ``endpoint``-ish key."""
    tree = ast.parse(source, filename=where)
    lines = source.splitlines()
    advertised: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if "endpoint" not in key.value.lower():
                continue
            elements = (
                value.elts if isinstance(value, (ast.List, ast.Tuple, ast.Set)) else [value]
            )
            for element in elements:
                if not (
                    isinstance(element, ast.Constant) and isinstance(element.value, str)
                ):
                    continue
                match = LEADING_PATH.match(element.value.strip())
                if not match or _suppressed(lines, element):
                    continue
                advertised.append((match.group(1), element.lineno))
    return advertised


def find_unserved_advertisements(
    source: str, served: set[str], where: str = "<source>"
) -> list[str]:
    """Every advertised path in ``source`` that ``served`` does not cover.

    This is the detector; the tests below are thin wrappers around it — over
    the real tree, over the block it was written for, and over what must stay
    legal.
    """
    findings: list[str] = []
    for path, lineno in find_advertised_paths(source, where):
        if flatten(path) not in served:
            findings.append(
                f"{where}:{lineno}: advertises {path!r}, which no module in this "
                f"repo registers. An endpoint list that outlives its endpoints "
                f"is a claim about a service that will not answer."
            )
    return findings


SERVED_ROUTES: set[str] = set()
ROUTE_SOURCE: dict[str, str] = {}
for _root in ROUTE_ROOTS:
    for _module in _modules(_root):
        _tree = _parse(_module)
        if _tree is None:
            continue
        try:
            _found = find_registered_routes(
                _module.read_text(encoding="utf-8", errors="ignore"),
                _module.as_posix(),
            )
        except (SyntaxError, ValueError):
            continue
        for _route in _found:
            SERVED_ROUTES.add(_route)
            ROUTE_SOURCE.setdefault(_route, _module.relative_to(REPO_ROOT).as_posix())

SCANNED_MODULES = [m for root in SCANNED_ROOTS for m in _modules(root)]


def _rel(module: Path) -> str:
    return module.relative_to(REPO_ROOT).as_posix()


def test_the_route_table_is_populated():
    """Anti-vacuity, and it is the whole ballgame.

    If the route scan returns nothing, every advertised path is "unserved" and
    the sweep below fails loudly — which is safe. The dangerous direction is
    the other one: a route table that silently swallowed everything would make
    every advertisement look served. Neither may pass unnoticed, so pin both
    the size of the table and one route we know by name.
    """
    surviving = [root for root in ROUTE_ROOTS if root.is_dir()]
    if not surviving:
        pytest.skip("every route root has been removed")
    assert len(SERVED_ROUTES) > 20, (
        f"only {len(SERVED_ROUTES)} routes found across "
        f"{', '.join(r.name for r in surviving)} — the scan is not reading "
        f"decorators any more, and every advertisement would read as broken"
    )
    assert "/audit/queries" in SERVED_ROUTES, (
        "a route this repo demonstrably serves is missing from the table"
    )


def test_the_detector_catches_the_payload_it_was_written_for():
    """Positive control. Proves a green run below means clean, not blind.

    This is the block withdrawn from
    ``extractors/government/comprehensive_government_extractor.py:472-482``,
    checked against the routes the repo actually registers today.
    """
    known_bad = '''
results = {
    "api_integration": {
        "ready_for_ui": True,
        "endpoints_available": [
            "/counties/{name} - Individual county data",
            "/audit/queries - County audit queries",
            "/national/issues - National government issues",
            "/national/ministries - Ministry performance",
            "/national/debt - National debt analysis",
            "/analytics/summary - Overall transparency metrics",
        ],
    },
}
'''
    findings = find_unserved_advertisements(known_bad, SERVED_ROUTES, "known_bad.py")
    blob = "\n".join(findings)
    for gone in ("/national/issues", "/national/ministries", "/national/debt"):
        assert gone in blob, f"{gone} was deleted by #191 and must be flagged: {findings}"
    for alive in ("/counties/{name}", "/audit/queries", "/analytics/summary"):
        assert alive not in blob, (
            f"{alive} does resolve today and must not be flagged: {findings}"
        )
    assert len(findings) == 3, f"expected exactly three findings, got: {findings}"

    # An empty suppression buys nothing.
    unreasoned = '{"endpoints": ["/national/debt"]}  # endpoint-ok:'
    assert find_unserved_advertisements(unreasoned, SERVED_ROUTES, "u.py"), (
        "an empty suppression bought silence for free"
    )


def test_the_detector_leaves_served_paths_and_prose_alone():
    """Negative control. Parameter names and free text must not matter."""
    served = {"/counties/{}", "/audit/queries", "/reports/{}/pages/{}"}

    # The parameter is named differently at each end; the path is the same.
    legal = '''
info = {
    "endpoints_available": [
        "/counties/{name} - by county",
        "/counties/{county_name}",
        "/audit/queries - every query",
        "/reports/{report_id}/pages/{page_no} - one page",
    ],
}
'''
    assert not find_unserved_advertisements(legal, served, "legal.py"), (
        find_unserved_advertisements(legal, served, "legal.py")
    )

    # A key with no "endpoint" in it is not an advertisement, and a string that
    # does not open with a path is not a path.
    quiet = '''
config = {"docs": ["see /national/debt in the old API"], "prefix": "/national"}
notes = {"endpoint_notes": ["retired in #191"]}
'''
    assert not find_unserved_advertisements(quiet, served, "quiet.py"), (
        find_unserved_advertisements(quiet, served, "quiet.py")
    )

    # A signed suppression is honoured.
    signed = (
        'x = {"endpoints": [\n'
        '    "/external/thing",  # endpoint-ok: served by the county portal, not us\n'
        "]}\n"
    )
    assert not find_unserved_advertisements(signed, served, "signed.py"), (
        "a suppression with a written reason must be honoured"
    )


def test_the_route_scanner_reads_decorators():
    """The route table must come from decorators, not from a text scan.

    A path mentioned in a docstring is not a route, and a route registered on a
    router rather than the app is.
    """
    source = '''
"""This module used to serve /national/debt."""

@app.get("/counties/{county_name}")
def county(county_name: str): ...

@router.post("/audit/queries")
def queries(): ...

@app.api_route("/health", methods=["GET"])
def health(): ...
'''
    routes = find_registered_routes(source, "routes.py")
    assert routes == {"/counties/{}", "/audit/queries", "/health"}, routes
    assert "/national/debt" not in routes, "a docstring mention was read as a route"


@pytest.mark.skipif(not SCANNED_MODULES, reason="the scanned roots hold no modules")
@pytest.mark.parametrize(
    "module",
    SCANNED_MODULES,
    ids=[_rel(m) for m in SCANNED_MODULES] or ["none"],
)
def test_no_module_advertises_an_endpoint_nobody_serves(module: Path):
    source = module.read_text(encoding="utf-8", errors="ignore")
    try:
        findings = find_unserved_advertisements(source, SERVED_ROUTES, _rel(module))
    except (SyntaxError, ValueError) as exc:
        pytest.skip(f"{_rel(module)} does not parse: {exc}")
    assert not findings, "\n".join(["endpoints advertised but not served:", *findings])

"""No module that serves HTTP may read ``enhanced_county_data.json``, directly
or through a module it imports, except through a gate that withholds what the
file models.

WHAT THIS WAS WRITTEN FOR. ``apis/county_analytics_api.py`` served::

    GET /audit/missing-funds
        "worst_offenders": county_missing_funds[:10],
        "summary": f"Total of {total_missing:,.0f} KES missing across 47 counties"

ten named county governments ranked by how much public money they had lost,
and a national total. Every ``missing_funds`` in that file is exactly 2% of
``budget_2025``, which is itself Census population x KSh 4,500 x a hand-set
"economic factor" (``test_the_premise_*`` below pins all of it). So "worst
offenders" was a list of the ten most populous, most urban counties, published
as the ten that lost the most money. Beside it, ``GET /rankings/{metric}``
ranked the 47 by seven fields and every one of them was modelled, including
``debt-ratio``, which is 15.0 for all 47, so its "ranking" was file order.
That is the #183 defect: a statement of fact about named public bodies with
nothing behind it, actionable under the Defamation Act (Cap 36). It survived
because ``apis/`` is not deployed, and none of the three guards beside this file
could see it: the county-selection guard reads hand-typed literals, the hash
guard reads ``hash()``/``random``/clocks, and the zero gate reads ``or 0``.

WHY THE RULE IS ABOUT THE FILE AND NOT THE FIELD NAMES. The obvious guard is
"no ``sorted``/``sum`` over a field in ``bootstrap._MODELLED_COUNTY_METRICS``".
It cannot be made precise, for four reasons that each show up in the code this
was written for:

1. The names are not what is modelled; the FILE is. ``pending_bills``,
   ``budget_2025`` and ``debt_outstanding`` are also the names measured
   Controller of Budget and Treasury BROP figures travel under, and ranking
   those is legitimate. A name-keyed rule either flags the real ones or
   exempts them by path, and an exemption by path is a blind spot.
2. That list is bootstrap's, and it names what BOOTSTRAP writes. The file
   models more than that: ``audit_rating``, ``financial_health_score`` and
   ``budget_execution_rate`` take three values that follow ``infrastructure_level``
   exactly, ``per_capita_budget`` is 4,500 x ``economic_factor``, and
   ``debt_to_budget_ratio`` is a constant. A guard keyed on the list would have
   passed ``/rankings/health-score``, ``/rankings/execution-rate`` and the
   named top-five lists in ``/analytics/summary``.
3. The field reaches the sort through a value chosen at request time:
   ``field = metric_mapping[metric]; sorted(..., key=lambda x: x[1][field])``.
   No literal sits at the sort. Seeing it needs dataflow, not a pattern.
4. The total was an accumulator loop, ``total_missing += missing``, with no
   ``sum()`` call to find.

So this guard moves to the boundary it CAN decide exactly: whether a module
that registers a route can reach the file at all. That is broader than the
defect (a route reading only the Census population would be flagged too, and
would need a written reason) and it is still narrower than "nothing modelled
is ever published", for the reasons under BLIND SPOTS.

THE RULE. A module "reaches" the file if it holds a string constant naming
``enhanced_county_data`` (docstrings excluded, comments are not constants), or
imports a repo module that reaches it. A module that registers a route with a
decorator (``@app.get``, ``@router.post``, ``@bp.route`` ...) may not reach it,
except through a module in ``GATES``, where the walk stops. Each gate names the
tests that prove it withholds what the file models.

BLIND SPOTS, in writing:

* A filename assembled at runtime (``"enhanced_county" + "_data.json"``, or read
  from config) is not a constant, so it is not seen.
* Data laundered through the database. ``backend/bootstrap.py`` writes this
  file into tables; after that, a route reads a table, not the file. That hop
  is the gates' job, and ``GATES`` names the tests that hold them to it.
* An import this resolver cannot map to a file: ``importlib``, ``__import__``,
  ``sys.path`` manipulation to an unusual root, or a star-import of a package
  whose ``__init__`` re-exports from elsewhere is followed only as far as the
  ``__init__`` itself.
* Anything outside Python. A committed document can publish the same ranking
  (``docs/COUNTY_API_README.md`` did, with Mombasa at number one) and no
  source scan of ``.py`` files will see it.

ESCAPE HATCH. ``KNOWN_OFFENDERS`` holds a route module that still reaches the
file, with the reason it has not been fixed. Each entry must still offend: once
the route is fixed, its entry is a stale exemption that would cover whatever
lands at that path next, and the suite says so.
"""

from __future__ import annotations

import ast
import json
import os
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELLED_FILE_STEM = "enhanced_county_data"
MODELLED_FILE = REPO_ROOT / "backend" / "data" / "reference" / "enhanced_county_data.json"

#: Directories that are not this repo's source. Pruned by name at any depth.
#: A virtualenv is recognised by its ``pyvenv.cfg``, whatever it is called.
ENVIRONMENT_DIR_NAMES = frozenset(
    {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
     ".ruff_cache", ".next", ".claude"}
)

#: This repo's source, skipped on purpose.
REPO_EXCLUSIONS = {
    "backend/tests": (
        "test modules register throwaway routes on test apps and name the file "
        "as a fixture; this guard carries its own known-bad payload as a "
        "positive control"
    ),
}

#: Modules a route may reach the file THROUGH. The walk stops here.
GATES: dict[str, dict] = {
    "backend/bootstrap.py": {
        "reason": (
            "reads the file into the database and withholds the fields it "
            "models: _MODELLED_COUNTY_METRICS never reaches entity.meta, and the "
            "modelled debt/pending-bills Loan rows are stamped with the dataset "
            "so the publication gate can refuse them"
        ),
        "proven_by": (
            "backend/tests/test_bootstrap_withholds_modelled_pending_bills.py",
            "backend/tests/test_stored_county_metrics_are_cleared.py",
        ),
    },
    "backend/services/publication_gate.py": {
        "reason": (
            "names the file only as the provenance stamp it REFUSES: "
            "loan_is_modelled_fixture() excludes bootstrap's modelled rows "
            "from county pending bills"
        ),
        "proven_by": (
            "backend/tests/test_bootstrap_withholds_modelled_pending_bills.py",
        ),
    },
}

#: Route modules that still reach the file, and why they are not fixed here.
KNOWN_OFFENDERS: dict[str, str] = {
    "apis/modernized_api.py": (
        "GET /counties/{county_name} returns the file's whole record for a named "
        "county (missing_funds and audit_rating included) and GET "
        "/counties/statistics totals its modelled budget and debt, both through "
        "apis/data_driven_analytics.py. Not deployed, and its data path "
        "(../data/county/enhanced_county_data.json) resolves to nothing today "
        "(issue #188), so it serves 503; it is one path edit from serving the "
        "model as fact. Withdraw those two routes and delete this entry"
    ),
}

HTTP_DECORATORS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "route", "api_route"}
)


# --------------------------------------------------------------------------
# the detector
# --------------------------------------------------------------------------


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def names_the_file(tree: ast.AST) -> bool:
    """A non-docstring string constant naming the modelled file."""
    docstrings = _docstring_ids(tree)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and MODELLED_FILE_STEM in node.value
        and id(node) not in docstrings
        for node in ast.walk(tree)
    )


def registers_a_route(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in HTTP_DECORATORS
                ):
                    return True
    return False


def _candidates(base: Path, dotted: str) -> list[Path]:
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return [base / "__init__.py"]
    target = base.joinpath(*parts)
    return [target.with_suffix(".py"), target / "__init__.py"]


def imported_files(module: Path, tree: ast.AST, root: Path) -> set[Path]:
    """Repo files ``module`` imports, resolved the way Python would find them.

    Absolute imports are tried against the importing module's own directory
    (a script run from there, as ``apis/modernized_api.py`` imports
    ``data_driven_analytics``), the repo root, and ``backend/`` (the backend's
    own import root). ``from a import b`` also tries ``a/b.py``, since ``b`` may
    be a submodule. Anything that does not resolve is third-party or stdlib.
    """
    bases = [module.parent, root, root / "backend"]
    found: set[Path] = set()
    for node in ast.walk(tree):
        names: list[tuple[list[Path], str]] = []
        if isinstance(node, ast.Import):
            names = [(bases, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = module.parent
                for _ in range(node.level - 1):
                    anchor = anchor.parent
                search = [anchor]
            else:
                search = bases
            head = node.module or ""
            names = [(search, head)]
            names += [(search, f"{head}.{alias.name}" if head else alias.name) for alias in node.names]
        for search, dotted in names:
            for base in search:
                for candidate in _candidates(base, dotted):
                    if candidate.is_file() and candidate != module:
                        found.add(candidate.resolve())
    return found


def python_modules(root: Path) -> list[Path]:
    """Every ``.py`` under ``root``, pruning environments and REPO_EXCLUSIONS."""
    root = root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d not in ENVIRONMENT_DIR_NAMES
            and not (here / d / "pyvenv.cfg").exists()
            and (here / d).relative_to(root).as_posix() not in REPO_EXCLUSIONS
        ]
        found.extend(here / f for f in filenames if f.endswith(".py"))
    return sorted(found)


class Graph:
    """Every module under ``root``: what it imports, whether it names the file,
    whether it serves a route."""

    def __init__(self, root: Path, modules: list[Path] | None = None):
        self.root = root.resolve()
        self.modules = modules if modules is not None else python_modules(self.root)
        self.imports: dict[Path, set[Path]] = {}
        self.names_file: set[Path] = set()
        self.routes: set[Path] = set()
        self.unparseable: list[str] = []
        for module in self.modules:
            try:
                tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            except (SyntaxError, UnicodeDecodeError) as exc:
                self.unparseable.append(f"{self.rel(module)}: {exc}")
                continue
            self.imports[module] = imported_files(module, tree, self.root)
            if names_the_file(tree):
                self.names_file.add(module)
            if registers_a_route(tree):
                self.routes.add(module)

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def chain_to_file(self, start: Path, gates: set[str]) -> list[str] | None:
        """The import chain from ``start`` to a module naming the file, or None.

        Breadth-first, so the chain reported is a shortest one. A gate is never
        entered: reaching the file through it is the sanctioned route.
        """
        start = start.resolve()
        parent: dict[Path, Path | None] = {start: None}
        queue = [start]
        while queue:
            current = queue.pop(0)
            if current in self.names_file:
                chain = []
                node: Path | None = current
                while node is not None:
                    chain.append(self.rel(node))
                    node = parent[node]
                return list(reversed(chain))
            for nxt in sorted(self.imports.get(current, ())):
                if nxt in parent or self.rel(nxt) in gates:
                    continue
                parent[nxt] = current
                queue.append(nxt)
        return None

    def offending_routes(self, gates: set[str]) -> dict[str, list[str]]:
        out = {}
        for module in sorted(self.routes):
            chain = self.chain_to_file(module, gates)
            if chain is not None:
                out[self.rel(module)] = chain
        return out


# --------------------------------------------------------------------------
# the premise: what the file is
# --------------------------------------------------------------------------


def _records() -> dict[str, dict]:
    return json.loads(MODELLED_FILE.read_text())["county_data"]


def test_the_premise_missing_funds_is_two_percent_of_a_modelled_budget():
    """Pins why "worst offenders" was false, not merely unsourced.

    Every county's ``missing_funds`` is 2% of its ``budget_2025``, and every
    ``budget_2025`` is population x 4,500 x ``economic_factor``. Ranking the 47
    by missing funds therefore ranks them by population and urbanisation. If
    this fails, the file has changed character: re-examine before trusting
    anything built on it, in either direction.
    """
    records = _records()
    assert len(records) == 47
    for name, r in records.items():
        assert r["missing_funds"] == pytest.approx(0.02 * r["budget_2025"], abs=1), name
        assert r["budget_2025"] == pytest.approx(
            r["population"] * 4500 * r["economic_factor"], abs=1
        ), name
        assert r["data_source"] == "realistic_estimate" and r["needs_verification"] is True, name

    by_missing = sorted(records, key=lambda n: records[n]["missing_funds"], reverse=True)
    by_budget = sorted(records, key=lambda n: records[n]["budget_2025"], reverse=True)
    assert by_missing == by_budget, "the 'worst offenders' order is the budget-model order"


def test_the_premise_the_file_models_more_than_bootstraps_list_names():
    """Pins reason 2 in the module docstring.

    The rankings withdrawn alongside /audit/missing-funds ran over fields that
    are not in ``_MODELLED_COUNTY_METRICS`` and are modelled all the same, so a
    guard keyed on that list would have passed them.
    """
    records = _records()
    assert {r["debt_to_budget_ratio"] for r in records.values()} == {15.0}
    assert {r["pending_bills_ratio"] for r in records.values()} == {8.0}
    for name, r in records.items():
        assert r["per_capita_budget"] == pytest.approx(4500 * r["economic_factor"]), name

    # audit_rating, financial_health_score and budget_execution_rate are read
    # off the same hand-set economic_factor that scales the budget. No auditor
    # issued these grades; the county's urbanisation coefficient did.
    def graded(factor: float) -> tuple:
        if factor >= 1.3:
            return ("A-", 85.0, 85.0)
        if factor >= 1.1:
            return ("B+", 80.0, 80.0)
        return ("B", 75.0, 75.0)

    for name, r in records.items():
        assert (
            r["audit_rating"], r["financial_health_score"], r["budget_execution_rate"]
        ) == graded(r["economic_factor"]), name
    assert Counter(r["audit_rating"] for r in records.values()) == {"B": 40, "B+": 3, "A-": 4}

    bootstrap = ast.parse((REPO_ROOT / "backend" / "bootstrap.py").read_text())
    listed = next(
        ast.literal_eval(node.value)
        for node in ast.walk(bootstrap)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_MODELLED_COUNTY_METRICS" for t in node.targets)
    )
    assert "missing_funds" in listed
    assert not {"audit_rating", "financial_health_score", "budget_execution_rate",
                "debt_to_budget_ratio", "per_capita_budget"} & set(listed)


# --------------------------------------------------------------------------
# controls: the detector on trees whose answer is known
# --------------------------------------------------------------------------

#: The route this guard was written for, as it stood before withdrawal.
WITHDRAWN_ROUTE = '''
import json
from fastapi import FastAPI

app = FastAPI()
with open("enhanced_county_data.json") as f:
    county_data = json.load(f)


@app.get("/audit/missing-funds")
async def get_missing_funds_analysis():
    counties = county_data.get("county_data", {})
    county_missing_funds = []
    total_missing = 0
    for county_name, data in counties.items():
        missing = data["missing_funds"]
        total_missing += missing
        county_missing_funds.append({"county": county_name, "missing_funds": missing})
    county_missing_funds.sort(key=lambda x: x["missing_funds"], reverse=True)
    return {
        "worst_offenders": county_missing_funds[:10],
        "summary": f"Total of {total_missing:,.0f} KES missing",
    }
'''


def _tree(tmp_path: Path, files: dict[str, str]) -> Graph:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return Graph(tmp_path)


def test_the_detector_catches_the_route_it_was_written_for(tmp_path):
    graph = _tree(tmp_path, {"apis/county_analytics_api.py": WITHDRAWN_ROUTE})
    assert graph.offending_routes(set()) == {
        "apis/county_analytics_api.py": ["apis/county_analytics_api.py"]
    }


def test_the_detector_follows_imports_to_the_reader(tmp_path):
    """The shape ``apis/modernized_api.py`` has: the route never names the file,
    its helper does. Sibling import, backend-rooted package import, and a
    relative import all reach it."""
    route = 'from fastapi import APIRouter\nrouter = APIRouter()\n{imp}\n\n@router.get("/x")\ndef x():\n    return helper()\n'
    reader = 'import json\nPATH = "../data/county/enhanced_county_data.json"\ndef helper():\n    return json.load(open(PATH))\n'
    graph = _tree(
        tmp_path,
        {
            "apis/route_a.py": route.format(imp="from analytics_helper import helper"),
            "apis/analytics_helper.py": reader,
            "backend/routers/route_b.py": route.format(imp="from services.county_reader import helper"),
            "backend/routers/__init__.py": "",
            "backend/services/__init__.py": "",
            "backend/services/county_reader.py": reader,
            "backend/routers/route_c.py": route.format(imp="from ..services.county_reader import helper"),
        },
    )
    assert graph.offending_routes(set()) == {
        "apis/route_a.py": ["apis/route_a.py", "apis/analytics_helper.py"],
        "backend/routers/route_b.py": ["backend/routers/route_b.py", "backend/services/county_reader.py"],
        "backend/routers/route_c.py": ["backend/routers/route_c.py", "backend/services/county_reader.py"],
    }


def test_the_detector_stops_at_a_gate_and_ignores_prose(tmp_path):
    graph = _tree(
        tmp_path,
        {
            # Reaches the file only through the gate: sanctioned.
            "backend/main.py": 'from fastapi import FastAPI\napp = FastAPI()\nfrom bootstrap import load\n\n@app.get("/")\ndef root():\n    return load()\n',
            "backend/bootstrap.py": 'PATH = "enhanced_county_data.json"\ndef load():\n    return {}\n',
            # Mentions it in a docstring and a comment only.
            "apis/prose.py": '"""Once read enhanced_county_data.json."""\nfrom fastapi import FastAPI\napp = FastAPI()\n# enhanced_county_data.json is gone\n\n@app.get("/")\ndef root():\n    """Not from enhanced_county_data.json."""\n    return {}\n',
            # Reads the file but serves nothing: a script, not a publisher.
            "tools/report.py": 'import json\nprint(json.load(open("enhanced_county_data.json")))\n',
        },
    )
    assert graph.offending_routes({"backend/bootstrap.py"}) == {}
    # And without the gate declared, main.py is caught — the gate is doing the work.
    assert graph.offending_routes(set()) == {
        "backend/main.py": ["backend/main.py", "backend/bootstrap.py"]
    }


# --------------------------------------------------------------------------
# the real tree
# --------------------------------------------------------------------------

GRAPH = Graph(REPO_ROOT)
OFFENDING = GRAPH.offending_routes(set(GATES))
ROUTE_MODULES = sorted(GRAPH.rel(m) for m in GRAPH.routes)


def test_the_sweep_is_not_vacuous():
    """An empty sweep must never read as a pass."""
    assert not GRAPH.unparseable, GRAPH.unparseable
    assert "backend/main.py" in ROUTE_MODULES, "route detection is blind to the shipping app"
    readers = {GRAPH.rel(m) for m in GRAPH.names_file}
    assert set(GATES) <= readers, "a gate no longer names the file; see test_every_gate_is_live"
    # The shipping app does reach the file, through bootstrap. If this stops
    # being true the gate list is protecting nothing and should be re-read.
    assert GRAPH.offending_routes(set()).get("backend/main.py"), (
        "backend/main.py no longer reaches the file even ungated — import "
        "resolution may have gone blind"
    )


@pytest.mark.parametrize("module", ROUTE_MODULES)
def test_no_route_reaches_the_modelled_file(module):
    if module in KNOWN_OFFENDERS:
        pytest.skip(f"known offender: {KNOWN_OFFENDERS[module]}")
    chain = OFFENDING.get(module)
    assert chain is None, (
        f"{module} serves HTTP and reaches {MODELLED_FILE_STEM}.json via "
        f"{' -> '.join(chain)}. Every field in that file except population is "
        "modelled (see test_the_premise_*); a route built on it publishes the "
        "model as fact about named counties. Read measured figures from the "
        "database through the publication gate, or serve nothing."
    )


@pytest.mark.parametrize("module", sorted(KNOWN_OFFENDERS))
def test_every_known_offender_still_offends(module):
    assert module in OFFENDING, (
        f"{module} no longer reaches the file — delete its KNOWN_OFFENDERS entry "
        "so it cannot cover whatever lands at that path next"
    )


@pytest.mark.parametrize("gate", sorted(GATES))
def test_every_gate_is_live(gate):
    path = REPO_ROOT / gate
    assert path.is_file(), f"gate {gate} no longer exists"
    assert path.resolve() in GRAPH.names_file, (
        f"gate {gate} no longer names the file — the exemption covers nothing"
    )
    entry = GATES[gate]
    assert entry["reason"].strip()
    for proof in entry["proven_by"]:
        assert (REPO_ROOT / proof).is_file(), f"{gate}'s proof {proof} is gone"

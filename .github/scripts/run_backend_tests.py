"""Run every core backend test with explicit ETL package ownership.

The repository ships two different ``etl`` packages and a root ``seeding``
stub. Test processes must choose the real package before importing the app.
Coverage is combined only after both disjoint cohorts have completed.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
LEGACY_ETL_TESTS = frozenset({
    "tests/test_audit_parser.py",
    "tests/test_batch9_legacy_etl_sessions.py",
    "tests/test_county_normalizer.py",
    "tests/test_county_pending_bills_one_source.py",
    "tests/test_etl.py",
    "tests/test_financial_absence_postgres.py",
    "tests/test_financial_absence_publication.py",
    "tests/test_knbs_parser_year_column.py",
    "tests/test_national_pending_bills_one_source.py",
})


def test_inventory():
    files = sorted(
        str(path.relative_to(BACKEND))
        for path in (BACKEND / "tests").rglob("*.py")
        if (path.name.startswith("test_") or path.name.endswith("_test.py"))
        and (BACKEND / "tests/integration") not in path.parents
    )
    if not files or not LEGACY_ETL_TESTS <= set(files):
        raise ValueError("Core test inventory is empty or a declared legacy file is missing")
    for name in files:
        tree = ast.parse((BACKEND / name).read_text(), filename=name)
        imports_etl = any(
            (isinstance(node, ast.ImportFrom) and node.module
             and (node.module == "etl" or node.module.startswith("etl.")))
            or (isinstance(node, ast.Import) and any(
                entry.name == "etl" or entry.name.startswith("etl.")
                for entry in node.names
            ))
            for node in ast.walk(tree)
        )
        if imports_etl and name not in LEGACY_ETL_TESTS:
            raise ValueError(f"Declare ETL ownership before running new importer: {name}")
    return {
        "backend": [name for name in files if name not in LEGACY_ETL_TESTS],
        "legacy": [name for name in files if name in LEGACY_ETL_TESTS],
    }


def owned_package_spec(name, directory):
    initializer = directory / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name, initializer, submodule_search_locations=[str(directory)]
    )
    if not initializer.is_file() or spec is None or spec.loader is None:
        raise ValueError(f"Package unavailable: {directory}")
    return spec


def bind_package(name, directory):
    if name in sys.modules or any(key.startswith(name + ".") for key in sys.modules):
        raise ValueError(f"Package {name} was imported before ownership was selected")
    spec = owned_package_spec(name, directory)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != (directory / "__init__.py").resolve():
        raise ValueError(f"Wrong package identity: {name}")


class CollectionReceipt:
    def __init__(self, cohort, files, output):
        self.cohort = cohort
        self.files = set(files)
        self.output = output

    def pytest_collection_finish(self, session):
        nodes = [item.nodeid for item in session.items]
        if not nodes:
            raise ValueError(f"No core tests collected in {self.cohort}")
        observed = {str(Path(item.path).relative_to(BACKEND)) for item in session.items}
        if not observed <= self.files:
            raise ValueError(f"Cross-cohort collection: {sorted(observed - self.files)}")
        identities = {
            name: str(Path(sys.modules[name].__file__).resolve())
            for name in ("etl", "seeding")
        }
        expected_etl = ROOT / "etl" if self.cohort == "legacy" else BACKEND / "etl"
        if identities != {
            "etl": str(expected_etl / "__init__.py"),
            "seeding": str(BACKEND / "seeding/__init__.py"),
        }:
            raise ValueError(f"Wrong package identities: {identities}")
        write_receipt(self.output, {
            "cohort": self.cohort,
            "scheduled_files": sorted(self.files),
            "collected_files": sorted(observed),
            "nodeids": nodes,
            "package_identities": identities,
        })


def write_receipt(path, fields):
    receipt = {
        "generated_by": str(Path(__file__).resolve().relative_to(ROOT)),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "target_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        **fields,
    }
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    if json.loads(path.read_text()) != receipt:
        raise ValueError(f"Receipt readback failed: {path}")


def descendant_environment(cohort, output):
    """Anchor inherited Python children without exposing the root seeding stub.

    sys.modules bindings do not cross process boundaries, and a child's cwd
    precedes PYTHONPATH. A dedicated startup module selects the same real
    package specs before the child's command can import either ambiguous name.
    Initializers run on normal import, after fixtures choose their own settings.
    """
    if cohort not in ("backend", "legacy"):
        raise ValueError("An explicit backend or legacy child owner is required")
    bootstrap = output / f"imports-{cohort}"
    bootstrap.mkdir(parents=True, exist_ok=True)
    source = f'''import importlib.util
from importlib.abc import MetaPathFinder
import os
import sys
try:
    spec = importlib.util.spec_from_file_location('_ci_package_owner', {str(Path(__file__).resolve())!r})
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    owners = {{'seeding': launcher.BACKEND / 'seeding',
              'etl': {'launcher.ROOT' if cohort == 'legacy' else 'launcher.BACKEND'} / 'etl'}}
    for name, directory in owners.items():
        launcher.owned_package_spec(name, directory)
    class PackageOwner(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in owners:
                return launcher.owned_package_spec(fullname, owners[fullname])
            return None
    sys.meta_path.insert(0, PackageOwner())
except BaseException:
    os.write(2, b'CI descendant package ownership failed\\n')
    os._exit(78)
'''
    path = bootstrap / "sitecustomize.py"
    path.write_text(source)
    if path.read_text() != source:
        raise ValueError("Descendant bootstrap readback failed")
    return str(bootstrap) + os.pathsep + str(BACKEND)


def run_cohort(cohort, output, collect_only=False):
    if os.environ.get("PYTEST_ADDOPTS"):
        raise ValueError("Ambient PYTEST_ADDOPTS cannot alter the complete core test gate")
    files = test_inventory()[cohort]
    sys.path.insert(0, str(BACKEND))
    bind_package("seeding", BACKEND / "seeding")
    bind_package("etl", ROOT / "etl" if cohort == "legacy" else BACKEND / "etl")
    os.environ["PYTHONPATH"] = descendant_environment(cohort, output)
    os.chdir(BACKEND)
    os.environ["COVERAGE_FILE"] = str(output / f".coverage.{cohort}")
    import pytest

    args = [*files, "-o", "addopts=", "--verbose", "--maxfail=5", "-m", "not slow"]
    if collect_only:
        args.append("--collect-only")
    else:
        args.extend(["--cov=.", "--cov-report="])
    return pytest.main(args, plugins=[CollectionReceipt(
        cohort, files, output / f"collection-{cohort}.json"
    )])


def validate_collection_receipt(receipt, cohort, files):
    if not isinstance(receipt, dict):
        raise ValueError("Invalid collection receipt schema")
    nodes = receipt.get("nodeids")
    collected = receipt.get("collected_files")
    valid_nodes = (isinstance(nodes, list) and bool(nodes)
                   and all(isinstance(node, str) and "::" in node for node in nodes))
    valid_files = (isinstance(collected, list) and bool(collected)
                   and all(isinstance(name, str) for name in collected))
    expected_etl = ROOT / "etl" if cohort == "legacy" else BACKEND / "etl"
    identities = {
        "etl": str(expected_etl / "__init__.py"),
        "seeding": str(BACKEND / "seeding/__init__.py"),
    }
    if (receipt.get("cohort") != cohort or receipt.get("scheduled_files") != files
            or receipt.get("generator_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or receipt.get("generated_by") != str(Path(__file__).resolve().relative_to(ROOT))
            or receipt.get("python_version") != sys.version
            or receipt.get("package_identities") != identities
            or not valid_nodes or not valid_files
            or len(nodes) != len(set(nodes))
            or collected != sorted(set(collected))
            or not set(collected) <= set(files)
            or {node.split("::", 1)[0] for node in nodes} != set(collected)):
        raise ValueError(f"Invalid cohort receipt: {cohort}")


def run_all(output, collect_only=False):
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").unlink(missing_ok=True)
    if os.environ.get("PYTEST_ADDOPTS"):
        raise ValueError("Ambient PYTEST_ADDOPTS cannot alter the complete core test gate")
    inventory = test_inventory()
    for name in ("backend", "legacy"):
        (output / f"collection-{name}.json").unlink(missing_ok=True)
        (output / f".coverage.{name}").unlink(missing_ok=True)
    results = {}
    for name in inventory:
        command = [sys.executable, str(Path(__file__).resolve()),
                   "--cohort", name, "--output-dir", str(output)]
        if collect_only:
            command.append("--collect-only")
        env = {**os.environ, "PYTHONPATH": str(BACKEND)}
        results[name] = subprocess.run(command, cwd=BACKEND, env=env, check=False).returncode
    receipts = {}
    for name in inventory:
        path = output / f"collection-{name}.json"
        if path.is_file():
            receipt = json.loads(path.read_text())
            validate_collection_receipt(receipt, name, inventory[name])
            receipts[name] = receipt
        else:
            results[name] = results[name] or 1
    if len(receipts) == 2:
        nodeids = [node for receipt in receipts.values() for node in receipt["nodeids"]]
        if len(nodeids) != len(set(nodeids)):
            raise ValueError("A core test was assigned to more than one cohort")
    coverage_rc = None
    if not collect_only:
        from coverage import CoverageData

        coverage_files = [output / f".coverage.{name}" for name in inventory]
        for path in coverage_files:
            if not path.is_file():
                raise ValueError(f"Missing cohort coverage: {path}")
            data = CoverageData(basename=str(path))
            data.read()
            if not data.measured_files():
                raise ValueError(f"Empty cohort coverage: {path}")
        env = {**os.environ, "COVERAGE_FILE": str(BACKEND / ".coverage")}
        subprocess.run([sys.executable, "-m", "coverage", "combine", "--keep",
                        *map(str, coverage_files)], cwd=BACKEND, env=env, check=True)
        coverage_rc = 0
        for command in (["xml"], ["html"], ["report"]):
            rc = subprocess.run([sys.executable, "-m", "coverage", *command],
                                cwd=BACKEND, env=env, check=False).returncode
            coverage_rc = coverage_rc or rc
    rc = 0 if all(value == 0 for value in results.values()) and not coverage_rc else 1
    write_receipt(output / "summary.json", {
        "mode": "collection" if collect_only else "execution",
        "cohort_results": results,
        "inventory": inventory,
        "collected_counts": {name: len(receipt["nodeids"])
                             for name, receipt in receipts.items()},
        "coverage_result": coverage_rc,
        "verdict": "PASSED" if rc == 0 else "FAILED",
    })
    return rc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=BACKEND / ".ci-test-results")
    parser.add_argument("--cohort", choices=("backend", "legacy"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    return (run_cohort(args.cohort, output, args.collect_only) if args.cohort
            else run_all(output, args.collect_only))


if __name__ == "__main__":
    raise SystemExit(main())

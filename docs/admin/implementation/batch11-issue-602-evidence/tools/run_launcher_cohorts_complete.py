"""Run one launcher cohort to completion: same inventory and bindings, no --maxfail.

.github/scripts/run_backend_tests.py hard-codes ``--maxfail=5``. On this macOS
host, tests/test_bounded_pg_backup.py fails 1 case and errors 16 on the pristine
accepted base too (a host prerequisite: Linux CI passes it), so the unchanged
launcher always stops early here, and its truncated run can never be called
complete. This runner imports that launcher file unchanged and reuses its own
``test_inventory``, ``bind_package``, ``descendant_environment`` and collection
receipt, so it schedules exactly the launcher's files with exactly its package
ownership. The only differences: no ``--maxfail``, no coverage, and pytest
arguments appended by the caller (record_v3 adds ``--junitxml``). It is a
completeness companion to the unchanged launcher run, not a replacement for it.

    python run_launcher_cohorts_complete.py --cohort backend|legacy --output-dir DIR [pytest args...]
"""
import argparse
import importlib.util
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=("backend", "legacy"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args, extra = parser.parse_known_args()
    root = Path.cwd().resolve().parent
    spec = importlib.util.spec_from_file_location("_launcher", root / ".github/scripts/run_backend_tests.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    if os.environ.get("PYTEST_ADDOPTS"):
        raise SystemExit("Ambient PYTEST_ADDOPTS refused, as by the launcher")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = launcher.test_inventory()[args.cohort]
    sys.path.insert(0, str(launcher.BACKEND))
    launcher.bind_package("seeding", launcher.BACKEND / "seeding")
    launcher.bind_package("etl", launcher.ROOT / "etl" if args.cohort == "legacy" else launcher.BACKEND / "etl")
    os.environ["PYTHONPATH"] = launcher.descendant_environment(args.cohort, output)
    os.chdir(launcher.BACKEND)
    import pytest

    return pytest.main([*files, "-o", "addopts=", "--verbose", "-m", "not slow", *extra],
                       plugins=[launcher.CollectionReceipt(args.cohort, files, output / f"collection-{args.cohort}.json")])


if __name__ == "__main__":
    raise SystemExit(main())

"""Run conflicting real package fixtures through the complete CI launcher."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/run_backend_tests.py"
SPEC = importlib.util.spec_from_file_location("backend_test_launcher", SCRIPT)
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


class LauncherTests(unittest.TestCase):
    def test_public_legacy_session_regressions_have_explicit_cohort_ownership(self):
        self.assertIn("tests/test_batch9_legacy_etl_sessions.py", LAUNCHER.LEGACY_ETL_TESTS)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.script = self.root / ".github/scripts/run_backend_tests.py"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        files = {
            "backend/pytest.ini": "[pytest]\npythonpath = .\n",
            "backend/etl/__init__.py": "OWNER = 'backend'\n",
            "backend/etl/normalizer.py": "def normalize_amount_to_kes(value): return value\n",
            "etl/__init__.py": "OWNER = 'legacy'\n",
            "etl/normalizer.py": "class DataNormalizer: pass\n",
            "backend/seeding/__init__.py": "OWNER = 'real'\n",
            "seeding/__init__.py": "raise AssertionError('Root stub was imported')\n",
            "backend/tests/test_backend.py": (
                "from etl.normalizer import normalize_amount_to_kes\n"
                "from seeding import OWNER\n"
                "def test_backend():\n"
                "    assert normalize_amount_to_kes(5) == 5\n"
                "    assert OWNER == 'real'\n"
            ),
        }
        for name in LAUNCHER.LEGACY_ETL_TESTS:
            files["backend/" + name] = (
                "from etl.normalizer import DataNormalizer\n"
                "from seeding import OWNER\n"
                "def test_legacy():\n"
                "    assert isinstance(DataNormalizer(), DataNormalizer)\n"
                "    assert OWNER == 'real'\n"
            )
        # The backend-only control above intentionally exercises a top-level
        # import in this synthetic tree. The product inventory rejects any new
        # undeclared importer, so bind this control by importlib in the fixture.
        files["backend/tests/test_backend.py"] = files["backend/tests/test_backend.py"].replace(
            "from etl.normalizer import normalize_amount_to_kes\n",
            "import importlib\nnormalize_amount_to_kes = importlib.import_module('etl.normalizer').normalize_amount_to_kes\n",
        )
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for args in (
            ["init", "-q"],
            ["-c", "user.name=Local fixture", "-c", "user.email=fixture@example.invalid",
             "commit", "--allow-empty", "-qm", "fixture"],
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.output = self.root / "results"

    def run_launcher(self, *args, env_overrides=None):
        env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR")
               if key in os.environ}
        # Deliberately offer the dangerous root package first. Anchored package
        # ownership must still choose backend/seeding, without mutating callers.
        env["PYTHONPATH"] = str(self.root)
        env.update(env_overrides or {})
        result = subprocess.run(
            [sys.executable, str(self.script), "--output-dir", str(self.output), *args],
            cwd=self.root, env=env, text=True, capture_output=True,
        )
        return result

    def test_original_combined_imports_fail_but_both_owned_cohorts_execute(self):
        original = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=self.root / "backend", env={"PATH": os.environ["PATH"]},
            text=True, capture_output=True,
        )
        self.assertNotEqual(original.returncode, 0)
        self.assertIn("cannot import name 'DataNormalizer'", original.stdout)
        fixed = self.run_launcher()
        self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["verdict"], "PASSED")
        self.assertEqual(summary["collected_counts"], {"backend": 1, "legacy": 9})
        self.assertEqual(summary["coverage_result"], 0)
        self.assertTrue((self.root / "backend/coverage.xml").is_file())
        for cohort in ("backend", "legacy"):
            receipt = json.loads((self.output / f"collection-{cohort}.json").read_text())
            self.assertEqual(receipt["package_identities"]["seeding"],
                             str(self.root / "backend/seeding/__init__.py"))
            self.assertEqual(receipt["package_identities"]["etl"],
                             str(self.root / ("etl" if cohort == "legacy" else "backend/etl") / "__init__.py"))
        from coverage import CoverageData

        combined = CoverageData(basename=str(self.root / "backend/.coverage"))
        combined.read()
        self.assertTrue(any(path.endswith("test_backend.py") for path in combined.measured_files()))
        self.assertTrue(any(path.endswith("test_audit_parser.py") for path in combined.measured_files()))

    def test_a_failing_legacy_case_keeps_the_complete_gate_red(self):
        path = self.root / "backend/tests/test_audit_parser.py"
        path.write_text(path.read_text() + "\ndef test_failure(): assert False\n")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["verdict"], "FAILED")
        self.assertEqual(summary["cohort_results"], {"backend": 0, "legacy": 1})

    def test_descendants_keep_their_real_packages_even_from_repository_root(self):
        for name, owner in (("tests/test_backend.py", "backend"),
                            ("tests/test_audit_parser.py", "legacy")):
            path = self.root / "backend" / name
            path.write_text(path.read_text() + f'''
def test_descendant():
    import os, subprocess, sys
    from pathlib import Path
    code = "import etl, seeding; assert etl.OWNER == '{owner}'; assert seeding.OWNER == 'real'"
    for directory in [Path.cwd(), Path.cwd().parent]:
        child = subprocess.run([sys.executable, '-c', code], cwd=directory,
                               env=os.environ.copy(), capture_output=True, text=True)
        assert child.returncode == 0, child.stderr
''')
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["collected_counts"], {"backend": 2, "legacy": 10})

    def test_descendant_package_selection_preserves_configuration_before_import(self):
        (self.root / "backend/database.py").write_text(
            "import os\nVALUE = os.environ.get('CI_FIXTURE_SETTING')\n"
        )
        (self.root / "backend/seeding/__init__.py").write_text(
            "OWNER = 'real'\nimport database\n"
        )
        path = self.root / "backend/tests/test_backend.py"
        path.write_text(path.read_text() + '''
def test_configured_child():
    import os, subprocess, sys
    child = subprocess.run([sys.executable, '-c',
        "import os; os.environ['CI_FIXTURE_SETTING']='after-start'; import seeding, database; assert seeding.OWNER=='real'; assert database.VALUE=='after-start'"],
        env={**os.environ, 'CI_FIXTURE_SETTING': 'before-start'},
        capture_output=True, text=True)
    assert child.returncode == 0, child.stderr
''')
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_backend_cohort_cannot_pass_and_stale_receipts_are_removed(self):
        (self.root / "backend/tests/test_backend.py").write_text("")
        self.output.mkdir()
        (self.output / "collection-backend.json").write_text('{"nodeids": ["stale"]}')
        result = self.run_launcher("--collect-only")
        self.assertNotEqual(result.returncode, 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["verdict"], "FAILED")
        self.assertNotIn("backend", summary["collected_counts"])

    def test_missing_legacy_file_refuses_the_inventory_and_removes_stale_summary(self):
        (self.root / "backend/tests/test_audit_parser.py").unlink()
        self.output.mkdir()
        (self.output / "summary.json").write_text('{"verdict": "PASSED"}')
        result = self.run_launcher("--collect-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("declared legacy file is missing", result.stderr)
        self.assertFalse((self.output / "summary.json").exists())

    def test_new_undeclared_etl_importer_requires_an_explicit_owner(self):
        (self.root / "backend/tests/test_new.py").write_text("from etl import normalizer\n")
        result = self.run_launcher("--collect-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Declare ETL ownership", result.stderr)

    def test_missing_real_seeding_does_not_fall_back_to_root_stub(self):
        (self.root / "backend/seeding/__init__.py").unlink()
        result = self.run_launcher("--collect-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Package unavailable", result.stderr)
        self.assertNotIn("Root stub was imported", result.stderr)

    def test_ambient_selectors_or_collect_only_cannot_turn_execution_green(self):
        path = self.root / "backend/tests/test_backend.py"
        path.write_text(path.read_text() + "\ndef test_failure(): assert False\n")
        for options in ("-k test_backend", "--collect-only"):
            with self.subTest(options=options):
                result = self.run_launcher(env_overrides={"PYTEST_ADDOPTS": options})
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((self.output / "summary.json").exists())
        with (self.root / "backend/pytest.ini").open("a") as config:
            config.write("addopts = --collect-only\n")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["mode"], "execution")
        self.assertEqual(summary["verdict"], "FAILED")

    def test_receipts_cannot_certify_wrong_package_identity_or_uncollected_cases(self):
        spec = importlib.util.spec_from_file_location("receipt_launcher", self.script)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        actual_run = subprocess.run
        for mode in ("good", "wrong-identities", "absent-identities", "wrong-files",
                     "absent-files", "string-nodeids", "foreign-nodeids", "duplicate-nodeids"):
            with self.subTest(mode=mode):
                output = self.root / ("receipt-" + mode)
                output.mkdir()
                (output / "summary.json").write_text('{"verdict": "PASSED", "stale": true}')

                def child(command, *args, **kwargs):
                    if command[0] == "git":
                        return actual_run(command, *args, **kwargs)
                    cohort = command[command.index("--cohort") + 1]
                    files = launcher.test_inventory()[cohort]
                    fields = dict(cohort=cohort, scheduled_files=files, collected_files=files,
                                  nodeids=[name + "::test_case" for name in files],
                                  package_identities={
                                      "etl": str(self.root / ("etl" if cohort == "legacy" else "backend/etl") / "__init__.py"),
                                      "seeding": str(self.root / "backend/seeding/__init__.py"),
                                  })
                    if mode == "wrong-identities": fields["package_identities"]["seeding"] = str(self.root / "seeding/__init__.py")
                    elif mode == "absent-identities": del fields["package_identities"]
                    elif mode == "wrong-files": fields["collected_files"] = ["tests/foreign.py"]
                    elif mode == "absent-files": del fields["collected_files"]
                    elif mode == "string-nodeids": fields["nodeids"] = "not-a-case-list"
                    elif mode == "foreign-nodeids": fields["nodeids"] = ["tests/foreign.py::test_case"]
                    elif mode == "duplicate-nodeids": fields["nodeids"] *= 2
                    launcher.write_receipt(output / f"collection-{cohort}.json", fields)
                    return SimpleNamespace(returncode=0)

                with patch.object(launcher.subprocess, "run", child):
                    if mode == "good":
                        self.assertEqual(launcher.run_all(output, collect_only=True), 0)
                    else:
                        with self.assertRaises(ValueError):
                            launcher.run_all(output, collect_only=True)
                        self.assertFalse((output / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()

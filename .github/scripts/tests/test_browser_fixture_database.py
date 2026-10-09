"""Browser CI database selection cannot accept an ambient production target."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "ci_browser_database", ROOT / "backend/tests/ci_browser_database.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BrowserDatabaseTests(unittest.TestCase):
    def test_defaults_preserve_original_owned_ports(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(MODULE.browser_database_port(55471), 55471)
            self.assertEqual(MODULE.browser_database_port(55483), 55483)

    def test_explicit_ci_uses_only_assigned_owned_port(self):
        with patch.dict(os.environ, {
            "BATCH9_CI_BROWSER": "true", "BROWSER_FIXTURE_POSTGRES_PORT": "55494",
            "DATABASE_URL": "postgresql://production.invalid/database",
        }, clear=True):
            self.assertEqual(MODULE.browser_database_port(55471), 55494)
            self.assertEqual(MODULE.browser_database_port(55483), 55494)

    def test_missing_hostile_and_ambiguous_configuration_is_refused(self):
        for values in (
            {"BATCH9_CI_BROWSER": "true"},
            {"BROWSER_FIXTURE_POSTGRES_PORT": "55494"},
            {"BATCH9_CI_BROWSER": "TRUE", "BROWSER_FIXTURE_POSTGRES_PORT": "55494"},
            *({"BATCH9_CI_BROWSER": "true", "BROWSER_FIXTURE_POSTGRES_PORT": port}
              for port in ("", "5432", "-1", "NaN", "true", "55494 ", "remote:55494")),
        ):
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(RuntimeError):
                    MODULE.browser_database_port(55471)


if __name__ == "__main__":
    unittest.main()

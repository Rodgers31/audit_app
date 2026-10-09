"""Actual coordinator fixture selects its declared additive schema, before I/O."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = r'''
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from sqlalchemy import Table
from tests import batch7_coordinator_integration_fixture as fixture

mode = sys.argv[1]
dispatch = 'e554d7c9a001_etl_dedicated_dispatch.py'
shared = 'e572b8c9a001_shared_seeding_exclusion.py'
if mode == 'actual-model':
    required = fixture.required_coordinator_migrations()
    expected = [('etl_dispatch_commands', dispatch)]
    if 'seeding_domain_claims' in fixture.Base.metadata.tables:
        expected.append(('seeding_domain_claims', shared))
    assert [(table, path.name) for table, path in required] == expected
    assert all(path.is_file() for _, path in required)
    print('actual declared migrations:', expected)
else:
    original = fixture.BACKEND
    with TemporaryDirectory(prefix='batch9-ci-migration-control-') as name:
        fixture.BACKEND = Path(name)
        versions = fixture.BACKEND / 'alembic/versions'
        versions.mkdir(parents=True)
        if mode != 'missing-dispatch':
            shutil.copy2(original / 'alembic/versions' / dispatch, versions / dispatch)
        if mode != 'missing-dispatch' and 'seeding_domain_claims' not in fixture.Base.metadata.tables:
            Table('seeding_domain_claims', fixture.Base.metadata)
        if mode == 'unrelated-head':
            # A genuine unrelated migration cannot replace the exact required one.
            shutil.copy2(original / 'alembic/versions' / dispatch, versions / 'unrelated_head.py')
        class NoDatabase:
            def __getattr__(self, attribute):
                raise AssertionError('Database used before migration inventory validation')
        fixture.engine = NoDatabase()
        try:
            fixture.prepare_database()
        except RuntimeError as error:
            expected = dispatch if mode == 'missing-dispatch' else shared
            assert str(error) == 'Missing required coordinator fixture migration: ' + expected
            print('missing exact migration refused before database access:', expected)
        else:
            raise AssertionError('Missing required migration was accepted')
'''


class CoordinatorSchemaTests(unittest.TestCase):
    def run_control(self, mode):
        env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHON_DOTENV_DISABLED": "1", "TESTING": "true",
               "PYTHONPATH": str(ROOT / "backend"),
               "BATCH7_COORDINATOR_INTEGRATION": "true",
               "BATCH9_CI_BROWSER": "true", "BROWSER_FIXTURE_POSTGRES_PORT": "55494",
               "DATABASE_URL": "postgresql+psycopg2://batch7_coordinator:batch7-inert-coordinator-local@127.0.0.1:55494/batch7_coordinator"}
        result = subprocess.run([sys.executable, "-c", SCRIPT, mode],
                                cwd=ROOT / "backend", env=env, text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_models_select_only_their_exact_additive_migrations(self):
        self.run_control("actual-model")

    def test_missing_dispatch_migration_refuses_before_database_access(self):
        self.run_control("missing-dispatch")

    def test_declared_shared_schema_requires_its_migration_before_database_access(self):
        self.run_control("missing-shared")

    def test_unrelated_head_cannot_replace_the_declared_shared_migration(self):
        self.run_control("unrelated-head")


if __name__ == "__main__":
    unittest.main()

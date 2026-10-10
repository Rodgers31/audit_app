"""Execute frontend configuration and preserve explicit backend workflow boundaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]


class ConfigurationTests(unittest.TestCase):
    def workflows(self):
        for name in ("ci.yml", "verification.yml"):
            yield name, yaml.safe_load((ROOT / ".github/workflows" / name).read_text())

    def assert_job_deadlines(self, workflow):
        expected = {
            "test-backend": 45, "test-frontend": 20, "test-etl": 10,
            "security-scan": 10, "test-browser": 20,
            "test-browser-legacy": 20, "quality-gate": 5,
        }
        for name, minutes in expected.items():
            actual = workflow["jobs"][name].get("timeout-minutes")
            self.assertIs(type(actual), int, name)
            self.assertEqual(actual, minutes, name)
        for name, job in workflow["jobs"].items():
            if name not in expected:
                self.assertNotIn("timeout-minutes", job, name)
        preparation = next(
            step for step in workflow["jobs"]["test-backend"]["steps"]
            if step.get("name") == "Prepare pinned owned PostgreSQL test images"
        )
        self.assertIs(type(preparation.get("timeout-minutes")), int)
        self.assertEqual(preparation["timeout-minutes"], 5)

    def test_complete_backend_has_finite_budget_without_relaxing_other_deadlines(self):
        # Run 38012121550 completed 15,466 pytest cases, coverage and cleanup,
        # then exhausted 30 minutes during controls before API smoke.
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                self.assert_job_deadlines(workflow)

    def test_deadline_policy_rejects_short_unbounded_or_broadened_budgets(self):
        for name, workflow in self.workflows():
            valid = deepcopy(workflow)
            valid["jobs"]["test-backend"]["timeout-minutes"] = 45
            self.assert_job_deadlines(valid)
            for minutes in (20, 30, 60, 0, -1, True, 45.0, "45", None,
                            float("nan"), float("inf"), [], {}):
                with self.subTest(workflow=name, backend_minutes=minutes):
                    mutated = deepcopy(valid)
                    mutated["jobs"]["test-backend"]["timeout-minutes"] = minutes
                    with self.assertRaises(AssertionError):
                        self.assert_job_deadlines(mutated)
            with self.subTest(workflow=name, missing_backend_limit=True):
                mutated = deepcopy(valid)
                del mutated["jobs"]["test-backend"]["timeout-minutes"]
                with self.assertRaises(AssertionError):
                    self.assert_job_deadlines(mutated)
            for job in valid["jobs"]:
                if job == "test-backend":
                    continue
                with self.subTest(workflow=name, broadened_job=job):
                    mutated = deepcopy(valid)
                    mutated["jobs"][job]["timeout-minutes"] = 30
                    with self.assertRaises(AssertionError):
                        self.assert_job_deadlines(mutated)
            with self.subTest(workflow=name, broadened_image_preparation=True):
                mutated = deepcopy(valid)
                preparation = next(
                    step for step in mutated["jobs"]["test-backend"]["steps"]
                    if step.get("name") == "Prepare pinned owned PostgreSQL test images"
                )
                preparation["timeout-minutes"] = 30
                with self.assertRaises(AssertionError):
                    self.assert_job_deadlines(mutated)

    def test_services_use_exact_official_ecr_pins_and_preserve_cached_role_fixture(self):
        postgres = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"
        redis = "public.ecr.aws/docker/library/redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                job = workflow["jobs"]["test-backend"]
                self.assertEqual(job["services"]["postgres"]["image"], postgres)
                self.assertEqual(job["services"]["redis"]["image"], redis)
                preparation = next(step for step in job["steps"] if step.get("name") == "Prepare pinned owned PostgreSQL test images")
                self.assertEqual(preparation["run"], "python .github/scripts/prepare_postgres_test_images.py --service-postgres-ref " + postgres)

    def test_each_frontend_step_can_load_actual_production_configuration(self):
        for name, workflow in self.workflows():
            job = workflow["jobs"]["test-frontend"]
            for step in job["steps"]:
                if "run" not in step:
                    continue
                with self.subTest(workflow=name, step=step["name"]):
                    env = {"PATH": os.environ["PATH"], "NODE_ENV": "production",
                           **job.get("env", {}), **step.get("env", {})}
                    self.assertFalse(any("secrets." in str(value) for value in env.values()))
                    result = subprocess.run(
                        ["node", "-e", "const c=require('./next.config.js'); c.rewrites().then(r=>console.log(JSON.stringify(r)));"],
                        cwd=ROOT / "frontend", env=env, text=True, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    rewrites = json.loads(result.stdout.splitlines()[-1])
                    self.assertEqual(rewrites[0]["destination"], "http://127.0.0.1:8000/api/v1/:path*")
                    if step["name"] == "Build (REQUIRED)":
                        self.assertEqual(env["NEXT_PUBLIC_SUPABASE_URL"], "http://127.0.0.1:8000")
                        self.assertEqual(env["NEXT_PUBLIC_SUPABASE_ANON_KEY"], "ci-test-only-anon-key")
                    else:
                        # A real auth client starts async session work under Jest's
                        # fake timers; those unit tests deliberately have no auth
                        # session. Only the production build needs inert auth config.
                        self.assertNotIn("NEXT_PUBLIC_SUPABASE_URL", env)
                        self.assertNotIn("NEXT_PUBLIC_SUPABASE_ANON_KEY", env)

    def test_backend_runs_complete_launcher_without_production_configuration(self):
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                job = workflow["jobs"]["test-backend"]
                step = next(step for step in job["steps"] if step.get("id") == "backend_tests")
                self.assertEqual(step["run"], "python .github/scripts/run_backend_tests.py")
                self.assertNotIn("continue-on-error", step)
                self.assertEqual(step["env"], {
                    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/audit_app_test",
                    "REDIS_URL": "redis://localhost:6379", "TESTING": True,
                    "PYTHON_DOTENV_DISABLED": "1",
                })

    def test_browser_cohort_verdicts_execute_with_negative_controls(self):
        result = subprocess.run(
            ["node", "--test", "scripts/ci-browser-cohorts.test.mjs", "scripts/run-legacy-e2e.test.mjs"],
            cwd=ROOT / "frontend", text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# pass 13", result.stdout)

    def test_etl_cohort_waits_for_an_actual_fixture_route(self):
        result = subprocess.run(
            ["node", "--input-type=module", "-e",
             "import {selectedCohort} from './scripts/ci-browser-cohorts.mjs'; console.log(selectedCohort('etl-ui').health)"],
            cwd=ROOT / "frontend", text=True, capture_output=True, check=True,
        )
        import importlib.util
        import sys
        from unittest.mock import patch
        from fastapi.testclient import TestClient

        spec = importlib.util.spec_from_file_location(
            "ci_etl_fixture", ROOT / "backend/tests/batch7_etl_ui_fixture.py"
        )
        fixture = importlib.util.module_from_spec(spec)
        # dataclasses resolves annotations through the module registry.
        with patch.dict(sys.modules, {spec.name: fixture}):
            spec.loader.exec_module(fixture)
            response = TestClient(fixture.app).get(result.stdout.strip())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()

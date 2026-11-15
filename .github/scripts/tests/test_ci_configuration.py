"""Execute frontend configuration and preserve explicit backend workflow boundaries."""
from copy import deepcopy
import json
import os
import re
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]


class ConfigurationTests(unittest.TestCase):
    def assert_backend_receipts(self, workflow):
        step = next(step for step in workflow["jobs"]["test-backend"]["steps"]
                    if step.get("name") == "Preserve backend test receipts")
        self.assertEqual(step["if"], "always()")
        self.assertEqual(step["uses"].partition("@")[0], "actions/upload-artifact")
        self.assertIs(step["with"].get("include-hidden-files"), True)
        self.assertEqual(step["with"]["path"].splitlines(), [
            "backend/.ci-test-results/collection-*.json",
            "backend/.ci-test-results/results-*.xml",
            "backend/.ci-test-results/summary.json",
            "backend/coverage.xml",
        ])

    def test_backend_receipts_include_only_explicit_hidden_reports(self):
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                self.assert_backend_receipts(workflow)

    def test_receipt_policy_rejects_hidden_omission_and_broader_upload(self):
        for name, workflow in self.workflows():
            for mutation in ("omitted", "false", "string", "broad"):
                bad = deepcopy(workflow)
                step = next(step for step in bad["jobs"]["test-backend"]["steps"]
                            if step.get("name") == "Preserve backend test receipts")
                if mutation == "omitted":
                    step["with"].pop("include-hidden-files", None)
                elif mutation == "broad":
                    step["with"]["path"] = "backend/"
                else:
                    step["with"]["include-hidden-files"] = False if mutation == "false" else "true"
                with self.subTest(workflow=name, mutation=mutation), self.assertRaises(AssertionError):
                    self.assert_backend_receipts(bad)

    def workflows(self):
        for name in ("pr-ci.yml", "verification.yml"):
            yield name, yaml.safe_load((ROOT / ".github/workflows" / name).read_text())

    def test_pull_request_ci_boundary(self):
        paths = ROOT / ".github/workflows"
        self.assertFalse((paths / "ci.yml").exists())
        raw = (paths / "pr-ci.yml").read_text()
        workflow = yaml.safe_load(raw)
        self.assertEqual(workflow.get("on", workflow.get(True)), {"pull_request": {"branches": ["main", "develop"]}})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        jobs = workflow["jobs"]
        required = {"test-backend", "test-frontend", "test-etl", "security-scan", "quality-gate"}
        browser = {"test-browser", "test-browser-legacy"}
        self.assertEqual(set(jobs), required | browser)
        self.assertEqual(set(jobs["quality-gate"]["needs"]), (required | browser) - {"quality-gate"})
        self.assertEqual(jobs["security-scan"]["permissions"], {
            "contents": "read", "security-events": "write", "actions": "read",
        })
        for name, job in jobs.items():
            self.assertNotIn("environment", job)
            if name != "security-scan":
                self.assertNotIn("permissions", job)
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"^[^@]+@[0-9a-f]{40}$")
        self.assertEqual(set(re.findall(r"secrets\.([A-Z0-9_]+)", raw)), {"CODECOV_TOKEN"})
        self.assertEqual(raw.count("alembic upgrade head"), 1)
        [(job_name, schema_guard)] = [
            (name, step) for name, job in jobs.items() for step in job["steps"]
            if "alembic upgrade head" in step.get("run", "")
        ]
        self.assertEqual(job_name, "test-backend")
        self.assertEqual(schema_guard["name"], "Check migrated public table access")
        self.assertEqual(schema_guard["timeout-minutes"], 5)
        self.assertEqual(schema_guard["env"], {
            "SCHEMA_GUARD_CONTAINER": "${{ job.services.schema-guard-postgres.id }}",
            "PUBLIC_SCHEMA_GUARD_CI_URL": "postgresql://postgres:postgres@127.0.0.1:55498/auditgava_schema_guard",
            "PYTHON_DOTENV_DISABLED": "1",
        })
        self.assertIn(
            'DATABASE_URL="$PUBLIC_SCHEMA_GUARD_CI_URL?hostaddr=127.0.0.1" python -m alembic upgrade head',
            schema_guard["run"].splitlines(),
        )
        service = jobs["test-backend"]["services"]["schema-guard-postgres"]
        self.assertEqual(service["image"], jobs["test-backend"]["services"]["postgres"]["image"])
        self.assertEqual(service["ports"], ["127.0.0.1:55498:5432"])
        self.assertEqual(service["env"]["POSTGRES_DB"], "auditgava_schema_guard")

    def assert_job_deadlines(self, workflow, backend_minutes):
        expected = {
            "test-backend": backend_minutes, "test-frontend": 20, "test-etl": 10,
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
        # Keep each workflow bounded while allowing PR CI's current core
        # inventory, legacy tests, coverage and cleanup to finish.
        for name, workflow in self.workflows():
            with self.subTest(workflow=name):
                self.assert_job_deadlines(workflow, 90 if name == "pr-ci.yml" else 60)

    def test_deadline_policy_rejects_short_unbounded_or_broadened_budgets(self):
        for name, workflow in self.workflows():
            backend_minutes = 90 if name == "pr-ci.yml" else 60
            other_backend_timeout = 60 if name == "pr-ci.yml" else 90
            valid = deepcopy(workflow)
            valid["jobs"]["test-backend"]["timeout-minutes"] = backend_minutes
            self.assert_job_deadlines(valid, backend_minutes)
            for minutes in (20, 30, 45, 70, other_backend_timeout, 120, 0, -1, True,
                            float(backend_minutes), str(backend_minutes), None,
                            float("nan"), float("inf"), [], {}):
                with self.subTest(workflow=name, backend_minutes=minutes):
                    mutated = deepcopy(valid)
                    mutated["jobs"]["test-backend"]["timeout-minutes"] = minutes
                    with self.assertRaises(AssertionError):
                        self.assert_job_deadlines(mutated, backend_minutes)
            with self.subTest(workflow=name, missing_backend_limit=True):
                mutated = deepcopy(valid)
                del mutated["jobs"]["test-backend"]["timeout-minutes"]
                with self.assertRaises(AssertionError):
                    self.assert_job_deadlines(mutated, backend_minutes)
            for job in valid["jobs"]:
                if job == "test-backend":
                    continue
                with self.subTest(workflow=name, broadened_job=job):
                    mutated = deepcopy(valid)
                    mutated["jobs"][job]["timeout-minutes"] = 30
                    with self.assertRaises(AssertionError):
                        self.assert_job_deadlines(mutated, backend_minutes)
            with self.subTest(workflow=name, broadened_image_preparation=True):
                mutated = deepcopy(valid)
                preparation = next(
                    step for step in mutated["jobs"]["test-backend"]["steps"]
                    if step.get("name") == "Prepare pinned owned PostgreSQL test images"
                )
                preparation["timeout-minutes"] = 30
                with self.assertRaises(AssertionError):
                    self.assert_job_deadlines(mutated, backend_minutes)

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
                prefix = "tini -s -- " if name == "pr-ci.yml" else ""
                self.assertEqual(step["run"], prefix + "python .github/scripts/run_backend_tests.py")
                self.assertNotIn("continue-on-error", step)
                census = [item for item in job["steps"] if item.get("name") == "Build isolated refresh census fixture"]
                if name == "pr-ci.yml":
                    self.assertEqual(len(census), 1)
                    self.assertLess(job["steps"].index(census[0]), job["steps"].index(step))
                    self.assertEqual(census[0]["timeout-minutes"], 5)
                    self.assertNotIn("continue-on-error", census[0])
                else:
                    self.assertEqual(census, [])
                self.assertEqual(step["env"], {
                    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/audit_app_test",
                    "REDIS_URL": "redis://localhost:6379", "TESTING": True,
                    "PYTHON_DOTENV_DISABLED": "1",
                    **({"TEST_REFRESH_CENSUS_CONTAINER": "1"} if name == "pr-ci.yml" else {}),
                })

    def test_browser_cohort_verdicts_execute_with_negative_controls(self):
        result = subprocess.run(
            ["node", "--test", "--test-reporter=tap", "scripts/ci-browser-cohorts.test.mjs", "scripts/run-legacy-e2e.test.mjs"],
            cwd=ROOT / "frontend", text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"(?m)^# tests 43$")
        self.assertRegex(result.stdout, r"(?m)^# pass 43$")
        self.assertRegex(result.stdout, r"(?m)^# fail 0$")
        self.assertRegex(result.stdout, r"(?m)^# skipped 0$")

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

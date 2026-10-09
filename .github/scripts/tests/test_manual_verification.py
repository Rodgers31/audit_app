"""Offline guards for the bounded manual verification workflow."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/verify_checkout.py"
JOBS = {
    "test-backend", "test-frontend", "test-etl", "security-scan",
    "test-browser", "test-browser-legacy", "quality-gate",
}
GUARD_NAME = "Verify frozen checkout"
FULL_SCOPE = "${{ inputs.verification_scope == 'full' }}"
FULL_QUALITY_SCOPE = "${{ always() && inputs.verification_scope == 'full' }}"


class ManualWorkflowBoundaryTests(unittest.TestCase):
    def test_required_reconciliation_fixture_is_ready_before_tests_and_always_cleaned(self):
        for filename in ("ci.yml", "verification.yml"):
            steps = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())["jobs"]["test-backend"]["steps"]
            images = next(i for i, step in enumerate(steps) if step.get("name") == "Prepare pinned owned PostgreSQL test images")
            preparation = next(step for step in steps if step.get("name") == "Prepare owned reconciliation test fixture")
            tests = next(i for i, step in enumerate(steps) if step.get("id") == "backend_tests")
            cleanup = next(step for step in steps if step.get("name") == "Remove owned reconciliation test fixture")
            self.assertLess(images, steps.index(preparation))
            self.assertLess(steps.index(preparation), tests)
            self.assertGreater(steps.index(cleanup), tests)
            self.assertEqual(preparation["timeout-minutes"], 5)
            self.assertEqual(cleanup["timeout-minutes"], 5)
            self.assertNotIn("continue-on-error", preparation)
            self.assertNotIn("continue-on-error", cleanup)
            self.assertEqual(cleanup["if"], "always()")
            state = '"$RUNNER_TEMP/reconciliation-fixture-state.json"'
            self.assertEqual(preparation["run"],
                             f"python .github/scripts/prepare_reconciliation_test_fixture.py prepare --state {state} --port 55496")
            self.assertIn(f"if [ -f {state} ]; then", cleanup["run"])
            self.assertIn(f"python .github/scripts/prepare_reconciliation_test_fixture.py cleanup --state {state}", cleanup["run"])
            self.assertNotIn("DATABASE_URL", preparation.get("env", {}))
            self.assertEqual(steps[tests]["env"]["DATABASE_URL"],
                             "postgresql://postgres:postgres@localhost:5432/audit_app_test")

    def test_only_manual_trigger_and_no_production_jobs(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/verification.yml").read_text())
        # PyYAML's YAML 1.1 loader may read an unquoted 'on' as True.
        trigger = workflow.get("on", workflow.get(True))
        self.assertEqual(set(trigger), {"workflow_dispatch"})
        self.assertIs(trigger["workflow_dispatch"]["inputs"]["commit_sha"]["required"], True)
        self.assertEqual(set(workflow["jobs"]), JOBS)
        self.assertIs(workflow["concurrency"]["cancel-in-progress"], False)

    def test_explicit_scope_selects_only_backend_without_claiming_full_quality(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/verification.yml").read_text())
        trigger = workflow.get("on", workflow.get(True))
        scope = trigger["workflow_dispatch"]["inputs"]["verification_scope"]
        self.assertEqual(scope, {
            "description": "full: all seven CI jobs; backend: backend only, full quality gate skipped",
            "required": True, "default": "full", "type": "choice",
            "options": ["full", "backend"],
        })
        self.assertEqual(workflow["run-name"],
                         "Manual verification [${{ inputs.verification_scope }}] ${{ inputs.commit_sha }}")
        self.assertNotIn("if", workflow["jobs"]["test-backend"])
        for name in JOBS - {"test-backend"}:
            self.assertEqual(workflow["jobs"][name]["if"],
                             FULL_QUALITY_SCOPE if name == "quality-gate" else FULL_SCOPE)
        # Model only the exact scope conditions above, not arbitrary expressions.
        for mode, expected in (("full", JOBS), ("backend", {"test-backend"})):
            selected = {name for name, job in workflow["jobs"].items()
                        if "if" not in job or mode == "full"}
            self.assertEqual(selected, expected)

    def test_owned_postgres_images_are_prepared_before_backend_tests(self):
        for filename in ("ci.yml", "verification.yml"):
            job = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())["jobs"]["test-backend"]
            steps = job["steps"]
            preparation = next(step for step in steps if step.get("name") == "Prepare pinned owned PostgreSQL test images")
            self.assertEqual(preparation["run"], "python .github/scripts/prepare_postgres_test_images.py --service-postgres-ref public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3")
            self.assertEqual(preparation["timeout-minutes"], 5)
            self.assertNotIn("continue-on-error", preparation)
            self.assertEqual(job["timeout-minutes"], 30)
            self.assertLess(steps.index(preparation), next(i for i, step in enumerate(steps) if step.get("id") == "backend_tests"))

    def test_manual_jobs_keep_the_required_ci_contract(self):
        ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        manual = yaml.safe_load((ROOT / ".github/workflows/verification.yml").read_text())
        self.assertEqual(manual["permissions"], ci["permissions"])
        for name in JOBS:
            with self.subTest(job=name):
                expected = ci["jobs"][name]
                actual = deepcopy(manual["jobs"][name])
                if name != "test-backend":
                    self.assertEqual(actual.pop("if"),
                                     FULL_QUALITY_SCOPE if name == "quality-gate" else FULL_SCOPE)
                    if name == "quality-gate":
                        actual["if"] = "always()"
                steps = actual["steps"]
                guards = [step for step in steps if step.get("name") == GUARD_NAME]
                checkouts = [step for step in steps
                             if step.get("uses", "").startswith("actions/checkout@")]
                if name == "quality-gate":
                    self.assertEqual(guards, [])
                    self.assertEqual(checkouts, [])
                else:
                    self.assertEqual(len(guards), 1)
                    self.assertEqual(len(checkouts), 1)
                    self.assertEqual(steps[1], guards[0])
                    self.assertEqual(guards[0], {
                        "name": GUARD_NAME,
                        "run": "python3 .github/scripts/verify_checkout.py",
                        "env": {"VERIFICATION_COMMIT": "${{ inputs.commit_sha }}",
                                "VERIFICATION_SCOPE": "${{ inputs.verification_scope }}"},
                    })
                    self.assertEqual(checkouts[0]["with"], {
                        "ref": "${{ inputs.commit_sha }}",
                    })
                    del checkouts[0]["with"]
                    steps.remove(guards[0])
                self.assertEqual(actual, expected)


class CheckoutGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for args in (
            ["init", "-q"],
            ["-c", "user.name=Local test", "-c", "user.email=local@example.invalid",
             "commit", "--allow-empty", "-qm", "fixture"],
        ):
            subprocess.run(["git", *args], cwd=self.directory, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.directory, text=True
        ).strip()

    def run_guard(self, **overrides):
        env = {
            "PATH": "/usr/bin:/bin", "VERIFICATION_COMMIT": self.sha,
            "GITHUB_SHA": self.sha, "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        env.update(overrides)
        return subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=self.directory, env=env,
            text=True, capture_output=True, check=False,
        )

    def test_real_matching_checkout_is_accepted(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.sha, result.stdout)

    def test_explicit_full_and_backend_scopes_are_reported(self):
        for scope in ("full", "backend"):
            with self.subTest(scope=scope):
                result = self.run_guard(VERIFICATION_SCOPE=scope)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"scope={scope}", result.stdout)
                self.assertIn(self.sha, result.stdout)
                if scope == "backend":
                    self.assertIn("full quality gate skipped", result.stdout)
        self.assertIn("scope=full", self.run_guard().stdout)

    def test_unknown_empty_and_hostile_scopes_are_refused(self):
        for scope in ("", "all", "frontend", "BACKEND", " full", "backend\n", "$(echo unsafe)"):
            with self.subTest(scope=scope):
                result = self.run_guard(VERIFICATION_SCOPE=scope)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("scope", result.stderr.lower())

    def test_backend_scope_preserves_frozen_commit_and_attempt_refusals(self):
        for overrides in (
            {"GITHUB_SHA": "0" * 40},
            {"VERIFICATION_COMMIT": "0" * 40, "GITHUB_SHA": "0" * 40},
            {"VERIFICATION_COMMIT": "main"},
            {"GITHUB_RUN_ATTEMPT": "2"},
            {"GITHUB_EVENT_NAME": "push"},
        ):
            with self.subTest(overrides=overrides):
                self.assertNotEqual(self.run_guard(
                    VERIFICATION_SCOPE="backend", **overrides
                ).returncode, 0)

    def test_automatic_events_are_refused(self):
        for event in ("push", "pull_request", "schedule", ""):
            with self.subTest(event=event):
                self.assertNotEqual(self.run_guard(GITHUB_EVENT_NAME=event).returncode, 0)

    def test_missing_short_and_hostile_sha_are_refused(self):
        for value in ("", "main", "a" * 7, "A" * 40, "$(echo unsafe)"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_guard(VERIFICATION_COMMIT=value).returncode, 0)

    def test_dispatch_ref_and_actual_checkout_must_both_match(self):
        wrong = "0" * 40
        self.assertNotEqual(self.run_guard(GITHUB_SHA=wrong).returncode, 0)
        self.assertNotEqual(self.run_guard(
            VERIFICATION_COMMIT=wrong, GITHUB_SHA=wrong
        ).returncode, 0)

    def test_unknown_or_repeat_attempt_is_refused(self):
        for attempt in ("", "0", "2", "unknown"):
            with self.subTest(attempt=attempt):
                self.assertNotEqual(self.run_guard(GITHUB_RUN_ATTEMPT=attempt).returncode, 0)


if __name__ == "__main__":
    unittest.main()

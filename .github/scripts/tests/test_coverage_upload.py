"""Offline coverage reporting controls; no application or provider imports."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/coverage_upload.py"


class CoverageUploadWorkflowTests(unittest.TestCase):
    def test_provider_rejection_is_not_a_successful_upload_step(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        upload = next(step for step in workflow["jobs"]["test-backend"]["steps"]
                      if step.get("uses", "").startswith("codecov/codecov-action@"))
        # Codecov's wrapper masks provider/CLI errors when this input is false.
        self.assertIs(upload["with"]["fail_ci_if_error"], True)
        self.assertIs(upload["continue-on-error"], True)

    def test_summary_observes_failed_and_skipped_steps(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        reporter = next(step for step in workflow["jobs"]["test-backend"]["steps"]
                        if step.get("name") == "Report optional hosted coverage outcome")
        self.assertEqual(reporter["if"], "always()")
        self.assertEqual(reporter["env"]["UPLOAD_OUTCOME"],
                         "${{ steps.coverage_upload.outcome }}")


class CoverageUploadReportingTests(unittest.TestCase):
    def run_script(self, phase, *, coverage=True, token="fixture-token",
                   enabled="", status="ready", outcome="success"):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            report = scratch / "coverage.xml"
            if coverage:
                report.write_text('<coverage line-rate="0.75"/>')
            output, summary = scratch / "output", scratch / "summary"
            child_env = {
                "PATH": "/usr/bin:/bin", "CODECOV_TOKEN": token,
                "CODECOV_UPLOAD_ENABLED": enabled, "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary), "UPLOAD_STATUS": status,
                "UPLOAD_OUTCOME": outcome, "COVERAGE_COMMIT": "a" * 40,
                "GITHUB_REPOSITORY": "example/project", "TEST_OUTCOME": "success",
                "LOCAL_COVERAGE_OUTCOME": "success",
            }
            result = subprocess.run(
                [sys.executable, str(SCRIPT), phase, "--coverage", str(report)],
                cwd=ROOT, env=child_env, capture_output=True, text=True, check=False,
            )
            return (result.returncode, result.stdout + result.stderr,
                    output.read_text() if output.exists() else "",
                    summary.read_text() if summary.exists() else "")

    def test_ready_does_not_claim_an_upload(self):
        rc, log, output, _ = self.run_script("prepare")
        self.assertEqual(rc, 0, log)
        self.assertEqual(output, "status=ready\n")
        self.assertIn("not attempted", log)
        self.assertNotIn("fixture-token", log)

    def test_disabled_is_intentional_and_visible(self):
        rc, log, output, _ = self.run_script("prepare", enabled="false", token="")
        self.assertEqual(rc, 0, log)
        self.assertEqual(output, "status=disabled\n")
        self.assertIn("disabled", log)

    def test_missing_auth_refuses_upload(self):
        rc, log, output, _ = self.run_script("prepare", token="")
        self.assertEqual(rc, 1, log)
        self.assertEqual(output, "status=missing_auth\n")
        self.assertIn("::warning::", log)

    def test_missing_coverage_refuses_upload(self):
        rc, log, output, _ = self.run_script("prepare", coverage=False)
        self.assertEqual(rc, 1, log)
        self.assertEqual(output, "status=missing_coverage\n")
        self.assertIn("::warning::", log)

    def test_unknown_policy_refuses_upload(self):
        rc, log, output, _ = self.run_script("prepare", enabled="maybe")
        self.assertEqual(rc, 1, log)
        self.assertEqual(output, "status=invalid_configuration\n")

    def test_action_success_is_unverified_and_warns(self):
        rc, log, output, summary = self.run_script("report")
        self.assertEqual(rc, 0, log)
        self.assertEqual(output, "status=uploaded_unverified\n")
        self.assertIn("::warning::", log)
        self.assertIn("Hosted report: **not verified**", summary)
        self.assertIn("a" * 40, summary)
        self.assertIn("/commit/", summary)
        self.assertNotIn("fixture-token", log + output + summary)

    def test_optional_failure_uses_raw_outcome(self):
        rc, log, output, summary = self.run_script("report", outcome="failure")
        self.assertEqual(rc, 0, log)
        self.assertEqual(output, "status=upload_failed\n")
        self.assertIn("::warning::", log)
        self.assertIn("rejected or failed", summary)
        self.assertIn("Upload action attempts: **1**", summary)
        self.assertIn("Local coverage step: **success**", summary)

    def test_skipped_and_unconfigured_paths_have_no_attempts(self):
        for status in ("disabled", "missing_auth", "missing_coverage", "",
                       "invalid_configuration"):
            with self.subTest(status=status):
                rc, log, output, summary = self.run_script(
                    "report", status=status, outcome="skipped")
                self.assertEqual(rc, 0, log)
                self.assertIn("Upload action attempts: **0**", summary)
                self.assertNotIn("uploaded_unverified", output)
                self.assertIn("Hosted report: **not verified**", summary)

    def test_unknown_action_result_never_certifies_acceptance(self):
        for outcome in ("", "skipped", "cancelled", "accepted", "true"):
            with self.subTest(outcome=outcome):
                rc, log, output, summary = self.run_script("report", outcome=outcome)
                self.assertEqual(rc, 0, log)
                expected = "not_attempted" if outcome == "skipped" else "upload_unknown"
                self.assertIn(f"status={expected}\n", output)
                attempts = "0" if outcome == "skipped" else "unknown"
                self.assertIn(f"Upload action attempts: **{attempts}**", summary)
                self.assertIn("::warning::", log)
                self.assertIn("Hosted report: **not verified**", summary)

    def test_completed_action_is_observed_even_with_missing_prepare_output(self):
        for status in ("", "disabled", "missing_auth", "ready"):
            with self.subTest(status=status):
                rc, log, output, summary = self.run_script(
                    "report", status=status, outcome="failure")
                self.assertEqual(rc, 0, log)
                self.assertIn("status=upload_failed\n", output)
                self.assertIn("Upload action attempts: **1**", summary)


if __name__ == "__main__":
    unittest.main()

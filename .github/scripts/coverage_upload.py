"""Report optional hosted coverage separately from local test/coverage results.

Prepare refuses absent prerequisites with a nonzero exit. Report exits zero
when it has written a truthful summary; that is not a provider success verdict.
Only a later exact-commit hosted report readback can establish acceptance.
"""

import argparse
import os
from pathlib import Path


def emit_status(status):
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"status={status}\n")


def prepare(coverage):
    enabled = os.environ.get("CODECOV_UPLOAD_ENABLED", "") or "true"
    if enabled == "false":
        status, message, rc = "disabled", "Optional Codecov upload disabled; not attempted.", 0
    elif enabled != "true":
        status, message, rc = (
            "invalid_configuration", "CODECOV_UPLOAD_ENABLED must be true or false; not attempted.", 1
        )
    elif not coverage.is_file() or coverage.stat().st_size == 0:
        status, message, rc = "missing_coverage", "Coverage XML missing or empty; upload not attempted.", 1
    elif not os.environ.get("CODECOV_TOKEN", "").strip():
        status, message, rc = (
            "missing_auth", "CODECOV_TOKEN unavailable to this run; optional upload not attempted.", 1
        )
    else:
        status, message, rc = "ready", "Optional Codecov upload ready; not attempted yet.", 0
    emit_status(status)
    print(("::warning::" if rc else "") + message)
    return rc


def report():
    prepared = os.environ.get("UPLOAD_STATUS", "")
    outcome = os.environ.get("UPLOAD_OUTCOME", "")
    attempts = 0
    if outcome in {"success", "failure"}:
        attempts = 1
        if outcome == "failure":
            status = "upload_failed"
            message = "Optional Codecov upload rejected or failed. See the upload step log."
        else:
            status = "uploaded_unverified"
            message = "Codecov action completed; hosted report processing/acceptance is unverified."
    elif outcome not in {"", "skipped"} or (prepared == "ready" and outcome == ""):
        attempts = "unknown"
        status = "upload_unknown"
        message = "Codecov attempt completion is unknown; check the upload step log."
    elif prepared == "disabled":
        status, message = "disabled", "Optional Codecov upload intentionally disabled for this run."
    elif prepared in {"missing_auth", "missing_coverage", "invalid_configuration"}:
        status = prepared
        message = f"Optional Codecov upload not attempted: {prepared}."
    else:
        status, message = "not_attempted", "No completed Codecov upload attempt; check preceding steps."

    emit_status(status)
    print(("" if status == "disabled" else "::warning::") + message)
    commit = os.environ["COVERAGE_COMMIT"]
    repository = os.environ["GITHUB_REPOSITORY"]
    tests = os.environ.get("TEST_OUTCOME", "") or "not_run"
    local_coverage = os.environ.get("LOCAL_COVERAGE_OUTCOME", "") or "not_run"
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        summary.write(
            "## Optional backend hosted coverage\n\n"
            f"Outcome: **{status}**. {message}\n\n"
            f"Upload action attempts: **{attempts}**. Hosted report: **not verified**.\n\n"
            f"Coverage commit: `{commit}`. Backend tests: **{tests}**. "
            f"Local coverage step: **{local_coverage}** (independent of hosted upload).\n\n"
        )
        if status == "uploaded_unverified":
            summary.write(
                f"[Inspect the exact commit report](https://app.codecov.io/gh/{repository}/commit/{commit}). "
                "A successful action or queued upload alone does not prove a processed hosted report. "
                "Record provider acceptance for this SHA during final CI verification.\n\n"
            )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "report"))
    parser.add_argument("--coverage", type=Path, default=Path("backend/coverage.xml"))
    args = parser.parse_args()
    return prepare(args.coverage) if args.phase == "prepare" else report()


if __name__ == "__main__":
    raise SystemExit(main())

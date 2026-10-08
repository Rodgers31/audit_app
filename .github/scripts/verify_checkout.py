"""Refuse a manual verification run unless it tests the frozen dispatch commit."""

import os
import re
import subprocess


def main():
    scope = os.environ.get("VERIFICATION_SCOPE", "full")
    if scope not in {"full", "backend"}:
        raise SystemExit("Verification scope must be full or backend.")
    expected = os.environ.get("VERIFICATION_COMMIT", "")
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise SystemExit("Verification requires a complete lowercase commit SHA.")
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise SystemExit("Verification is manual-only.")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise SystemExit("A new verification attempt requires a separately authorized dispatch.")
    if os.environ.get("GITHUB_SHA") != expected:
        raise SystemExit("Dispatch ref moved or differs from the approved commit.")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != expected:
        raise SystemExit("Checked-out commit differs from the approved commit.")
    print(f"Verified frozen checkout: {actual}; scope={scope}; manual dispatch, attempt 1.")
    if scope == "backend":
        print("Backend only: frontend, ETL, security and browser jobs skipped; full quality gate skipped.")


if __name__ == "__main__":
    main()

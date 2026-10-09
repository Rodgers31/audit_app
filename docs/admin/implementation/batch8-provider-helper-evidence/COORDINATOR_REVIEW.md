# Coordinator review of PR #579

Comment 4232126293 is refuted by executed checks against HTTPX 0.25.2 and
0.28.1. In both, InvalidURL inherits directly from Exception, and is not an
HTTPError. A real malformed URL returns the bounded 500 diagnostic before any
transport call. A valid UUID profile read succeeds; a memory-transport
ConnectError returns the bounded 503 diagnostic. Socket transport was denied.

The two JSON receipts are copied unchanged from the actual runs. The replay
script is `verify_helper_invalidurl.py`; run it with the backend on PYTHONPATH,
PYTHON_DOTENV_DISABLED=1, and the chosen installed HTTPX version. The script
itself installs inert configuration and refuses socket transport. Its helper
SHA256 binds the exact evaluated implementation.

The documentation typo in comment 4232126359 is corrected. No production
helper change was warranted by either finding. Current helper/auth/Users/import
selection: 449 passed. Minimum-HTTPX helper selection: 215 passed. Earlier
incomplete fixture attempts remain in the external coordinator packet and are
not counted as successes. Hosted CI and live-provider acceptance were not run.

## Signed-auth fixture isolation

The broader coordinator run exposed five failures when the inherited JWT key
did not match the new test's hardcoded signed token. The test now scopes its
own inert verification key using monkeypatch and signs with that same local
key. Application authentication is unchanged. An independent replay passes
5/5 with no ambient key and 5/5 with a different ambient key. The initial
failures are retained in the coordinator packet; this is a test portability
defect, not a live authorization defect. Combined current-source validation
passes 1,425 selected backend tests, with three explicit retained-document
skips. The corrected fixture does not require an operator-provided secret.

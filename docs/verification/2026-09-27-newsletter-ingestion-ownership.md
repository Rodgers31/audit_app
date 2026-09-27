# Newsletter and web ingestion ownership (session 4)

Main-compatible changes based on `1bd397f398450245da83abc2e24502ab16ffb063`.
No merge, deployment, production seed, production configuration change or real
email delivery was performed. Related issues remain open for release verification.

## Newsletter (#288, #303)

The standalone anonymous welcome and unsubscribe routes are removed, along with
the unused frontend callers and write-route allowlist exemptions. Welcome mail
is a best-effort background task only after committing a new subscription.
Normalized duplicate signup and concurrent retries create at most one row and
one welcome task. A failed welcome is not retried by anonymous signup: the API
success describes the subscription, not SMTP delivery. A durable email outbox
would be separate work.

An existing opted-out address can only resubscribe when `/newsletter/subscribe`
receives its valid token. The anonymous opt-out reversal was reproduced and logged
under #288. The existing unsubscribe verification flow remains usable and replay
is idempotent. Tokens remain scoped to the address, as before. Existing signed
links retain their format. The banner cannot reverse an opt-out by address alone.

Production and staging require a configured persistent SECRET_KEY; newsletter
operations return 503 before mutations if missing. Development/test can share one
process-local fallback. The production compose file now requires the key explicitly.
The deployed Render key is UNVERIFIED. Keys must match across replicas/restarts;
changing a real key invalidates existing links. No historical signing key or
working historical link is assumed. The key is resolved once per Settings instance.

Tests run the actual HMAC comparison with valid-format wrong signatures and a
positive valid token. A mutation that bypassed compare_digest made two tests fail.
Separate Python processes produced identical tokens under the configured test key.
All send functions were stubbed; no verification email was sent to a real user.

## Ingestion ownership (#322 item 7)

The web auto-seeder no longer schedules audits, counties_budget or the budgets
alias, and its registry dispatcher explicitly refuses direct calls. It reports
`.github/workflows/seed.yml` as the external job owner. This is the existing
out-of-process CLI pipeline with workflow concurrency and per-domain budgets.
The workflow and CLI remain available; this session did not dispatch them.

A second local path was found: APScheduler registered OAG/COB/Treasury deep jobs
and the authenticated admin endpoint queued them inside the web process. Deep
registrations are removed, admin deep requests return 409 before a job is queued,
and `_run_job` refuses any non-light invocation before discovery/artifact writes.
Light discovery remains available and was tested as a positive control.

Reachability is not deployment evidence. The configured image build uses
`context: ./backend` and backend/Dockerfile.prod copies that context, sets
ENVIRONMENT=production, and installs APScheduler/pdfplumber/pandas. It contains
backend/seeding used by the auto-seeder registry path. Production compose limits
the backend to 512 MB. The legacy main.py path imports root `etl.kenya_pipeline`,
which the backend context does not contain; that import is missing locally when
using only backend and was previously reported missing in production. The legacy
path was proven executable with a fake pipeline, not verified as a live OOM.
Actual deployed image and enabling environment were not inspected here.

## Executed validation

- Initial focused tests on main: 11 failures, one positive control; additional
  legacy scheduler/direct/admin probes: three failures before their guards.
- Final focused backend suite: 27 passed, one skipped (#325 signed-cache route
  absent on this baseline). Repository-root test invocation also passes.
- Forced two-session duplicate subscription: one new subscription, one duplicate,
  one welcome task. No real send.
- Independent hostile signature/key/dispatch probes passed after fixes.
- Broad backend run: 2,751 passed, ten skipped, nine failures. The nine integration
  failure names match a fresh untouched-main run (9 failed, 63 passed).
- Frontend TypeScript: clean. Jest: 52 suites / 545 tests pass; it reports the
  existing open-handle warning after completing its tests.

Release prerequisites: deploy this code, verify SECRET_KEY without exposing its
value, verify removed routes and signed flow on a controlled address, and confirm
heavy ingestion is owned by the dedicated job. Keep #288/#303/#322 production
close conditions open until those checks are completed by the parent release task.

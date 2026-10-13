# Batch 11 navigation evidence

This packet records a local pagination repair against the pinned launch lock.
It does not establish hosted or production acceptance. #601 remains unresolved.

## Measured behavior

The original scroll case passed 100 times before changes. Forty instrumented
original-case runs also passed, using real response delivery and bounded
history/layout/scroll observations. Neither reproduces the historical natural
failure. The historical #607 delivered-200 observation and #601 Y=100 failure
remain preserved in the committed Batch 10 scroll packet and GitHub issues.

A controlled pending response obtained the real server 200, then held delivery.
The unchanged original test failed three times at its existing URL assertion,
before the original test's scrollTo/detail/back steps, while rows 11–20 were
visible at `/counties`. Playwright had already scrolled to the pagination button.
After the repair, the same three inputs passed, issued no pagination Flight
request, and returned at Y=890–894 on `?p=2`. This establishes the client-state /
asynchronous-URL boundary; it does not prove a lost React retry caused the old
naturally completed-response failure.

Three additional real-browser controls failed before the repair: pending
response URL disagreement, failed response causing a document reload, and
competing page/page/View All navigation. The same boundary source passes after
repair. The query/hash contract failed before repair because pagination dropped
the fragment; it passes after repair. The first search-control attempt used an
incorrect `textbox` selector for a `searchbox`; that setup error is archived
separately. The corrected pre-change contract run had one hash failure and two
passes. No original assertion, timeout, sleep, skip or browser configuration was
changed.

The first explicit full Jest run retained four failures that required the old
`router.replace` transport. The county unit harness now observes pass-through
native history writes and excludes only its own external navigation inputs.
All row, URL, SSR and hydration contracts remain; positive controls also check
the resulting URL and absence of server-router calls. That21-case file and the
full147-suite Jest run pass. The one existing pending Jest test is named in the
handoff. Earlier browser runs retain their original source identity, and are
historical for this later test-harness snapshot.

The implementation publishes pure client list state synchronously using
[Next's integrated History API](https://nextjs.org/docs/app/getting-started/linking-and-navigating#native-history-api).
The county server page does not consume these query parameters. This keeps the
URL and local rows independent of Flight delivery while retaining duplicate
unrelated query values, fragments and history depth. Hydration, templates,
styles and navigation scroll code retain their launch bytes.

## Integrity versus execution

`archives/` retains raw producer bytes (some gzip-compressed without changing
the decompressed content). `archive-generators/` retains original producer
scripts, configurations and probe/test inputs. Their fixed launch paths are
historical identities, **not supported replay entrypoints**. Do not edit them to
bind old results to a later commit. Setup failures and flawed helper attempts
are historical integrity records, not behavioral reds or acceptance.

Use `tools/verify_packet.py` against the final packet manifest from the handoff:

```sh
python3 "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py" \
  --packet "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence" \
  --checkout "$CHECKOUT" --manifest packet-v2.json --integrity-only \
  --output "$EXTERNAL/packet-integrity.json"
```

The current full suite retains two original county initial-render failures.
Default verification rejects this failed acceptance; the explicit integrity-only
command above validates the recorded corpus while returning
`local_recorded_acceptance:false`. It never replaces a failed run with a green
rerun. The earlier318-pass full run retains its actual older source identity.

The output must be fresh and outside the checkout and packet. Verification
checks complete catalogue hashes, rejects symlinked/missing files and malformed
metadata, binds current recorded results to measured source bytes, reconciles
nonempty unique cases/counters, and distinguishes diagnostic/historical records
from local acceptance. It does not execute a browser or certify hosted state.
The final remote HEAD/tree is in an external postcommit binder, avoiding a
handoff that attempts to name its own future hash.

`packet-v2.json` includes the final independent reports and fresh replays.
The frozen `packet-v1.json` retains its original bytes and catalogue; verify
that historical packet in checkout `6fcaed18327d4ebdb91b475c016d81ca624deda8`,
where all755 original members are committed. Explicitly select packet-v2 for
this final checkout; the tool's historical default remains packet-v1.

Independent Spec replay passed the unchanged original case100/100, and
Standards passed the six focused cases on their first executions, with zero
retries and unchanged source/helpers. Spec's21 unit controls and live mutation
detectors, Standards'30 malformed-report guards and adversarial44 actual-corpus
checks are retained under `reviews/`. Their successful focused results do not
replace the two failures in current full-suite acceptance. The handoff links
their concise reports and records preserved reviewer metadata/setup errors.

## Fresh replay

The portable supported entrypoint is `tools/replay.py`. Prepare an explicitly
owned Linux container with label `audit_app.owner=batch11-navigation`, no host
ports, checkout bind-mounted at `/app`, and an external artifact directory at
`/evidence`. Use the runtime identities in `archives/runtime.json.gz`: official
Node 22.23.3 x64 at `/opt/b11/node-v22.23.3-linux-x64`, an owned Python venv at
`/opt/b11/python` with the launch backend requirements, and Playwright 1.58.2 /
Chromium 145.0.7632.6 from the digest-pinned image. Install pinned frontend inputs
with `npm ci` in the owned checkout/cache; never modify a shared environment.
The image digest is in the handoff. No `.env` or real provider credentials are
needed. The unchanged cohort environment explicitly sets inert local transport.

Set `CHECKOUT`, `EXTERNAL`, `OWNED_CONTAINER`, and `DOCKER_SOCKET` for the current
machine. The socket value is a Docker endpoint such as `unix:///var/run/docker.sock`,
not an author-specific path. The output directory must be a new child of the
external `/evidence` mount. Serialize fixture/server and database use.

```sh
python3 "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/tools/replay.py" \
  --checkout "$CHECKOUT" --output "$EXTERNAL/focused-replay" \
  --container "$OWNED_CONTAINER" --docker-host "$DOCKER_SOCKET" --mode focused
```

`--mode original-100` executes the unchanged original scroll case 100 times;
`--mode cohort --cohort NAME` executes each original production configuration,
including the six added cases in public. The six names are public, users,
operations, overview-audit, etl-ui and coordinator. PostgreSQL-dependent cohorts
require an owned PostgreSQL instance in the same container network namespace on
internal port 55494, with disposable `fixture` and `batch7_coordinator` databases
and the inert fixture credentials declared in the unchanged cohort module.
No host port is published: these internal ports cannot occupy another lane's
reserved host resources. Each run captures actual tracked source hashes,
HEAD/tree, child exit, exact argv and raw report/log. The child environment is
allowlisted. On timeout, preserved output identifies the exact owned container;
stop and inspect it before reuse because Docker's remote children can outlive
its client. Do not sweep unrelated processes/containers.

Linux AMD64 here runs under macOS ARM64 Docker Desktop emulation, viewport
1280×720, original configured worker counts, zero retries. The local full cohort
inventory is 323 unchanged original identities plus six focused additions.
The eleven prerequisite fixmes are reported by name in the handoff and never
claimed as executed.

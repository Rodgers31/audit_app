# Local Sentry privacy repair (#525)

Prepared 2026-10-08 on branch `codex/sentry-oauth-redaction`,
base `8276d75780604355b099f1129b75116ceb3b3712`.
This repairs the local setup helper and retained memory-transport captures.
**#525 remains open** for exact-host SDK, activation and exporter validation;
#488's CDN/proxy/access-log and operational acceptance gates also remain open.
No application installation, environment change, deployment or external Sentry
request was performed. The primary checkout was untouched.

## Policy and useful observations

`setup_sentry` now registers the same `before_send_filter` for errors and
transactions, plus `before_breadcrumb_filter` before SDK scope storage. It
disables local-variable and source-context capture, request-body capture and
profiling. Profiles are separate envelope items outside these final hooks;
the setup deliberately ignores `SENTRY_PROFILES_SAMPLE_RATE` until a profile
policy is reviewed. Default integration activation was not changed.

The final policy rebuilds operational metadata rather than trying to find
secrets by their names. It retains SDK event/trace/span correlation IDs,
timestamps, fixed operation/status values, known HTTP methods/status codes,
known built-in/owned error classes, frame line numbers/in-app flags and span
counts/timing. Unknown classes/operation labels become fixed labels. IDs and
numeric metadata are correlation observations, not authenticated provenance.

It excludes all URLs, query strings, fragments/userinfo, headers of every case,
cookies, bodies, arbitrary messages/log-entry arguments, exception text, SQL,
user/extra data, arbitrary tags, unreviewed contexts and frame variables/source. Supplied
frames and manually constructed events receive the same treatment as automatic
SDK captures. Breadcrumbs retain fixed labels, time and reviewed HTTP metadata.
This deliberately sacrifices detailed messages, paths, filenames and grouping
detail so an arbitrary private value cannot evade a field-name blacklist.

The walker permits at most 8,192 node visits, depth 16, 256 entries per mapping,
1,000 per list, 65,536 characters per string and 524,288 total string characters.
These are character limits, not byte measurements. Projections further limit
spans to 1,000, frames to 256, exceptions/threads to 20 and breadcrumbs to 100.
Repeated containers can occur in actual SDK payloads; ancestor cycles are
refused. Unsupported shapes, nonfinite numbers, invalid metadata/intervals or
oversized payloads are excluded, never returned unchanged.

SDK string enums can occur after serialization; they are bounded but never
forwarded as arbitrary labels. Exact datetime values accept naive UTC or the
stdlib `timezone`/`ZoneInfo` implementations; unreviewed timezone callbacks are
refused before invocation. Transaction type uses exact strings, avoiding
hostile string-subclass equality. Fixed Prometheus `sentry_privacy_excluded_total`
labels expose event/breadcrumb refusals. Actual SDK loss accounting additionally
records a final-hook refusal. No refusal logs its payload or exception.

The relevant options are present in the repository's minimum SDK 1.38.0
[constructor contract](https://github.com/getsentry/sentry-python/blob/1.38.0/sentry_sdk/consts.py).
Its [client pipeline](https://github.com/getsentry/sentry-python/blob/1.38.0/sentry_sdk/client.py)
serializes before final hooks and accounts for dropped events. Execution here
uses installed `sentry-sdk 2.53.0`; it does not establish the deployed version.

## Caller coverage and remaining wiring

| Surface | Coverage or unresolved boundary |
| --- | --- |
| `monitoring.instrumentation.setup_sentry` | Sole runtime SDK initializer found. Registers error/transaction/breadcrumb hooks and exclusions. No call from current `main.py` was found; deployed installation is MISSING. |
| FastAPI/Starlette automatic captures | Actual installed integrations capture callback-shaped GET and URL-encoded POST success/failure and preserve method/status/transaction counts without private query/form material. |
| HTTPX/SQLAlchemy integration spans | Final transaction projection excludes URL/query/SQL/arbitrary descriptions/data while preserving reviewed operations/status/timing. Existing wrapped-provider failure controls remain green. |
| `services.auto_seeder._record_domain_failure` | Explicit `capture_message` reaches the final event policy when this helper configured the SDK. Its ordinary logger/CDN/host outputs are not sanitized by this Sentry change. |
| `SocialRoute` and `social.telemetry` | Existing static allowlisted logging remains intact. SDK request/exception capture passes through the shared final policy independently. |
| Connection/provider and native Graph transports | Existing lower-level secret query protection is preserved; it does not replace inbound filtering. |
| Privacy data-deletion/status paths | Form/capability data and supplied/caller frames fall under global body/local/source exclusion and the final policy when installed. Runtime privacy enablement is unchanged. |
| Frontend callback, CDN/proxy/access exporters | Existing standalone browser response remains unchanged. These exporters require their own real deployed receipts; local Sentry tests cannot certify them. |

No other runtime `sentry_sdk.init` or capture caller was found in the source
inventory. Direct independent SDK initialization bypasses this helper and is
not certified. Attachments, standalone log/profile items or future SDK channels
are not accepted by this evidence; no such caller is added here.

## Executed red/green receipts

Tests were written before the product change. On unfixed base `8276d757`, the
focused module produced **16 failures plus one passing ordinary-error control**:
seven private surfaces, five malformed fallbacks/crash cases and four actual
setup/memory-transport captures. The coordinator independently reproduced all
16 failures before authorizing implementation. The coordinator retains the
execution receipts in its `BATCH_5_REVIEW` artifact:
`525_baseline_red.log`.

The coordinator independently demonstrated an unfixed forced-profile control:
one transaction and one profile item retained an inert dynamic source filename.
This was not a claim that profiling retained key/local-variable values. The
configured repaired helper, even with profile environment value 1, emits only
the healthy transaction and zero profile items.

Two additional unsupported-input cases were observed red on the first repaired
draft: a custom timezone and a string-subclass equality callback raised private
exception text. Both are now refused without invoking those callbacks; the
known-UTC positive survives. Receipt: `social-525-unsupported-red.log`.
Two further nested-object cases were independently reproduced and observed red:
`isinstance` consulted a hostile `__class__` property. The shared walker now uses
actual type identities, built-in subtype checks and native string length without
caller properties/metaclass equality. Both pass; receipt:
`social-525-class-property-red.log`.

The retained real POST form test asserts that URL-encoded `signed_request` and
capability markers reach the application in both success and error requests.
Replay against the saved unfixed helper emits one error and two transactions,
but retains the inert form marker. The repaired helper preserves the same
counts without that marker. Receipt: `social-525-forms-red.log`; replay script:
`social-525-forms-red.py` with `525_unfixed_instrumentation.py`.

Latest authored execution, from the repository root using `AUDIT_PYTHON` set
to the interpreter in the existing test environment:

```sh
PYTHONPATH="$PWD/backend" PYTHON_DOTENV_DISABLED=1 "$AUDIT_PYTHON" -m pytest -q backend/tests/test_monitoring_redaction.py backend/tests/social/test_connections_readiness_logs.py backend/tests/social/test_connections_recovery_sentry.py
```

**44 passed**, with two existing SQLAlchemy deprecation warnings. Actual installed
SDK integrations run in isolated subprocesses with inert material, a memory-only
transport and no inherited DSN/secrets. Expected event/transaction/span counts
and ordinary-error controls prevent excluding everything from passing. Actual
SDK refusal/loss accounting is exercised. The two existing evidence modules
retain explicit no-hook unsafe positive controls, then execute this setup helper.
Frame tests inspect the whole emitted event, including caller frames.

Existing provider, HTTP policy, shared boundary, telemetry and privacy HTTP
cohorts: **57 passed**, with the same two existing warnings. These plus the
focused cohort pass together as **101 tests**. `git diff --check` passes.
The coordinator separately ran **64 affected tests, zero skips**, with the
same two warnings; this overlaps the authored cohorts and is not an additional
test count. Independent Spec/adversarial review also executed 59 direct shapes,
three unsupported-object controls, 65 retained scalar-field mutations and
actual SDK captures totaling six errors, eight transactions and one span;
all passed on the reviewed policy. Its receipt is
`pr525_review_executions.json` in `BATCH_5_REVIEW`. The only subsequent policy
diff renames the character-count variable without changing behavior.
Independent Standards review passed **154 independent cases** (145 boundary
cases and nine actual SDK cases) and reran the **44 authored tests**. Its separate
Python 3.9.6 run passed **61 stdlib-only policy checks**; that is not SDK/runtime
parity on 3.9. Report: `STANDARDS_525.md`; execution log:
`social-525-independent-final.log`, retained in `BATCH_5_REVIEW` by the coordinator.
Final reviewed policy SHA-256:
`206470b5f7f8158bebd2ae3ac496200f6da6248fc61036c5661cf185a539008e`.
No outstanding local defect was reported. No commit or push has occurred at
this authored checkpoint; final Git receipts are supplied by the coordinator.

## PR #543 status compatibility review — 2026-10-08

The review's body-only HTTP-status concern was half-right: installed SDK 2.53.0
retained numeric status through trace/child data, but minimum SDK 1.38.0 core
transactions lost it because their numeric sources were response context and
legacy tags. Fixed local regression #544 is distinct from #525's deployed gate.
Fourteen retained regression cases failed on original PR head `6cddcbb` before
repair; all pass now. These include response-only errors, legacy HTTP and
status-name child tags, legacy numeric data and conflicting known aliases.

The projection now retains `contexts.response` reviewed method/status metadata,
event/span `http.status_code` tags and fixed known status-name tags. Other tags,
response headers and bodies remain excluded. Data/context fields accept exact
integer status 100..599 under `status_code`, `http.status_code` and
`http.response.status_code`; HTTP tags also accept exact three-digit ASCII
decimal text and emit canonical text. Booleans, floats, noncanonical text and
invalid ranges are refused. Conflicting aliases within one metadata container
are refused; equal aliases survive. Distinct containers/child spans are not
asserted to describe the same HTTP observation. Status metadata remains an
observation, never authenticated provenance.

Root verification: **105 affected tests passed, zero skips**, with two existing
SQLAlchemy deprecation warnings. Actual SDK 2.53.0 captures include GET and form
POST 200/500 response contexts, plus five transactions and five children with
200/418/422/500/503 in both response/data and HTTP tags. Whole emitted payloads
exclude the inert private markers. SDK 1.38.0 was separately executed from
official immutable source commit
`2904574dea5cb3d1f330cb549f269c0eda0a51a7`, without installation: two transactions
and two children preserve numeric 200/500 and fixed status names after repair.
The identical core replay on original `6cddcbb` loses both transaction numeric
codes. This is SDK-core evidence, not old-SDK/current-framework parity.

The startup inline finding re-litigates the scope recorded at the start of this
handoff: **“No application installation, environment change, deployment or
external Sentry request was performed.”** An isolated execution with dotenv
disabled, inert settings, temporary SQLite and sockets blocked constructed the
real `main.app` with **zero Sentry init calls**. An explicit helper call made
exactly one intercepted init call and registered both final hooks and the
breadcrumb hook. Lifespan/background tasks and exporters were not executed.
The repository's missing automatic call is acknowledged; actual deployed
initialization remains unverified under #525/#488. This review does not add it.

The coordinator retains `status_baseline_red.log`, `status_final_green.log`,
`minimum_core_original_red.json`, `minimum_core_final_green.json` and
`startup_receipt.json` in `PR_543_REVIEW`. Final policy SHA-256:
`e238e15ff30521e04a05ef3d802ba7e380d5c69c05575d4f4865bc66f8f77146`.
Historical execution counts above overlap these checks and are not additive.

Independent Standards verification passed 978 combined checks, including 678
status/alias inputs, earlier retained boundaries and authored cohorts, plus 12
separate actual SDK cases. Independent Spec verification passed all 102 declared
contract cases and characterized three cross-container observations without
claiming provenance/consistency. Its real GET/POST run retained five transactions
and two errors with exact 200/422/500 statuses and no private markers; the prior
six-error/eight-transaction/one-span controls also passed. These executions
overlap the root suite. Both axes found no remaining local defect. Separate
reports and categorized receipts are retained in `PR_543_REVIEW`.

## Exact-host acceptance remains pending

Local helper/configuration: VERIFIED_BY_EXECUTION for installed memory transport.
Exact deployed SDK/options, whether/where this helper is installed, Sentry
exporter routing/custody and ingress/CDN/proxy/access redaction: MISSING/BLOCKED.
Keep the original Batch 5 unsafe capture receipts as historical evidence.

Next operator step: identify the exact host/build/SDK and actual initialization,
then retain authorized inert captures through each deployed exporter and upstream
layer. Prove absence in success/failure paths and healthy event emission, review
custody/retention and make a separate acceptance decision. This local repair
authorizes no production tracing, callback installation, publishing or deletion.

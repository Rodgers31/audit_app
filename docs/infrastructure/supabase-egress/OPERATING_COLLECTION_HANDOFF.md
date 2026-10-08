# Operating collection handoff — 8 October 2026

#481 remains open. The real sources below establish current identity, accrued
usage and a partial host inventory; they do not establish seven representative
days, billed savings or acceptance of Free/worker hosting. Worktree:
`/Users/roger/.codex/worktrees/social-operating-evidence/audit_app`; branch:
`codex/social-operating-evidence`; fetched base:
`bd46832156cb921173fea32d9d9698d696a676dc`. The dirty primary checkout was read
only. Delivery commit and draft PR are recorded in the session's final handoff.

## Real receipts available now

[Sanitized observation receipt](collection/2026-10-08-observations.json) retains
the source, observation/capture bounds, identity, method, selected scope, unknowns
and transcription status. It is a manual record of actual visible readbacks,
not an authenticated portable provider export or an evaluator packet. Hashing
or editing this file cannot turn it into production acceptance.

| Source observed on 8 October | Actual readback | Limits |
| --- | --- | --- |
| Supabase Auditors organization `hdyktpafltykrgpkcvgt`, **All projects**, Pro | Cycle 8 Oct–8 Nov; summary **3.641 / 250 GB** uncached; no exceeded-Pro warning | Provider refresh can lag one hour. Billing timezone, refresh cutoff, rounding convention and owner reserve were not exposed/accepted. Keep the accrued amount; do not replace it with a quieter future week. |
| Same daily chart | 8 Oct Shared Pooler **3.391 GB**, **100.0%** displayed | Incomplete day; chart includes cached traffic; rounded percentage is not literal zero other traffic. Summary/chart differ by 0.250 displayed GB. No reconciliation or invented service zeros. |
| Supabase `audit_gava`, project `xznjxwrkbkahwtnbstbj`, main PRODUCTION | Nano; max **200 concurrent pooler clients**; **15 backend connections per user+database**. Infrastructure showed **7/60 database connections** | Different kinds. Neither 15 nor 7/60 is the application's client limit or evidence of peak occupancy. No actual pooler client occupancy or accepted connection reserve. |
| Render service `srv-d6hr3t5m5p6s73bomqu0` | Live `dep-db3oskc9v7es73dtuvc0`, SHA **2d3cd5959df1914bf068cb0381057d1bcbbabf81**. Web Shell `RENDER_GIT_COMMIT` independently matches. Auto-deploy disabled. | This readback is older than main. `git merge-base --is-ancestor 4d22e828 2d3cd595` returned 1: #510 is **not** in the live SHA. #487/#505 are in it. Exact deployment instant was not read. No deploy was triggered. |
| Render Compute and selected instance `44sdb` | One selected Starter replica; displayed $7/month, 0.5 CPU/512 MB. `/proc` census: Gunicorn master PID 1 and web child PID 7. Live `database.py` AST: pool 5 + overflow 10. `AUTO_SEEDER_ENABLED=false`. | One known web process implies **15 client connections maximum** for this replica; the master is not another established DB pool. Other hosts, workers, ingestion, developer/admin clients and reserve remain missing. File literals plus census are not measured concurrent occupancy. Owner cost/always-on worker acceptance remains missing. |
| Render Logs, Last hour, bounded visible DOM | 195 visible text lines, eight HTTP-access lines, zero matched boot/warmup lines | Virtualized/filtered visible rows are incomplete. Zero matching markers cannot mean zero restarts/warmups for the hour/day. No cache hit/miss counters or DB-byte correlation. Raw paths/IPs/payloads were not exported. |
| GitHub REST permissions | `enabled:false`; latest retained run 37825962018 was completed | Actions-off days do not represent an enabled nightly profile. No dispatch/enablement/status fabrication. |

The Web Shell executed only a bounded `/proc` census, selected nonsecret env
readbacks and AST parsing of the deployed database configuration, without
importing the application. `ps` was unavailable; its failure was retained, then
the Python census succeeded. A first substring classifier included the
diagnostic Python command as Gunicorn; the retained receipt uses the corrected
exact process-name census and excludes that diagnostic process from web demand.
No existing process was stopped. Logs and UI observations generate ordinary
provider requests; measurement is not asserted to be zero-cost.

Existing local configuration contained ordinary DB_* credential keys, but no
dedicated egress/read-only statistics credential. Only key names were examined;
credentials were not printed or copied. No production SQL was executed in this
session. Earlier 13:17:31–13:31:12 UTC snapshots and 200-row decoded estimates
remain historical evidence in [the #510 investigation](2026-10-08-public-query-transfer.md).
The reset was April 22; the selected group was quiet apart from internal pooler
auth. They neither cover today's full traffic nor authenticate a current bill.

## Collection and preparation seams

`scripts/verification/social_operating_collect.py` defaults to `PLAN_ONLY`.
Both direct calls and CLI require explicit execution before reading credentials
or connecting. It accepts an exact project/database OID and 1–50 explicit
user/query/top-level identities; no query text, arbitrary SQL, application-table
sample, discovery scan or environment DSN. Its initial transport is the exact
`db.<project>.supabase.co` direct endpoint, TLS `verify-full`, explicit CA and
dedicated reader. Pooler/custom-host transports are unsupported, not automatic
fallbacks. A direct diagnostic does not measure the Shared Pooler bill.

The private credential JSON has only `user`, `password`, `sslrootcert`; it must
be owned by the current user, private, regular, nonsymlinked and <=8 KiB.
Credentials are passed in driver arguments and never emitted. Inherited PG*
variables are refused to prevent libpq redirection. Read-only repeatable-read
sessions have 5-second statement/connect/idle-transaction deadlines and
1-second lock timeout. Catalog readback rejects administrative/inherited admin
roles, table/column write privileges, relation ownership even after revoked DML,
schema CREATE and database CREATE/TEMP. Application schemas beginning `pgx_`
remain subject to the checks; only the literal `pg_` catalog prefix is excluded.
The reader must already be approved/provisioned; this task provisions none.

Fixed catalog/statistics queries select only identity, settings, extension
support, exact reset/deallocation values and allowlisted calls/rows/stats_since.
Each SELECT has a 2-row limit and fetches at most three rows to detect overflow.
Outputs are capped at 64 KiB; captures over five minutes are refused. Sessions
roll back and close on success/failure. Unsupported history remains explicit
partial evidence. Query digests bind database/reader/server/extension identity
and user/query/top-level tuple; no SQL text or caller subject is returned.

Fresh local collection distinguishes `TLS_DATABASE_SESSION_READBACK` from
`INJECTED_TEST_DRIVER`. Its payload hash binds the actual emitted snapshot and
capture occurs after the real snapshot end. TLS authenticates the selected
endpoint/session readback; it does not verify an organization bill, deployment
or caller. An imported file is always **unverified**: hashes are not signatures
and a person can reseal a fabricated TLS label. Unknown/history disclosures are
validated from the data, rather than trusted from a self-described status.

`scripts/verification/social_operating_prepare.py` provides:

- `coverage(records, expected_identity=..., first_day=..., as_of=...)`: seven
  civil-day slots, with missing records/sections left missing, exact receipt
  periods and DST lengths. `covered_days` counts section-complete closed slots;
  `window_missing` separately exposes missing API/publication/deploy/cache/restart
  activity. It always returns BLOCKED/full acceptance pending, even for seven
  fabricated or complete declarations.
- `delta(before, after, expected_database_sha256=..., start_at=..., end_at=...,
  as_of=...)`: matching allowlisted shapes only, stable reset/deallocation and
  per-shape stats_since, monotonic counters, actual endpoint brackets and capture
  ends. Equivalent UTC offsets compare as instants. Missing/reset/evicted shapes,
  payload tampering and windows extending outside actual captures block. Valid
  imported deltas retain exact per-shape observed times, `interval_exact:false`,
  caller attribution unverified and provider bytes unmeasured. They include the
  bracket margins; do not assign them to a narrower workload or create a rate.

No adapter auto-promotes these artifacts into evaluator authority. The unchanged
[full evaluator](OPERATING_ACCEPTANCE.md) still checks accrued charges, all
workloads, matched social bases, DST, conservative rounding, protocol zero and
future growth/overlap, hosting and connection reserves. Preparation neither
relaxes those gates nor changes its schema. Protocol bytes, provider-meter bytes,
decoded JSON estimates and cumulative calls/rows remain different quantities.

## Dated coverage ledger and continuation

**Zero complete representative post-rollout days are available.** Billing
timezone is missing, #510/current-main rollout has not been observed, intended
worker hosting/behavior has not been accepted, and Actions remains off. The
following seven consecutive slots are a continuation ledger, with missing
evidence explicitly recorded; they are not successful measurements or promised
rollout dates. Oct 8 is partial and is excluded from closed-day coverage.

| Civil date in confirmed billing timezone | Provider daily + service split | Build/readback + API/cache | Nightly/worker | Restart/deploy | Coverage |
| --- | --- | --- | --- | --- | --- |
| Oct 9 | Missing | Missing | Missing | Missing | Pending |
| Oct 10 | Missing | Missing | Missing | Missing | Pending |
| Oct 11 | Missing | Missing | Missing | Missing | Pending |
| Oct 12 | Missing | Missing | Missing | Missing | Pending |
| Oct 13 | Missing | Missing | Missing | Missing | Pending |
| Oct 14 | Missing | Missing | Missing | Missing | Pending |
| Oct 15 | Missing | Missing | Missing | Missing | Pending |

Earliest review for these seven **closed** slots is **Oct 16**, after the final
midnight in the confirmed billing timezone and provider refresh. If the accepted
build/workload first spans a later full day, shift all seven slots. The earlier
issue's Oct 15 calendar review is not a pass: today's partial rollout/day cannot
be counted as a full representative day. Actual approval/enablement remains a
separate operator gate. Ordinary restarts/deploys may be observed; none should
be forced to fabricate coverage. Render's visible maintenance notice for Oct 13
20:00 CDT/Oct 14 01:00 UTC should be annotated if it affects the eventual window.

Manual operator protocol; no recurring job or automation was installed:

1. Read back the accepted backend SHA, exact deployment instant, every replica
   and actual command/process pool. Confirm billing timezone, exclusive cycle
   boundaries, organization-wide uncached allowance, decimal units/rounding and
   owner reserve. Record actual observation/refresh cutoffs, not capture time as
   a substitute for a lagging provider period. Obtain owner hosting/cost and
   workload acceptance separately. A rollout or enabling jobs is not authorized
   by this collection handoff.
2. Retain each closed day's provider total and complete services plus cycle-to-
   date accrued usage through an exact cutoff. Repeat after the documented
   refresh delay if summary/breakdown disagree. Unknown services stay unknown;
   cached egress and R2 are separate. Preserve spikes and prior charges across
   every quiet-week forecast. A 3.641 GB display is not exact 3,641,000,000 bytes;
   require the rounding rule or a confirmed exact export before evaluator input.
3. Inspect existing bounded runtime logs/counters for API requests, cache hits/
   misses, ordinary startup/warmup/recycles, ingestion and intended worker
   uptime/scans/heartbeats/active/retry/recovery behavior. State each log's
   filtering, sampling/virtualization and retention gaps. Actions-off or absent-
   worker days do not represent the proposed enabled profile. Do not dispatch
   work, restart a host, probe social mutations or load application tables merely
   to fill a slot. A real-worker pilot needs its own authorization/gates.
4. If an approved statistics reader and retained explicit query IDs exist, use
   the collector with nonsecret config and private credential files outside Git:
   `python scripts/verification/social_operating_collect.py --config CONFIG.json`
   previews only; adding `--credential-file PRIVATE.json --execute-read-only
   --out NEW.json` performs one bounded collection. No automatic retry or
   recurring schedule. Preserve exact source fingerprints, reset, deallocation,
   stats_since and snapshot/capture ends. Missing support blocks attribution.
5. Pair snapshots only across an observed normal interval and use `delta`.
   Retain brackets and concurrent-client ambiguity. For social measurement use
   a bounded directional protocol/provider source including connection setup,
   idle/pre-ping, busy operations, retries/recovery and restart traffic, under a
   consistent basis for days/accrued usage/future units. Decoded fixture widths
   cannot substitute; exact zero protocol with active traffic is contradictory.
6. Run coverage CLI with `--records DAYS.json --expected-identity IDENTITY.json
   --first-day YYYY-MM-DD --as-of TIMESTAMP`. Fill only actually retained dates;
   missing slots remain null/missing. Then independently inspect source artifacts
   and prepare the full evaluator packet, including hosting, accrued usage and
   future increments. Run its existing CLI. A candidate still consists of
   unverified assertions requiring owner/source review, never authorization.

## Attribution and owner decision packet

| Client family | What is established now | Smallest additional measurement |
| --- | --- | --- |
| API | One live web child; eight visible HTTP lines in a partial log view | Bounded same-interval query deltas plus complete request/cache-family counters; callers sharing a DB role/shape remain ambiguous. |
| Startup/warmup | Deployment history is accessible; no matched warmup/boot in the partial Last-hour view | Retained ordinary boot/recycle timestamps plus cache-fill counters and matched query deltas around the next normal event. No forced restart. |
| Ingestion | Live auto seeder false; Actions permission false | Actual ordinary ingestion identity/run interval with bounded deltas and source/row correctness receipts. Actions status alone does not exclude developer/manual ingestion. |
| Social worker | No accepted worker host or actual transfer source | Approved inventory and real directional setup/idle/busy/retry/recovery measurement; source must match the future enabled profile. |
| Developer/admin/diagnostics | Production credential keys exist locally; this collector did not use them | Operator inventory of intended clients and retained nonsecret application labels; current labels cannot reconstruct historical callers. |

Shared Pooler is a transfer path, not a caller. No percentage allocation is
established among these families. `pg_stat_statements` keys database/user/query/
top-level identity, not application_name. A shared role/shape cannot distinguish
API from ingestion/developer traffic even with stable counters. The smallest
prospective interface need is reviewed nonsecret caller labels plus per-family
bounded counters/transfer telemetry at existing clients, or separate approved
reader/client roles. That change belongs to runtime owners, outside this lane;
this session changed no pools, workers, connection/media services or public/ETL
queries. [PostgreSQL statistics contract](https://www.postgresql.org/docs/18/pgstatstatements.html)
and [Supabase connection kinds](https://supabase.com/docs/guides/database/connection-management).

The measured/pending decision packet is **BLOCKED**. Planning targets remain
120 MB/day total and 200 MB/cycle social, subject to actual allowance/reserves.
Current Pro allowance is observed; Free downgrade, alternative hosting, always-
on worker cost and full connection headroom are not accepted. The 15 known web
ceiling cannot be compared with an assumed reserve/unknown other processes to
declare capacity. No purchase, downgrade, deployment, migration, job activation,
production write or social mutation occurred.

## Verification and delivery receipts

Executed with the existing Python runtime and `PYTHON_DOTENV_DISABLED=1`:

- Unchanged evaluator baseline: 163 passed; two existing SQLAlchemy deprecation
  warnings. Its synthetic fixture remains blocked.
- New author collection/preparation suite: 85 cases, including direct/CLI
  defaults, SQL/row/size/identity guards, secrets/files, copied days, historical
  spike preservation, incomplete workloads and spring/fall civil days.
- Independent adversarial suite: 91 cases; separate 190-expectation hostile
  direct-call matrix, zero unexpected accepts and a seven-statement positive
  fake-driver control. Fabricated/resealed TLS claims and seven copied/supplied
  declarations never grant authentication or acceptance.
- Nine independent regressions were observed red (six missing-history/status
  consistency; three equivalent-offset instants), reproduced by the parent,
  fixed centrally and rerun green. An additional all-zero ordinary-workload
  ledger regression was observed red before adding aggregate missing coverage.
- Actual SQL lane: 11 passed against this scope's private PostgreSQL 17 server
  on loopback **61281**, database `social_operating_owned_fixture`; catalog and
  statistics SQL, missing shapes, app writes/schema CREATE/BYPASSRLS/CREATEDB
  refusal and connection closure. Four column-only/`pgx_` privilege regressions
  and a relation-ownership/revoked-DML regression were reproduced red, then green
  with the final guard. Explicit injected test transport remains
  labelled; this is not production TLS/protocol/provider evidence. The server
  and database belong only to this scope; coordinator port 62124 was untouched.

- Final combined command: `SOCIAL_OPERATING_OWNED_PG=61281
  PYTHON_DOTENV_DISABLED=1 <existing-python> -m pytest --noconftest
  backend/tests/egress/test_operating_acceptance.py
  backend/tests/egress/test_social_operating_collection.py
  backend/tests/egress/test_social_operating_independent.py
  backend/tests/egress/test_social_operating_owned_postgres.py -q`:
  **350 passed, zero skips, zero warnings** on Python 3.13.9. This includes the
  unchanged evaluator's 163 cases, author 85, independent 91 and actual SQL 11.
  `--noconftest` isolates these explicit standalone tests from application
  startup; it does not establish full-application runtime compatibility.
- Final-source standard-library compatibility: Python **3.9.6** and **3.12.15**
  each passed the 190-expectation hostile collector matrix and missing-day /
  blocked-synthetic preparation smoke. The Linux 3.12 run used the existing
  image with network disabled and a read-only worktree mount. These checks do
  not exercise production TLS or the entire application on those runtimes.
- Independent adversarial verdict: pass (91 tests and 190 hostile expectations).
  Standards re-review: pass, including independent 11/11 actual PostgreSQL
  checks after the privilege fixes. Spec review: no actionable findings; 176
  offline cases and 14 independent direct-call probes passed. Earlier reviewer
  runs loaded application conftest and reported two existing SQLAlchemy warnings.
- The scope-owned `audit-social-operating-evidence-61281` container was removed
  after verification; an exact-name Docker inventory returned no container.
  No coordinator server or existing production process was stopped.

[Sanitized verification receipt](collection/2026-10-08-verification.json) retains
commands, runtime/count/verdict facts and source/log hashes. Local raw red/green
logs and hostile scripts are retained in the scope-owned session artifact folder
`/Users/roger/.codex/visualizations/2026/10/08/01a11d17-d085-7980-b6e5-05b6adab5dee/operating-evidence`.
The delivery SHA and draft PR are recorded in the final session handoff.
No new proven shared-query defect was discovered; #481 already tracks the
unfilled operational gates. No unrelated issue was closed or duplicated.

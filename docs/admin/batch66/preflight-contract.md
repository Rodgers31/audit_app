# Manual ingestion preflight contract

This lane adds metadata inspection and a cost planning interface. It does not
activate ingestion or certify production. Frozen base:
`924f1a4f27e1952f97d2291d8878d88603132237`. Acceptance references: issues
[#583](https://github.com/Rodgers31/audit_app/issues/583),
[#699](https://github.com/Rodgers31/audit_app/issues/699),
[#481](https://github.com/Rodgers31/audit_app/issues/481) and
[#778](https://github.com/Rodgers31/audit_app/issues/778), including B65's latest
comments and NIGHTLY_READINESS. Historical issue paragraphs do not supersede
those comments. No parent acceptance issue is closed by this delivery.

## Admission and identity

The shipped `preflight-admission.json` is disabled with absent expectations.
The workflow also refuses without the independently owner-provisioned nonsecret
`INGESTION_PREFLIGHT_APPROVED_WORKFLOW_SHA` variable; it is absent in author work.
The hash-bound shipped policy remains disabled. Repository
Actions must stay globally OFF; no hosted run is part of this author work.
An invalid dispatch fails explicitly, rather than skipping a job green.

The fixed implementation and admission checkout SHAs are independent of dispatch
inputs; dispatch has no inputs. A policy is committed after the implementation
identity exists and refers to that already-known implementation HEAD. A later
workflow commit pins both, with the policy's exact SHA256. The CLI hashes and
parses the same bounded raw bytes once, preventing a second-read replacement.
This avoids a policy trying to name the commit containing itself.
The owner may provision the exact workflow SHA only after the reviewed workflow
commit exists, during a separately approved activation window. No variable is
created by this delivery. A selectable dispatch ref cannot replace that pin.
Only reviewed code from that immutable implementation checkout may receive the existing
DATABASE_URL secret, in the final inspection step after admission. No credential
is used for checkout, installation or uploads. A later activation change must
pin the accepted implementation commit, the approved main dispatch identity and
exact nonsecret expectations. The author-phase pin is a deliverable identity,
not an assertion that new code has already been accepted into main.

Expectations are never learned from the target by the inspector. Require exact
database name/OID, role name/OID, endpoint, TLS mode, supported major version17,
revision, structural catalog hash, reviewed source HEAD and SHA256 for every
required source file. The structural hash includes column types/order/nullability,
relation kind, owner and RLS flags for the six inspected tables. It is NOT a full
schema/constraint or whole-database equivalence certificate. Existing rollout
observation/reconciliation machinery remains responsible for that broader gate.

Hosted mode only permits direct `db.<20 letters>.supabase.co:5432`, verify-full
with system CA roots. URLs with arbitrary query options/services/certificate paths
or fragments refuse; the existing secret may therefore require separately
reviewed compatibility work, without printing or copying it. No secret value was
read in author work. The local exception is exact loopback port56972 and an
explicit `b66_preflight_` fixture identity, visibly recorded with TLS disabled.
It cannot establish hosted TLS, permissions, production identity or usability.

No repository workflow alone can protect repository secrets from a malicious
administrator rewriting its definition. Main governance, exact source review,
fresh controls and keeping Actions OFF are the external trust boundary. This
delivery does not add environments, grants, secrets or approval settings.

## Read and resource boundary

The invoked Python API validates the same config/execute boolean on direct calls.
Connection options default to read-only; the invoked transaction explicitly begins
REPEATABLE READ READ ONLY. Before any observation, fixed SET LOCAL statements
enforce timeouts, catalog search path, row_security=off, parallelism0 and64kB
work_mem. Runtime readback must match. The role may have no application write,
owner, privileged membership, schema CREATE, database CREATE or TEMP capability;
full stats visibility is required, never granted by this tool. RLS-filtered reads
fail instead of treating an invisible claim as absent.

Only fixed allowlisted catalog SQL and seven bounded EXISTS predicates execute.
No application record, query text, credential, financial value or receipt payload
is selected. Other non-idle client sessions, prepared transactions, unfinished
commands/nonterminal jobs, retained claims, dispatch ownership/ready bits and worker
ready state refuse. Idle external clients, restart channels, background/provider
writers and changes after the snapshot are not certified. Every-writer custody
always remains UNMET. Receipt authority must be an accepted independent expected
identity, but no storage request is made: its live gate remains NOT_OBSERVED.

One connection, no pool/retry; workflow concurrency1; one parent and one owned
fresh interpreter, with at most one database worker. No libpq connection is
opened in the parent or inherited via fork. The fixed supported workflow runtime
is Python3.12.15 x64, installed by SHA-pinned setup-python; all Python and pip
steps explicitly invoke that action's selected interpreter.
Whole invocation30s, connect3s, statement2s, lock500ms, idle-transaction3s,
idle-session5s, workflow5min, inspection step1min. At most24 SQL commands plus
one cleanup rollback, with20 commands/11 SELECTs on the current path. At most256
total rows and65536 decoded result bytes. Schema query LIMIT257 is an overflow
sentinel. Fixed metadata scalar sizes bound network results; decoded bytes are
not wire/provider billing measurements. The workflow downloads no source files
from government hosts and makes no provider/storage HTTP requests. It performs
no migration/bootstrap/seed/revalidation/upload/account mutation.

The Python deadline includes source admission, inspection, cleanup and publication,
and restores the previous signal handler. Connection work runs in a fresh
interpreter with bounded private stdin/stdout pipes, a minimal environment and no
credential arguments/files. The parent reserves up to1second INSIDE its30second
budget for forced termination and reaping. It accepts a report only after that
exact worker has exited and been reaped; blocked rollback/close, forced cleanup,
late output or unconfirmed cleanup always refuse. Cleanup errors are retained.
The unreaped leader reserves its identity while a bounded PID/PGID-only census
checks that exact owned group. Any descendant forces termination and refusal;
acceptance requires reaping and group absence. The short local census helper
has bounded output and shares the original deadline. The process-concurrency
budget denotes one inspection run/database worker; its parent and census helper
are supervision overhead. This does not sandbox arbitrary untrusted native code.
Database timeouts remain enforced inside the actual invoked transaction;
idle_session_timeout is also set locally and read back as5s. The private worker
entry refuses without the supervising parent context and is not a public API.
The hosted step/job deadlines are the final process boundary. Resource caps do
not certify current provider capacity or prevent other clients consuming it.

## Verdicts and publication

`OBSERVED_READ_CHECKS_ONLY` / exit0 means exactly that all declared bounded read
checks executed with matching expected identities. `safe_to_write`,
`production_authorized`, `free_ready` remain false; custody stays UNMET and live
receipt certification NOT_OBSERVED. REFUSED exits1; admission/CLI/publication
failure exits2. Missing/malformed/unsupported/unknown observations cannot pass.
Errors use fixed codes, without underlying exception strings or traceback text.

Reports bind generator bytes, selected source bytes/HEAD, canonical config hash,
and actual policy raw-byte hash on CLI attempts, including refusals. Unsupported
config/source observations retain explicit binding-unavailable markers. Reports bind
Python and driver runtime, time, counts, limits and observation scope. These are
content bindings, not signatures: imported reports are UNVERIFIED_WHEN_IMPORTED.
Private worker reports must also satisfy the complete exact shape/type/binding
contract: success requires empty errors and complete seven-check observation,
supported runtime, fresh timestamp and bounded nonzero counts. Unknown failures
or malformed/contradictory reports refuse without propagating arbitrary text.
Do not import an edited JSON status as authority. Optional outputs must be fresh
external regular files with bounded exclusive creation, no symlink components or
overwrite, and byte-for-byte readback. No hosted artifact upload is configured.

## Cost readiness interface

`python -B scripts/verification/ingestion_preflight_readiness.py` returns BLOCKED
and exit1. It records retained B65 facts:90.1decimalMB database,43.126decimalGB
uncached cycle, cached0/MAU1. This includes earlier releases and diagnostics;
there is no optimized daily rate.500MB DB fits at the retained instant, with
409.9MB before growth/reserve; historical cycle uncached is8.6252times5GB.
WAL/system/provisioned disk are distinct categories.

The interface delegates packet/expected identity/explicit as-of to the existing
`evaluate_social_operating_budget.py`, rather than implementing another egress
acceptance verifier. Use its complete closed-day/representative/caller/reserve
and receipt contracts. `future_increments` workload=nightly carries measured
source units/bytes and explicit already-included/additional overlap. A separate
measured recurring backup traffic/storage/retention forecast and owner-managed
offsite policy remain required: Pro daily backups are not supplied by Free.
Decoded selected bytes and protocol proxies cannot certify billed savings.
Even an existing evaluator candidate leaves this planning interface BLOCKED.

Unresolved decision checklist: provider day/cycle/cutoff/rounding; full caller
and peak inventory/operator reserve; representative active source+backup traffic;
memory warning #778/shared500MB RAM; storage/retention/recovery and inactivity
policy; recurring offsite backups; fresh custody and owner plan decision.
Official Free allowances are500MB database,5GB uncached plus a separate5GB
cached bucket,1GB storage,50kMAU, shared500MB RAM and inactivity pausing.
Preserve current Supabase plan/spend cap and Vercel$1PauseOn. No downgrade,
export/backup, resource addition or support message is performed.

Sources checked during authoring:
[Supabase pricing](https://supabase.com/pricing),
[backups](https://supabase.com/docs/guides/platform/backups),
[PostgreSQL17 connection defaults/read-only/timeouts](https://www.postgresql.org/docs/17/runtime-config-client.html),
[GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Future run / abort / observation plan

1. Coordinator obtains fresh control readbacks: Actions/other workflows OFF,
   Preview Branch Tracking disabled, automatic reviews off, current main/head,
   budget/default-off state. Owner separately approves a bounded hosted read.
2. Independently certify exact secret target/role/TLS and full accepted schema;
   do not read/copy/export the secret in an author chat. Review every writer and
   restart channel and the existing custody/receipt operator contracts. Retained
   Render stop/restore fixtures keep their disclosed scopes.
3. Review/merge a separate admission update with exact expectations, source
   hashes, immutable implementation checkout and main dispatch identity. The
   dispatch-definition guard must match the approved definition, not a selectable
   branch. After the workflow commit exists, independently provision its exact
   SHA in the nonsecret owner-admission variable; remove that admission on abort.
   Keep all other Actions workflows and social switches OFF. Do not
   treat the current disabled sample as an executable production plan.
4. For that separately approved window only, invoke one manual read-only run,
   no retries or scheduled cadence. Observe first admission refusal or bounded
   read report immediately. Any identity/TLS/schema/role mismatch, unknown,
   retained/active state, timeout/cleanup error, private output or budget breach
   aborts. Cancel the exact owned job if needed; restore and independently read
   back all workflow/repository OFF controls. No retry that learns expectations.
5. Verify the report's generator/config/source/runtime against accepted bytes;
   verify connection cleanup and no mutation. Imported content is not authority.
   A pass still needs fresh independent every-writer/receipt certification.
6. Native preview, one source ingest, unchanged repeat/idempotency, provenance,
   storage/cache/UI and representative capacity/cost are later separately
   authorized operations. No safe-to-write or Free-ready claim follows this read.

Abort/rollback here means stop the owned process, allow transaction rollback and
close, disable the scoped workflow/repository, and retain sanitized refusal.
No application/schema/access repair is attempted. Source rollback is reverting
the new additive workflow/tool/admission commit before any future activation;
there is no ingestion state to undo from this tool.

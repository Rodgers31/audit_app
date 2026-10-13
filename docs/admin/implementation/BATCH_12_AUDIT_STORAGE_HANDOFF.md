# Batch 12 durable admin audit storage handoff

Updated 2026-10-12. Addresses #611, parent #545. Durable storage, production-route
pagination and actual browser acceptance are implemented and verified locally.
The unchanged default launcher passes on clean commit `596f015`: 17,197 native
cases, 15,730 passed, 1,467 prerequisite skips and zero failures/errors. All 951
required cases pass. The human approves nine formerly skipped media cases now
passing with installed FFmpeg; there are no new skips. Six original hosted
generated-file scanner cases pass separately against exact native generated
bytes and are not added to the canonical count. Native cleanup is verified,
including both retained clusters and removal of the approved temporary image tag.
The coordinator owns independent combined hosted acceptance and the separately
reviewed production release under #583/#554. This draft supplies no production
migration, certification, provider or writer-activation authority.

## Source and ownership

- Accepted base: `dfd18032b6f38d57bfaa6f66d0feac218189f54c`, tree
  `3a680eef19822ef0ac83aa6890c3b41deee97058`.
- Product implementation: `e9c2ec91cf4ad8ae49171d59503282125214a5d2`.
- Clean final fixture checkpoint: `596f01570baaf9cb9519604f087b42700501a826`, tree
  `71d62b045a8374dc86e7bff8574c66aeda649082`.
- Branch: `codex/batch12-durable-audit-storage`.
- Owned checkout:
  `/Users/roger/.codex/worktrees/batch12-durable-audit-storage/audit_app`.
- External evidence directory (`EVIDENCE` below):
  `/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_12_LAUNCH/AUDIT_STORAGE`.
- `EVIDENCE/MIGRATION_CONTRACT.json` binds the migration design, exact source
  hashes and final commit/tree. `EVIDENCE/STATUS.md` records publication and the
  PR URL. The last commit changes this handoff only; its identity is external
  to avoid a self-referential hash. All tested product/fixture bytes are unchanged.

The coordinated exception in `BATCH_12_LAUNCH/COORDINATION.md` covers setup in six
existing writer fixtures. The remaining changes are owned audit source, two
necessary migration expectation modules, three durable test modules, an API
fixture, the fixture helper, browser config and this handoff: 19 paths total.
The primary checkout, dependency files, existing dispatch/reconciliation writer
source, router registration and global workflow wiring were preserved.

## Implemented storage and route contract

Revision `a611b12a0001` descends directly from accepted `e602b11a0001`. It adds
`admin_audit_provenance` and singleton `admin_audit_storage`, plus a validated
positive audit ID constraint. Existing audit columns and writer INSERT shapes
remain compatible. An ALWAYS AFTER INSERT trigger atomically stores ordinary
full-width `pg_current_xact_id()` and the storage incarnation in the writer's
transaction. Raw SQL and ORM inserts use the same trigger. Savepoints preserve
root provenance; rollback removes the audit row and provenance together.
Migration function bodies are frozen in the revision.

ALWAYS BEFORE UPDATE/DELETE/TRUNCATE triggers enforce append-only log/provenance.
All three tables use RLS and private ACLs. Restricted NOLOGIN groups have six
false role flags, no parent memberships and no public-schema CREATE authority.
The reader receives SELECT on all three tables and EXECUTE on the identity
function. The writer receives log SELECT, INSERT on its seven existing input
columns and sequence USAGE; it cannot write IDs, provenance or storage state.
Existing owner writers retain their transaction ownership. PUBLIC and existing
anon/authenticated table/column ACLs are revoked. Unsafe effective privileges
refuse migration or reader admission.

The already-mounted production router uses a separate restricted reader engine
from `ADMIN_AUDIT_DATABASE_URL` at REPEATABLE READ. It does not switch a writer
session's role. Admission checks actual isolation, privileges, RLS, validated
constraints, permanent ordinary tables, exact policies and frozen ALWAYS
triggers. Admission, snapshot capture and reads share one repeatable-read
population, including concurrent storage de-certification.

Admission additionally requires externally held `ADMIN_AUDIT_INCARNATION` and a
32-byte hex `ADMIN_AUDIT_BOOKMARK_KEY`, certified singleton state, actual system
identifier/database OID/timeline and no recovery. Migration assigns a fresh UUID
with `certified=false`; it does not backfill historical root xids or certify
production. Any unknown, mismatched or invalid provenance refuses the entire
dataset before filters. Prepared transactions in the current database refuse.
Storage failures return the existing sanitized private HTTP 503 response.

Signed v3 bookmarks bind actor, incarnation, full `pg_snapshot`, UTC capture time
and ID ceiling. Existing expiry, bounds, redaction, ordering, filter transfer,
authentication and private/no-store guarantees remain. Visibility uses the stored
root xid with `pg_visible_in_snapshot`. The ceiling is computed over the visible
population before client filters, including an initially empty filter. SQLite
retains its local behavior and supplies no PostgreSQL certification.

## Maintenance, restore and rollback limits

- Actual epoch-one SQL controls pass for lower-ID late root commit, raw writes,
  savepoints, concurrent pages, freeze and VACUUM FULL, preserving issued history.
- History mutation/retention, bypassing the capture/immutable trigger, invented
  legacy backfill and prepared transactions are unsupported and refuse admission.
- Actual native logical dump/restore copies history into a different database
  OID. Both initial and retained-bookmark production-route requests refuse it.
  Copied `certified=true` and incarnation values do not certify restored history.
- Restore/PITR/clone/promotion/import must revoke external incarnation authority
  before service startup. Restored history needs a separate reviewed custody and
  provenance design. Distinguishable identities refuse; a byte-identical physical
  clone with copied external custody authority is outside this design's contract.
- Upgrade requires the dedicated worker stopped and uses 2-second lock and
  30-second statement limits. Partial audit objects, ambiguous worker evidence,
  unsafe roles, recovery and nonpositive existing IDs abort transactional DDL.
- Downgrade requires empty history and uncertified state. It retains private
  audit RLS and global groups, does not erase history or restore public access.
  Repeated Alembic upgrade is a no-op. Historical migration controls keep their
  original start revisions and assertions, with mapping-specific checks bound
  to `e602b11a0001` and legitimate current-head expectations updated to `a611b12a0001`.

These are local implementation/acceptance semantics. Production roles, epoch,
every writer and external custody remain separately unverified here.

## Verification and fixture compatibility

Counts overlap and must not be added. Every scoped row below has raw stdout/XML,
exact source/runtime/command/environment identities, exit states and cleanup.
Current runtime is Python 3.13.9 / SQLAlchemy 2.0.54; minimum is Python 3.12.15 /
SQLAlchemy 2.0.23. Actual optimized Python flags are retained where shown.

| Evidence packet | Actual local outcome |
|---|---|
| `BASELINE_ZERO_*_V2` / `BASELINE_ONE_*_V2` | Original route: 2 epoch-zero passes and 2 intended epoch-one HTTP 503 failures per runtime; real PostgreSQL, not setup failures |
| `DURABLE_SQL_CURRENT_V1` / `MINIMUM_V1` | 45 passes each, zero errors/failures/skips: 44 real SQL controls and 1 frozen-body equality control |
| `FINAL_CONTRACT_{CURRENT,MINIMUM}_{NORMAL,OPTIMIZED}` | 96 passes per mode, including existing privacy/SQLite controls; transport doubles are identified explicitly |
| `ANCILLARY_CURRENT_V3` / `MINIMUM_V4` | Earlier 161 original writer/readiness cases pass per runtime; the changed 21-case B7 subset is re-executed in final 82, and other fixture bytes are unchanged |
| `MAPPINGS_EXPORT_CURRENT_V1` / `MINIMUM_V1` | 165 passes per runtime: 117 original mapping, 12 original process and 36 ownership cases; final fixture bytes |
| `B7_EXPORT_CURRENT_V1` / `MINIMUM_V1` | 82 original writer/process/consumer cases pass per runtime; final fixture bytes |
| `HEAD_CURRENT_V3` / `MINIMUM_V3` | 7 original migration cases pass per runtime; actual single head |
| `LEGACY_CURRENT_V4` / `MINIMUM_V4` | All 61 original cases pass per runtime, no errors/skips |
| `COORDINATOR_HTTP_CURRENT_V5` / `MINIMUM_V5` | Real API/worker: 1 pass each, full-head audit/provenance/effect plus fresh-incarnation reset |
| `COORDINATOR_SCHEMA_CURRENT_V1` / `MINIMUM_V1` | 9 original migration-inventory controls pass per runtime |
| `LOGICAL_RESTORE_CURRENT_V1` / `MINIMUM_V1` | 1 native dump/restore refusal pass each; exact archive bytes/hash retained |
| `FINAL_FIXTURE_GUARDS_{CURRENT,MINIMUM}_{NORMAL,OPTIMIZED}` | 36 ownership/uncertain-cleanup controls pass per mode |
| `BROWSER_DURABLE_CURRENT_V1_ACCEPTANCE.json` | Original browser control: 1 pass, zero skipped/unexpected/flaky/retries; real migrated production route, actual inert JWT decoding |
| `BACKUP_NATIVE_TEMP_CURRENT_V1` / `HEALTH_NODE_PATH_CURRENT_V1` | Original 35 backup and 20 health cases pass on clean 596; native owner/group and installed Node corrections only |
| `SOCIAL_ROLES_ORIGINAL_CURRENT_V1` | All 13 original role cases pass, zero failures/errors/skips, temporary approved native pinned cache tag |
| `CRITICAL_FLAKE8_CURRENT_V2` | Existing whole-backend CI critical-error selection passes after final fixture edits |
| `CANONICAL_CLEAN_CURRENT_V7` / `CANONICAL_V7_OUTCOME_RECONCILIATION_R2` | 15,730 passed / 1,467 skipped / zero failures or errors; all 951 required cases pass; no new skips and only the nine human-approved additional passes |
| `GENERATED_SCANNER_ORIGINAL_CURRENT_V1` | Six exact original hosted scanner selectors pass against the 944-byte native generated input; input removed, clean source restored; counts overlap baseline |

Six literal old TRUNCATE expressions failed against frozen full-head storage in
`FULL_HEAD_RESET_CURRENT_RED_V1`; this is expression-level evidence, not six
complete old fixture runs. The coordinated setup changes use explicitly owned
empty uncertified full-head templates and fresh per-case databases. They do not
disable triggers, erase retained audit history or weaken original assertions,
skips, payloads, retries or individual workload deadlines. Fixed-name child
fixtures retain their original target guards. Native owner/database/schema/OID/
system identities are verified before reads, copies and removal. Uncertain CREATE
or cleanup outcomes stay explicit; cleanup never forces a database drop.

All 70 original test bodies/skip shapes in the six exception files are preserved.
The final mapping/B7 export correction also preserves 46 importing-consumer bodies
and decorator/skip ASTs. `ADVERSARIAL_FIXTURE_EXPORT_V1/REPORT.md` executes actual
pytest fixture graph/generator/finalizer controls: 5/5 green scenarios and 7/7
literal checkpoint 734 missing-dependency refusals per normal/optimized runtime.
Mapping caches follow each consuming Module and its outer mapping resource; B7
uses the source cluster session lifetime. Both retain exact original static URLs.
These scoped real SQL/export packets ran before commit 596f015 with recorded
dirty fixture hashes and an unchanged generated coverage XML.
`SOURCE_CLEAN_EXPORT_CHECKPOINT.json` verifies every tracked source byte now
equals all five passing packet inventories; the canonical gate separately
executes the clean committed head. Existing optional historical B7 migration
bodies were not executed in the 82-case cohort; their accepted prerequisite
skips remain preserved in the default gate.
Independent `ADVERSARIAL_FIXTURE_LIFECYCLE_V6/REPORT.md` executes 228 controls per
normal/optimized runtime, including owned and concurrent-peer probe boundaries.
`ADVERSARIAL_FIXTURE_V4/REPORT_V4.md` executes original 88 and expanded 90 controls
per mode with zero mismatches. The earlier service/bookmark reports bind final
product hashes. These boundary doubles do not certify actual SQL or psycopg2
failure behavior; the real SQL, process and browser packets supply that evidence.

Human-approved immutable reuse of the matching dependency lane's Node tree is
recorded in `CONTINUATION_APPROVALS_2026_10_12.json`. Native Node 22.19.0, Next/SWC
15.5.27, Playwright 1.58.2 and Darwin arm64 identities were verified. All 47,782
entries and 985,716,887 regular-file bytes match before/after content, inode,
mode and symlink identities. Only an ignored symlink in the owned checkout was
added; browser output remained owned. The original 45-second test, zero retries,
selectors and assertions are unchanged.

## Historical failures, cleanup and remaining work

Failed packets remain immutable. The earlier Docker/disk blocker and blocked
handoff commit `59628e4` are historical. Legacy V1 had 61 setup errors from a held
owned bootstrap readiness connection; V2 reached passing cases but the author's
180-second outer capture timed out; V3 failed before native provisioning because
an external capture shim used an incorrect Docker path. V4 uses verified native
`/usr/local/bin/docker`, preserves the original workload, and uses the existing
CI 45-minute outer capture budget, explicitly approved by the human.

The first reconciliation name exceeded PostgreSQL's identifier limit and setup
refused the actual truncated target. Its owned resources were removed with native
absence proof; V2 uses a shorter lane-qualified allowed prefix and real full-head
readback. An earlier ancillary capture exceeded its declared archive bound and
lost temporary identity files; later green runs do not repair that packet. A
literal independent V5 cleanup failure remains preserved; the final helper
attempts the healthy second owned connection and still reports the first close
unverified. The SQLite empty-filter regression has a separate retained red/green
packet and is not the original epoch defect. Clean canonical V2 stopped after
five mapping-process setup errors because imported `pg` fixtures did not export
the newly introduced standalone template dependency. Its legacy cohort passed
295 cases with 41 existing skips. The outer archive also refused its 512-MiB
bound and lost the remaining temporary manifest. Exact canonical artifact prefix
members and raw output were recovered; V2 remains NOT_ACCEPTED. The final
fixture correction removes the export dependency and preserves static child
URLs. Fresh capture keeps the complete temporary-file hash/size manifest,
compact exact canonical artifacts and native generated coverage XML; it does
not archive wholesale fixture repositories or change tests/deadlines. Canonical
V3 preserves 6,070 passes, 389 skips and five setup errors caused by the external
Docker capture wrapper requiring an environment variable that existing native
fixtures intentionally omit. Source remained clean; its three mapping containers
and volumes and 25 known parent/command PIDs are absent. The dedicated V4 wrapper
passed actual native success/failure byte/exit controls with PATH-only and
variable-present environments. No repository fixture or product change was
needed for this capture failure. The first read-only companion capture also
refused pytest current symlink aliases; its failure is retained. V2 copied
ordinary source-resource paths only, and all three literal final receipts match
the complete native V3 temporary manifest.

Canonical V4 stops with backend 7,235 passed / 571 skipped / one failure / four errors and
legacy 295 passed / 41 skipped. Its unchanged backup ownership predicate correctly
refused group0 files created under /private/tmp for caller UID501/GID20. The
external runner had dropped the native macOS user TMPDIR. Literal native file
controls reproduce that refusal and pass under the verified caller-owned native
temp parent with UID501/GID20/mode0700. No guard, assertion, owner or file mode
was weakened. All 35 original backup cases then pass on clean 596f015 using the
corrected external runner, including real PostgreSQL acquisition and restore.
V4 remains NOT_ACCEPTED. Its 12 known journaled/native-B11-event containers,
five networks, 12 volumes and 94 known parent/command PIDs are absent; six ports are free.
The hardcoded backup PATH bypassed the V4 capture shim, leaving a historical
backup creation-ID gap. The scoped 35-case retrospective daemon query is also
limited to the daemon's 256-event history and is not a complete creation/volume
census. A fresh concurrent read-only event observer captures canonical V5
creation IDs and native inspections directly. The first V4 known-resource
absence parser refused native network-not-found wording; literal native red/green
controls bind the corrected parser to exact type/ID/exit/empty-output/stderr.
No fixture or product change was needed for these external capture failures.

Canonical V5's native result is10,705 passes / 895 skips / five failures. It stops at
five original health-workflow cases because the external explicit PATH omitted
the already installed Node binary. All 35 original backup cases now pass in the
actual default backend gate. The unchanged 20-case health module then passes
with native Node 22.19.0 on PATH, zero skips/failures/errors. Product and fixture
bytes remain unchanged. The V5 recorder additionally refuses the newly generated
4-byte SHA-addressed %PDF response receipt beside native coverage XML. Both exact
outputs are preserved before scoped removal; a fresh inventory verifies every
preexisting source byte and clean checkout. Nonempty ignored seeding contents
remain preserved. V5 native creation-event 41 containers / six networks / 41 volumes and
known journal/runner/observer PIDs are absent, six ports free, and four literal
final B11 receipts match the complete endmanifest. V5's observer was stopped
as an exact known read-only process group after the missing final recorder file;
its raw event stream/source receipts remain, but in-memory native inspections
and descendant PID samples were not serialized and are not invented.
V6 adds the verified existing Node directory to external PATH and captures only
new native XML/content-addressed local response outputs after verifying all
preexisting source bytes and exact untracked status. It keeps every other source
change as a refusal and retains ignored cache/parent contents. Its concurrent
read-only observer finishes on native prearchive completion and records any error
or manual stop explicitly. No cases, assertions, retries, skip rules, individual
deadlines, dependency files or product/fixture source were changed for these
external capture corrections. All failed packets remain NOT_ACCEPTED.

Canonical V6's native launcher/recorder pass with 15,717 passes / 1,480 skips
and no failures/errors. Strict acceptance remains NOT_ACCEPTED: 13 original
role cases skip without the cached `postgres:17` tag, while nine original media
cases pass with installed FFmpeg. Native cleanup verifies 41 containers, six
networks, 41 volumes, recorded PIDs, six ports and four manifest-bound B11
receipts. The human explicitly approves nine additional media passes with no
new skips and temporary tagging of the installed pinned PostgreSQL 17.11 image.
All 13 original role cases then pass, with native fixture cleanup verified.
The final gate executes the same launcher from clean commit 596f015.

Final comparison reuses only the accepted source-bound credential/UUID display
limits and separately qualifies two original UTC-date-derived payloads (#634).
Their runtime dates differ; literal date-payload identity is not claimed. Six
hosted generated-file scanner cases use their exact original selectors and
assertions against fresh native launcher-generated bytes. They overlap baseline
counts and are not invented local collection rows. The scoped replay records
its temporary ignored input explicitly and restores clean source afterward.

Final V7 executes 16,861 backend cases (15,435 passed / 1,426 skipped) and 336
legacy cases (295 passed / 41 skipped), with no failures or errors. Every native
outcome matches the actual unique collected node inventory. All 951 required
cases pass, including the 13 original role cases. No new skips exist; the only
removed skips are the nine explicitly approved media cases. Six original
scanner assertions pass with their exact hosted selectors on the captured
944-byte native generated input in the existing ignored fixture-output path;
that input is removed afterward. An initial metadata parser required a percentage
suffix absent from the scoped `-s` output, and the first reconciler pointed at
CI_V7 instead of the immutable CI_V6 baseline. Both failed validation attempts
and original inputs/scripts remain preserved in
`FINAL_RECONCILIATION_R1_CAPTURE_FAILURE`; corrected validators require the same
exact cases, statuses and source bindings. No tests were changed or retried for
these metadata errors. Final readback is
`CANONICAL_V7_OUTCOME_RECONCILIATION_R2/READBACK.json`.

`CANONICAL_V7_NATIVE_CLEANUP/READBACK.json` verifies absence of 42 exact native
container IDs, six network IDs, 41 volume IDs and 875 recorded journal/sample
PIDs, plus seven free loopback ports. Four literal final B11 receipts match the
complete native endmanifest. The read-only observer retains 699 native events
and 48 creation inspections; sampled processes are not an exhaustive worker
census. `FINAL_RETAINED_FIXTURE_CLEANUP_V1/READBACK.json` freshly verifies complete
retained ownership, runs both original cleanup entrypoints and proves epoch and
reconciliation container/network/volume absence, reset-container absence and
ports 55545/55496 free. It removes only the approved temporary `postgres:17`
tag after an exact identity check and verifies the installed pinned image
remains. Both cleanup process groups, the canonical group and owned temporary
directories are absent. All tracked product/fixture bytes remain unchanged.
Historical inputs, including protected `__pycache__` fixtures, remain intact.
Runtimes/evidence and the managed worktree remain retained while review is open.
The unchanged shared visualization baseline and 10-GiB growth limit were checked
before/after allocation phases; exact receipts are in `EVIDENCE/storage-checks`.

No new defect issue was filed. Remaining production legacy admission/custody and
deployed every-writer acceptance remain under #611/#583/#554; parent #545 stays
open. The coordinator should review this exact draft source, validate immutable
combined hosted checks and browser wiring, then review audit migration as a
separate release step after the baseline `e602b11a0001` rollout. Production must
not consume a mutable draft `upgrade head` target.

## Proposed narrow skill update

Add an independent-resource cleanup rule to `adversarial-verify` or
`verify-boundary-shapes`: attempt every exactly owned resource even after one
uncertain close, while preserving the failure. Actual example:
`ADVERSARIAL_FIXTURE_LIFECYCLE_V5` shows a persistent first close error prevented
attempting the healthy second connection; V6 proves the second is attempted and
the first remains unverified in normal and optimized Python. Require an import-consumer census
when a shared pytest fixture changes dependencies: canonical V2 and literal 734
reds show that importing `pg` alone does not import a standalone template
fixture, while final export controls prove the preserved minimal dependency
closure/static URLs and actual cleanup ordering. Also require native
boolean identity/row arity for privilege evidence and distinguish transport
doubles from actual SQL acceptance. No shared skill file was edited.


## Coordinator review repairs — PR641

The author acceptance counts above describe the original published candidate,
not the later review edits. The coordinator preserved those packets unchanged.
Review findings and fixture defects are tracked in #643; #611 and #545 remain
open for deployed storage custody, epoch, actual roles and all-writer acceptance.

The migration now clears existing PUBLIC, anon/authenticated, reader and writer
sequence ACLs before granting only writer USAGE. PostgreSQL does not grant
PUBLIC sequence rights by default; an explicit retained PUBLIC grant reproduces
the reported defect. Both migration postconditions and runtime reader admission
refuse forbidden effective sequence privileges. A real PostgreSQL regression
first fails on the original revision and passes after the repair, retaining a
working restricted writer and private reader route.

The three older opt-in audit PostgreSQL controls now reuse the fully migrated
canonical durable fixture while preserving their original assertions and opt-in
contract. Original table-only fixture execution reproduces sanitized HTTP503 in
two route controls; updated real PostgreSQL controls pass.

The full-head template guard inventories every public ordinary table under
actual unrestricted owner authority, refuses any retained product/history rows,
and requires exactly one Alembic-version row and one correctly typed,
uncertified storage identity. It verifies the native storage identity before
copy/removal. The only populated static control allowed is the established
single normal-mode coordinator control with its exact column definition;
worker effects and every other table remain required empty.

Durable API and browser fixtures share independent owned-resource cleanup.
They register creation before transport, preserve uncertain outcomes without
deleting unverified resources, and bind every database/role cleanup to the
registered native cluster identity. A failure or interruption still attempts
other resources and control disposal. Setup and cleanup errors remain visible
together; cleanup success is never inferred from a partial attempt.

Fresh coordinator evidence is external under BATCH_12_REVIEW.
`641_SCOPED_V2` passes 166 cases on each supported SQLAlchemy runtime, including
the native migration/old audit controls. `641_FINAL_GUARDS` separately checks
final guard/interruption bytes on current/minimum normal and optimized Python.
Independent original/candidate cleanup transport-double receipts retain actual
caller execution and uncertainty controls; these are not native database proof.
Final integrated hosted acceptance and owned browser replay are recorded by the
coordinator before merge. No production certification, role update, migration
or worker activation is performed by these review repairs.

## Coordinator review: canonical role parity (#646)

The first complete combined hosted candidate (`7c803a1`, run38341871807)
failed the unchanged coordinator Chromium bootstrap: the canonical restricted
login could not CREATE ROLE for the new full migration. The ancillary local
harness's superuser did not establish canonical compatibility. Source review
also found that the template guard required a superuser and the canonical
login lacked the CREATEDB permission needed for owned per-case copies.

The canonical runner now precreates only the exact safe audit group roles
through its owned container administrator. Migration/runtime ownership remains
with the coordinator; its login is explicitly NOSUPERUSER, NOBYPASSRLS,
NOCREATEROLE and NOREPLICATION. Its isolated fixture now explicitly permits
CREATEDB. Native role flags and absence of inherited memberships are checked
and retained in the database receipt before any browser cohort starts.

The complete population guard sets transaction-local row_security=off and
verifies readback before every history read. PostgreSQL refuses reads that
would apply RLS filtering; this grants no bypass privilege. All full-head,
storage identity, table inventory and retained-row refusals remain. Native
controls exercise a restricted table owner passing with an empty population,
and ordinary nonowner/forced-owner RLS refusing known retained rows without
erasing them. All52 scoped controls passed on both current and minimum
SQLAlchemy. The literal original population function fails the empty-owner
control, with exact source/function and native cleanup evidence retained.
These controls are separate from actual canonical CLI/hosted acceptance,
which remains pending and must use the complete original browser inventory.

No production role, connection, migration or storage certification was changed.

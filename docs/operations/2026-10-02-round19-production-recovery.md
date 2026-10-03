# Round19 production recovery and serialized correction operation

This is the root coordinator's review packet. Local engineering and isolated
verification are complete; production acquisition, freeze, restoration,
configuration adoption and corrections have **not** run. Actions stays OFF.
The ready marker distinguishes executable acquisition controls from the facts
that must be established during the approved operation. No production recovery
certificate or live cleanup digest is asserted here.

## Targets, current facts and integration contracts

Use the consolidated reviewed release checkout, not a worker's historical
checkout. Bind its commit, tool hashes and both provider deployment IDs in the
operation receipt. Supabase project is `xznjxwrkbkahwtnbstbj`. S2's Oct2 23:40 UTC
observation selects Render service `srv-d6hr3t5m5p6s73bomqu0`, deployment
`dep-db038g8ae00c73e85hi0`, one instance, master1/worker7, and Vercel production
`GMVVKuHmoKyE226EvBfkZ2sZboE4` in `rodgers31s-projects/audit_app`; both observed
base commit4645d0e. These are observations, not the eventual approved deployment.

The shared bank is
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170`.
`ROUND19_RUNTIME_READY.json` binds S2 commit
`fdae2bed08f83be7cb2c0cad6b860bf22865b082` and its
[runtime adoption operation](2026-10-02-round19-runtime-adoption.md).
`ROUND19_OAG_VALIDATION_READY.json` binds S3 commit
`37b623766c3c8cb73113e71f6284f8907d1b2449` and genuine listing/full validation
bridge. Root must verify those marker/producer/file hashes before using them.
Those peer changes must be integrated before the commands below are enabled.

S1's narrow verified READ ONLY REPEATABLE READ observation, Oct2
23:58:36–23:58:41 UTC, adds five small query results: PG17.6, the observed five
extensions and owners, zero Vault secrets, zero storage objects/buckets, two
auth users, zero foreign tables/subscriptions/security labels, one publication,
24 default ACL entries, 22 enum/domain/range/multirange types, and no unreadable
non-system table/materialized-view/sequence. It rolled back. This path used
`sslmode=require`; it is not evidence of verified server identity by a CA.
Recheck these facts inside the freeze; counts alone do not prove completeness.

## Concrete approval and writer window

Root reviews one acquisition attempt at this exact project, with **300seconds
connection window and 128MiB cumulative namespace RX+TX sampled abort**. Retain
the prior 256MiB proposed allowance as a cost decision, not a hard guarantee.
The largest previously measured overshoot is **4,661,194bytes**; this is an
observed lower bound on possible excess, not a maximum. The latest compatible
fixture transferred5,088,519bytes in0.281seconds, including inventory/roles/dump;
it does not predict production size, time, server memory or egress. Delayed
provider quota needs a fresh project-specific readback. Inventory aggregation
can consume server memory and its transfer can exceed compressed dump size.
Choose another threshold only by recording that exact root decision in the
request. If a hard provider accounting cap is required, first obtain a
provider-enforced quota/reservation or independently verified transport control;
the present helper cannot provide that cap. No retry after an abort without
reviewing cost and failure. Reserve1GiB private local capacity; no image pull.

Root names the operator/reviewer in the receipt and approves an API outage
target of30minutes for freeze/acquire/restore review. This is a
planning window, not a measured production duration; recovery and OAG work may
require extending it. At the deadline stop new writes and classify committed
state before deciding whether to extend or resume. Acquisition itself remains
bounded independently. OAG's1320second total budget is separate and may leave
earlier volumes committed. A service suspension cannot span the later refresh
experiment's warm baseline and after-state.

1. Keep GitHub Actions disabled; reserve manual/native writers and external
   ingestion for this project. Record actual previous settings and job states.
2. Adopt S2's reviewed configuration and signing key before the serving baseline:
   `AUTO_SEEDER_ENABLED=false`, `PARLIAMENT_PIPELINE_ENABLED=0`,
   `CACHE_GENERATION_FILE=/tmp/auditgava-cache-generation`, one instance/worker,
   root backend/context`.`/Dockerfile`./Dockerfile.prod`, no command override.
   Use one dedicated32-byte random key encoded as64hex characters for server-only
   Render/Vercel Production/GitHub `REVALIDATE_SECRET`. Keep the authority file
   private and verify through actual signed worker/path responses, not public
   secret hashes. Saving settings alone is not adoption. Startup still writes
   reference data; finish it before the subsequent stable baseline.
3. Suspend **only** Render service `srv-d6hr3t5m5p6s73bomqu0` for acquisition and
   recovery acceptance; record suspension readback and outage start. No broad process
   kill. S2 observed a running reference refresher, next refresh Oct9 22:46:52Z.
4. Resolve the actual owning scheduler database/provider job IDs for visible
   pg_cron/pg_net processes. Their job/run/queue tables did not resolve in the
   inspected database. Record and pause only identified writer jobs, drain
   their relevant queues/in-flight transactions, and retain prior enabled
   states. Do not guess SQL against missing tables or terminate all provider
   sessions. This unresolved topology is a precise remaining prerequisite.
5. Verify the selected service is stopped, reserved writers remain paused, and
   scoped activity has drained. A single pg_stat_activity snapshot is supporting
   evidence, not proof of exclusive authority. Write a private freeze receipt
   with target, operator, times, jobs, previous states and drain readbacks.
6. After recovery acceptance, resume serving at the approved configuration and
   complete startup. Keep all domain writers reserved, including the actual
   loaded reference refresher: root must identify and verify its scoped pause
   mechanism before keeping serving workers live. Neither AUTO_SEEDER=false
   nor a distant next refresh proves a pause. If that cannot be established,
   stop before the serving experiment. Warm and record changed API/browser
   values at the fixed serving SHAs/PIDs **before stage1 below**. Do not restart,
   redeploy or suspend those workers through the final after-state. Resume only
   recorded previously enabled writer jobs after accepted final state and
   restore their exact settings.

## One reviewed acquisition

Root prepares `/Users/roger/.codex/round19_s1_private` mode0700; all input files
mode0600. Resolve existing project credentials privately; no passwords in argv,
logs or Git. Obtain the **selected project's** root CA via Supabase Dashboard
database SSL settings. Use direct `db.xznjxwrkbkahwtnbstbj.supabase.co:5432`
userpostgres, or the currently configured **session** pooler hostname on5432
user`postgres.xznjxwrkbkahwtnbstbj`. Transaction pooler6543 is refused. Preserve
the actual hostname with `sslmode=verify-full`; no TLS proxy or certificate bypass.
[libpq SSL](https://www.postgresql.org/docs/17/libpq-ssl.html).

The private `pg_service.conf` has exactly one `[round19_recovery]` section and
these keys (host/user chosen as above):

```ini
[round19_recovery]
host=db.xznjxwrkbkahwtnbstbj.supabase.co
port=5432
user=postgres
dbname=postgres
connect_timeout=8
sslmode=verify-full
sslrootcert=/backup/root.crt
passfile=/backup/pgpass
gssencmode=disable
```

Create private `request.json` immediately after reviewing the frozen identity:
exact keys `version`1, `project`, `expires_at` UTC within15minutes,
`generator_sha256`, `inventory_generator_sha256`, `service_sha256`,
`pgpass_sha256`, `ca_sha256`, `identity`, `wall_seconds`300,
`transport_abort_bytes`134217728, `writer_freeze_receipt_sha256`, and
`transport_acknowledgement` equal to
`sampled_namespace_abort_is_not_a_hard_provider_ceiling`. Hash the actual files
in the adopted checkout. Identity has exactly database_name_sha256,
server_address_sha256, role, server_port, version. Last observed values are:

```json
{"database_name_sha256":"a942b37ccfaf5a813b1432caa209a43b9d144e47ad0de1549c289c253e556cd5","server_address_sha256":"33f838b4102220395b7189be29b6d33c2edcfb00ca16bcc25c8c5594f25c99d8","role":"postgres","server_port":5432,"version":"17.6"}
```

Reconfirm, rather than overwrite a changed address/version automatically.
The request hash is an explicit operator checkpoint, not a cryptographic proof
of authorization or that the freeze receipt's contents are true. Root reviews
the receipt itself. From `$APPROVED_RELEASE_CHECKOUT`:

```sh
"$APPROVED_PYTHON" tools/reviewed_pg_acquisition.py \
  --request "$PRIVATE_OPERATION_DIR/request.json" \
  --execute-reviewed-request-sha256 "$APPROVED_REQUEST_SHA256" \
  --service-file "$PRIVATE_OPERATION_DIR/pg_service.conf" \
  --pgpass-file "$PRIVATE_OPERATION_DIR/pgpass" \
  --ca-file "$PRIVATE_OPERATION_DIR/root.crt" \
  --output "$PRIVATE_OPERATION_DIR/acquired"
```

The output directory must be new. The pinned available SupabasePG17.6 image is
`public.ecr.aws/supabase/postgres@sha256:21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab`.
The helper bypasses its provider entrypoint, inherits no application/libpq env,
exports a verified read-only repeatable-read snapshot, imports it for full
non-system relation checksums, and holds it through the custom dump. Globals
are exported separately without password hashes; freeze is required for
non-MVCC roles/sequences. One fresh namespace supervises every connection;
20ms sampling shuts its eth0 down on a byte/wall breach, then the host removes
it. No valid bundle is published after failed/late-aborted capture or cleanup.
Failed private scratch is removed; the sanitized refusal is not a retained
diagnostic archive. Retain terminal exit/time and sanitized receipt separately.

Success means `acquired_inputs_restore_and_completeness_pending`, never backup
verified. Keep the private dump, roles, inventory and hash-bound receipt. Auth
table rows are private dump content. Global role password hashes are omitted;
login credential/provider Auth configuration re-establishment requires its own
private recovery disposition. Vault root key and storage object bytes require
separate inputs. [PostgreSQL dump scope](https://www.postgresql.org/docs/17/app-pgdump.html),
[Supabase backup scope](https://supabase.com/docs/guides/platform/backups).

## Compatible restore acceptance before any correction

The bank's `ROUND19_SESSION_1_COMPATIBLE_V14.json` and producer establish an
actual isolated PG17.6 TLS acquisition/restore with30roles,21memberships and
the exact five observed extension versions/owners/placements. A reviewed
local template creates `extensions` owned bypostgres and installs
pg_stat_statements1.11/pgcrypto1.3/uuid-ossp1.1 aspostgres; the bootstrap
supabase_admin owns plpgsql1.0 and creates supabase_vault0.3.1. Only locally,
temporarily elevate postgres to create these extensions, then restore its
captured NOSUPERUSER state. Do not elevate any production role.

For actual private data use a new secured local target named
`round19_s1_production_restore` with `--pull never --network none`, no ports,
no production credentials, explicit initdb/server startup and no app/bootstrap
or schedulers. Load only required pg_stat_statements/Vault libraries; do not
enable restored cron/net jobs. Match the actual source database name, owner,
encoding, locale/provider and tablespaces from a reviewed frozen catalog
readback. Provider-managed system privileges/settings and custom base-type
I/O bindings are not completely inventoried by this helper and require exact
disposition. Missing facts stop acceptance; they are not silently excluded.

Hash-review roles SQL before executing trusted input locally. Bootstrap
supabase_admin already exists: remove exactly its single CREATE ROLE entry,
retain its ALTER/settings and all other role/member definitions. For the
extension template retain every TOC entry except exactly one verified
`SCHEMA - extensions postgres` entry already satisfied by that template.
Keep original/edited role/TOC hashes and full disposition. No --no-owner,
--no-acl, ignored restore errors or arbitrary TOC filtering. Restore with:

```sh
docker exec round19_s1_production_restore pg_restore \
  --exit-on-error --single-transaction --use-list=/backup/reviewed-restore.list \
  -U supabase_admin -d postgres /backup/database.dump
```

Bind all private input bytes and read back image/version/isolation/role flags.
Run `bounded_pg_backup.inventory_local(target)` and
`compare_inventory(acquired_inventory, restored_inventory)`; each refuses bad,
missing, duplicate or mismatched evidence. Compare complete source/restored
rows, sequences, large objects, ownership, ACLs/default ACLs, constraints,
triggers, RLS, routines, custom enum/domain/range/collation and publications.
Extension config is qualified table identity plus ordered conditions, not
cluster-local OIDs. A retained test failure showed `CREATE COLLATION ... FROM C`
can restore encoding -1 as the database encoding; this remains a strict
mismatch requiring exact template/disposition, not automatic normalization.
The fixture used an explicit libc/C collation for its successful control.

Recheck frozen Vault/storage counts. If still zero, record empty state as the
current recovery scope. If nonzero, root's separately reviewed private key read
is authenticated GET `https://api.supabase.com/v1/projects/xznjxwrkbkahwtnbstbj/pgsodium`,
saved directly to a0600 private file with no terminal/tool output. This is the
managed64hex root key, not a database row or application API key. Review its
local image key-install/decryption path before testing; never PUT/rotate the
production key. Acquire separate private storage object bytes before acceptance;
SQL metadata alone cannot restore those bytes. Never publish these inputs.
[Vault key portability](https://supabase.com/docs/guides/database/vault).
Test auth/storage and actual provider/custom objects; synthetic rows do not
certify actual managed privileges. The actual production dump/restore, source
database properties, system privilege disposition and fresh frozen writer facts
are still unverified. Rehearse operation-specific forward/inverse/drift controls
against that accepted private restore; no production acquisition has run here.

## Serialized corrections and public acceptance

For each stage record reviewed plan/forward/inverse hashes, actual complete
before/after readback, commits and protected cohorts. Stop on drift; do not
manufacture an after-image. `ROUND18_CORRECTIONS_PREPARED.json` is the existing
authority/index, hash9000d40a32fe40bb9609f595d8c6aba6f2e4de26e9ba170fe99c48672fc042e2.
Its private paths are available; local CPI resolved IDs and modeled cleanup
states are explicitly excluded from production inputs.

1. Review current rows/relationships against accepted recovery. Publisher SQL
   `/Users/roger/.codex/round18_s3_private/source-publishers.sql`
   hash0ae206a4d1a0172d4469b8ec62b53535a58e2ce3b2fe12db81e7539bf339e889
   relabels1840→CBK and2383→NationalTreasury only. Preserve IDs, loan426 and
   monetary relations. County SQL `county-codes.sql` in that directory,
   hash63462f804450ad3f59f339b346b9359a5a7cf7095ab59994c4f19cda62a66c3b,
   changes only Nairobi Entity3 FY2024/25+2025/26 nested001→047 and Mombasa4
   047→001; legacy routes001=Nairobi/047=Mombasa stay intact. Original SQL ends
   ROLLBACK. Root reviews a separately hashed exact terminal-COMMIT copy; do
   not globally replace transaction tokens. Execute via private service using
   `psql -X -v ON_ERROR_STOP=1 --dbname=service=round19_recovery -f FILE` only
   after that service has an explicitly reviewed write credential configuration.
2. **Reprepare #379 from actual post-code state.** The old plan correctly
   refuses because Entity3 metadata changed. Supply dedicated
   `OAG_BOUNDARY_DATABASE_URL` privately, disable dotenv, then from release root:

   ```sh
   PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_boundary_correction.py \
     --pdf "$REVIEWED_OAG_PDF" \
     --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
     --output "$PRIVATE_OPERATION_DIR/oag-plan-post-code.json"
   ```

   Hash-review the new canonical plan, run the same command with `--plan FILE
   --expected-plan-sha256 DIGEST` and a new dry-run output, then add `--commit`
   with a new durable recovery output only after root approval. Trim only
   separately attached prior-year tables in audits5545/5679/5716 and
   extractions6023/6158/6196 at2541. Preserve narrative, amounts, institution,
   period, page/locator/IDs and all579 other findings of its582-row cohort.
3. Take the real post-code/post-text protected baseline. Confirm S3 adopted
   three unselected edition PDFs are retained at deployed paths. From backend:

   ```sh
   "$APPROVED_PYTHON" -m seeding.cli seed --domain audits \
     --audits-source-manifest ../docs/operations/2026-10-01-round11-oag-catchup/manifest.json \
     --audits-observe-listing --no-dry-run
   ```

   This writes jobs even on refusal; each completed selected volume can commit.
   Require fresh parent/year listing and genuine persisted/PDF evidence for
   unselected adopted volumes before selected registration. Keep exact five
   selected editions; no unselected PDF download/backfill. Preserve national2392,
   legacy2395/2396, HomaBay2391, current2539/2541/2542 and every unselected field.
   Retain per-source deltas, job outcomes and actual timings/egress. A timeout
   requires current-state reconciliation; there is no generic catch-up inverse.
4. Prepare CPI from actual current state with private
   `CPI_CORRECTION_DATABASE_URL`; retained reviewed Jan/Dec PDFs are indexed in
   ROUND18_CORRECTIONS_PREPARED, hashesca9654579a2a0b8d14301de005cea70f1db2943c8d40cb111be3b8b1e0ccd44d
   and75e6f741704874180edd8378ec6219c5920f15082496e6bf47aa00e0f7570614.

   ```sh
   PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/cpi_source_correction.py \
     --manifest docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json \
     --january-pdf "$REVIEWED_JAN_PDF" --december-pdf "$REVIEWED_DEC_PDF" \
     --output "$PRIVATE_OPERATION_DIR/cpi-plan.json"
   ```

   Review canonical plan, dry-run with `--plan FILE --expected-sha256 DIGEST`,
   then `--commit` to a new durable receipt.67/86 Jan2025 143.08→142.68;
   87 Dec2024 142.47→141.66; KNBS Overall CPI Feb2019=100, coherent document/
   extraction authority. Allocate production's own two sources/extractions.
   Preserve1715/1823, annualWorldBank, population79=51,202,827 and all population
   facts. Inverse `--recovery RECEIPT --expected-sha256 DIGEST` restores the
   guarded fact images while retaining archival evidence and consumed sequences.
5. Capture actual complete post-all-writes P3 state under the same writer
   reservation, following `ROUND18_SESSION_5_STAGE_INPUT_CONTRACT.json`:
   all47 complete county rows/metadata/projects, full1836 row and dependencies,
   audits870–894, schema/FKs/logical references, committed adoption deltas and
   CPI/OAG/publisher/code preservation. Use a newly adapted reviewed read-only
   collector and manifest generator; the old CURRENT_PREPARE script is tied
   to pre-write evidence and **must not run unchanged**. This stage cannot
   have a valid digest until preceding production writes actually exist.
   Exact fixture authority remains47economic_profile+3missing_funds_cases+
   8audit_summary keys and25 audits; preserve all47 sourced project blocks.
   Render `tools/prepare_legacy_evidence_cleanup.py ACTUAL_MANIFEST NEW_OUTPUT`;
   review both default-ROLLBACK files, their exact terminal-COMMIT variants and
   guarded inverse before execution. Keep1836 and1707/1718; zero refs alone
   gives no source-disposal authority. New extraction/page binding, incoming
   audit references, changed source coverage or fixture authority stops cleanup.
6. Retain the serving baseline established before stage1. After all writes run
   the genuine full validation body from the adopted checkout, followed by the
   signed generation and frontend acknowledgments. If any serving process or
   deployment changed meanwhile, the experiment is invalid and requires a new
   reviewed baseline/changed-state experiment; an already changed response
   cannot retroactively establish cache refresh. Commands:

   ```sh
   PYTHONPATH="$APPROVED_RELEASE_CHECKOUT/backend" "$APPROVED_PYTHON" \
     "$ROUND19_BANK/ROUND19_SESSION_3_VALIDATION_RUNNER.py"
   "$APPROVED_PYTHON" tools/verify_refresh_acceptance.py --execute \
     --api-url https://audit-app-4pwa.onrender.com \
     --frontend-url https://www.auditgava.com/api/revalidate \
     --worker-pid "$APPROVED_WORKER_PID" --backend-commit "$APPROVED_RUNTIME_SHA" \
     --marker-path /tmp/auditgava-cache-generation \
     --reason 'Round19 approved source release after dedicated full validation' \
     --output "$PRIVATE_OPERATION_DIR/refresh-ack.json"
   ```

   Require0critical full validation errors, genuine376county/year/institution
   cells without qualified run gaps, source/page/protected-column receipts.
   Repeat --worker-pid for every actual worker; require generation adoption
   and exact10frontend-path acknowledgment, then changed API and real rendered
   source/value evidence at fixed SHAs/PIDs. Utility bounds are1invalidate,
   max30status,1frontend,120seconds total/15seconds per request/64KiB response.
   It does not itself run full validation or certify ISR/browser after-state.
   No restart/redeploy between a serving baseline and its after-state.

## Failure, inverse and closure

On lost acknowledgment classify fresh complete rows as exact before/exact
after/mixed or drifted. Intent files do not prove commit. Stop further writes
on unknown state. Undo only actual committed stages in reverse order: guarded
cleanup; CPI fact inverse with archival allocations retained; reviewed actual
catch-up deltas; guarded #379 inverse; code cells; publishers. Text inverse is
not catch-up recovery. Never overwrite whole stale metadata, reset sequences,
or delete shared sources. Full production restore requires a separate root
disaster-recovery decision and reconciled auth/storage/provider dependencies.

#273 can close independently after actual2383 Treasury publisher/source/API/
rendered evidence with loan426 preserved;1840 remains a #319 criterion. #379 can close after actual three
text/extraction trims, full shared-source preservation and rendered source/page
acceptance. #231/#319 remain open for accepted actual complete recovery, writer
coordination, adopted runtime/config, all approved corrections/cleanup and
signed/public acceptance. #234 needs actual five-volume adoption, genuine full
validation and refresh. #230 still needs source/human project and narrative
decisions, public provenance/language acceptance and Projects exposure. No local
test or ready marker closes these issues.

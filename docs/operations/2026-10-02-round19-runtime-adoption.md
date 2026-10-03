# Round19 runtime adoption and refresh acceptance

This is a review-ready operation for the coordinator. S02 performed no live
configuration, secret, service, seed or cache operation. Actions remains OFF.
The code adds signed per-worker observation and fixes acknowledgements that could
advance before a failed clear or bind to a missing/competing marker. It does not
complete #231's production seed-to-render acceptance.

## Current actual target

Authenticated observation on 2 October 2026 at 23:40:08 UTC found Render service
`srv-d6hr3t5m5p6s73bomqu0`, deployment `dep-db038g8ae00c73e85hi0`, selected instance
`d2qlc`, Gunicorn master PID1/worker PID7. Both report commit
`4645d0ed602c70c906a42627193f4d2c78fa002f`, production, PORT10000 and
WEB_CONCURRENCY1. They share mount `mnt:[4026540704]` and `/tmp`
device66305/inode27364113. Five deployed file hashes match the base Git bytes:
Dockerfile, Dockerfile.prod, invalidation module, cache router and main.

The deployment's **build log** at22:46:32UTC explicitly says
`#1 [internal] load build definition from Dockerfile.prod` (3.57kB transferred).
That file's `sh -c exec gunicorn` CMD expands PORT10000 to the observed command.
This resolves the actual command's origin. The settings form still displays
backend root/context, `backend/./Dockerfile`, and empty command/predeploy
overrides. Why the form and actual build differ is unresolved provider state;
the form is not evidence that the serving image uses the development CMD.

The computed marker path is `/tmp/auditgava-cache-generation`, absent in both
process roots. The actual loaded Python path/adopted identity remain unobserved
in production. The signed `/api/v1/system/cache/status` added here makes those
values observable from the worker after adoption. It does not create a marker,
clear Redis or alter data; like ordinary request middleware it can clear this
worker's memory caches when a marker has changed. A cold absent-marker status
can have `synchronised:true` with null identities. Only comparison to a **non-null
successful invalidation identity** proves the intended transition.

Vercel project `rodgers31s-projects/audit_app` has Ready production deployment
`GMVVKuHmoKyE226EvBfkZ2sZboE4`, hostname
`audit-6zp3lrg9t-rodgers31s-projects.vercel.app`, at the same full base commit.
Current Render/Vercel complete names lists and successful23:53UTC GitHub reads
lack `REVALIDATE_SECRET`; no linked environment groups/shared variables were
listed. GitHub reports `enabled:false`. Initial clean-environment gh attempts
returned4 because credential resolution was unavailable; the separate normal
environment retry succeeded. No values were revealed or hashed.

Fresh public23:48UTC health reports memory caching/no Redis and namespace
`4645d0ed602c`. Pipeline health reports a running reference refresher, last
county completion22:46:52UTC, next9October22:46:52UTC, and dedicated job health
`not_checked_here`. The narrow23:50UTC verified READ ONLY/REPEATABLE READ rollback
census captured13 activity rows: five client sessions including its own plus
eight background workers, including pg_cron/pg_net. Their job/run/queue catalogues
do not resolve in the connected database. This is not a writer-free reservation.

All observations, exact commands/SQL, original failures and producer/source
hashes are retained under `ROUND19_SESSION_2_*` in the coordinator bank. The
Round18 full before-images/catalogues remain inherited and are not recaptured.

## Exact coordinator configuration operation

Do this only after the coordinator approves the concrete operation and S01's
serialized recovery/data window. It includes provider builds/restarts and small
cache writes; it is not authorized by this local commit.

1. Generate **one dedicated random 32-byte secret encoded as64 hexadecimal
   characters** in a coordinator-owned0700 directory/0600 file. No whitespace
   or newline in the value. Never reuse SECRET_KEY, SUPABASE_JWT_SECRET or a
   NEXT_PUBLIC variable. The same private file is the authority for all targets.
2. On Render service `srv-d6hr3t5m5p6s73bomqu0`, set server-only
   `REVALIDATE_SECRET` from that file and explicit
   `CACHE_GENERATION_FILE=/tmp/auditgava-cache-generation`. Preserve
   WEB_CONCURRENCY1/one instance/no Redis. Normalize the Dockerfile setting to
   `backend/Dockerfile.prod` (the UI field relative to backend is
   `./Dockerfile.prod`) and retain backend build context/empty Docker command.
   Record previous settings privately for rollback. Confirm the resulting build
   log and PID command before trusting adoption; do not change the dev Dockerfile.
3. On Vercel project `rodgers31s-projects/audit_app`, add **Production** server-only
   `REVALIDATE_SECRET` from the same authority file. Adopt it by a production
   deployment of the reviewed consolidated commit. Render must likewise deploy
   that commit containing the new status endpoint. These adoption deployments
   occur **before the refresh experiment baseline**. Saving a provider variable
   is not loaded-worker adoption.
4. Root alone sets repository `Rodgers31/audit_app` Actions secret using private
   stdin: `gh secret set REVALIDATE_SECRET --repo Rodgers31/audit_app < "$PRIVATE_SECRET_FILE"`.
   Keep Actions OFF. Successful storage from the common file and a names-only
   read establish configuration intent; actual workflow-loaded equality stays
   pending the separately approved final hosted batch.
5. At each actual worker, use a timestamped signed `/cache/status` request with
   that private key to verify loaded commit/path/PID. Its signature verification
   supplies a private challenge-response equality check with the source key.
   Root's first signed exact-path frontend acknowledgement similarly checks the
   adopted frontend key, and is a cache operation requiring this checkpoint.
   Retain only equality/target/revision/challenge ID and sanitized acknowledgements,
   never the key, raw key hash, signed headers or credential-bearing URL.

Normalizing the build setting and adopting the key can cause builds/restarts,
startup DB/reference work and cache warmup. Costs include those provider builds,
ordinary startup queries, one32-byte marker per invalidation and bounded refresh
requests. This session measured neither build cost nor quota consumption for
future operations. It did not reread quota or acquire a backup. S01 must include
startup effects and the inherited egress constraints in the reviewed window.

## Freeze and resume method

The application has no universal scheduler-off switch. Setting
AUTO_SEEDER_ENABLED=false disables the reference refresher on the next boot;
PARLIAMENT_PIPELINE_ENABLED=0 suppresses Parliament scheduling. Neither disables
all potential legacy/manual/provider writers, and startup reference initialization
still runs. Adopt these settings and finish startup **before the baseline**.
Record prior values for resume. Current pipeline reports the legacy discovery
module unavailable and no tracked ETL jobs; this does not prove no scheduler
or manual tasks exist elsewhere.

For acquisition/corrections S01 can use the exact selected Render service's
**Suspend Web Service** control, confirm selected serving processes are gone and
record availability loss, then resume this same service after the guarded data
operation. This freezes this web process only. Do not suspend between the refresh
baseline and after-state: a restart would invalidate the experiment. A still
running paused-writer serving configuration is required for that phase.

pg_cron/pg_net's visible Supabase-admin background processes cannot be frozen or
certified from the absent catalogues. Root/S01 must first resolve their owning
scheduler database/provider control for this exact project and capture a bounded
job-ID/active-state inventory (not command text with credentials), then deactivate
only captured domain-writer jobs, drain/confirm active runs and outbound queue,
and retain each previous active state for resume. Do not run guessed cron SQL
against this database or kill platform background workers. Auth/storage/manual
and other provider writes need S01's explicit owner reservation; ActionsOFF alone
does not freeze them. These are concrete remaining owner choices, not a claim of
exclusive writing from the snapshot.

## Executable experiment after adoption

1. Record exact Render/Vercel deployment IDs/full SHAs, actual worker census
   (worker PIDs, not master PID1), shared marker mount/path, module hashes and
   loaded signed status. Freeze the approved writer set. Record source IDs/PDF
   hashes and preserved history from S01/S03's adopted source/validation receipts.
2. Warm the exact API and rendered page measures expected to change under the
   approved source release. Retain values, units, IDs/periods/provenance, response
   hashes and browser evidence. Choose actual changing measures; unchanged data
   cannot demonstrate refresh. Do not create synthetic production rows.
3. S01 executes the actual approved source seed; S03 performs the dedicated full
   validation with its bounded bridge. Retain commands/runtime/source hashes and
   actual validation success. Stop if any full-validation criterion fails. This
   refresh utility does not validate a seed or replace that receipt.
4. Root executes the following from the final adopted checkout, with
   REVALIDATE_SECRET privately loaded from the common authority file. Use fresh
   worker PIDs and adopted SHA/path, never today's PID7 as a future assumption:

   ```sh
   python tools/verify_refresh_acceptance.py --execute \
     --api-url https://audit-app-4pwa.onrender.com \
     --frontend-url https://www.auditgava.com/api/revalidate \
     --worker-pid "$APPROVED_WORKER_PID" \
     --backend-commit "$APPROVED_RUNTIME_SHA" \
     --marker-path /tmp/auditgava-cache-generation \
     --reason "Round19 approved source release after dedicated full validation" \
     --output "$PRIVATE_OPERATION_DIR/refresh-ack.json"
   ```

   Repeat `--worker-pid` for every current worker if the topology changes.
   The output directory must be0700; the new receipt is0600. No requests run
   without `--execute`. The command requires an actual non-null32-byte generation
   identity, every supplied worker's matching loaded SHA/path/adopted identity,
   then the exact10 allowed frontend paths from `paths.json`. It stops before
   frontend refresh if any worker acknowledgement is malformed/missing/mismatched.
   It makes at most one invalidation,30 worker probes and one frontend request,
   bounded by120seconds total/15seconds per request/64KiB per response. Repeatedly
   sampling only one worker cannot certify another. A fresh end census must show
   the same worker cohort; recycling invalidates this experiment's comparison.
5. Read changed API and browser-rendered measures/provenance. Verify both full
   deployment SHAs and process cohort still match the baseline and no restart,
   redeploy or unrelated cache operation intervened. API success, status equality
   and frontend acknowledgement alone are not changed-render acceptance. Keep
   #234's deferred volumes and #347's original inflation history intact.
6. Resume only the recorded writer settings/jobs after S01 accepts after-state.
   The provider/account runnable-job check and actual workflow-loaded equality
   remain deferred to the owner-approved final Actions batch.

Abort on wrong SHA/path/census, invalid auth/ack, a marker race, missing full
validation, source/history drift or unexpected writer. A failed refresh may
already have cleared backend caches or partially revalidated frontend paths;
it is safe to repeat the **approved refresh** after correcting the cause, but
never automatically repeat the seed/data operation. Preserve failed0600 receipts.
If adoption fails, root restores recorded provider config and the previously
successful deployment/key, verifies readiness and records the rollback. If data
already changed, S01's guarded inverse/recovery decides rollback; cache TTL or a
service restart is not data recovery. Cache changes themselves are recomputable.

## Local proof and remaining acceptance

The baseline failed-clear regression shows adoption advancing before clear and
skipping the next retry. Fixed code retries and only acknowledges completed
clears. Independent marker-delete/replacement controls reproduce the false/null
or competing acknowledgement and now return500 `generation_marker_changed`.
Two independent interpreters retain warm100 after underlying125, then both adopt
the same identity and serve125 after signed invalidation with unchanged PIDs.

The actual command was also executed against a local HTTP adapter invoking the
real FastAPI router and the actual TypeScript signing/path handler. It moved a
warm100 response to125 and acknowledged all10 paths; the county pattern used
type`page`. Wrong secrets and `/etc/passwd` were rejected. Next's `revalidatePath`
was a side-effect spy, so this proves signatures/path/CLI contracts, not ISR or
production browser rendering. Independent final controls cover52 backend cases
and129 runner cases; original failures/versions remain frozen in the bank.

Inherited acceptance: the single manifest, signed invalidation-before-frontend
order and generation-key late-fill fixes are retained. Completed here: actual
startup origin/file equivalence, fresh bounded topology/signing/writer evidence,
failed-clear/marker-ack fixes, loaded status and executable approval/refresh path.
Still pending: final code/config loaded in both providers, private runtime key
equality at every target (workflow after final Actions approval), S01 recovery and
writer reservation, actual approved source seed/full validation, each real worker
acknowledgement and changed API/browser render without restart/redeploy. #231 stays
open until those original criteria are met. Discoveries fit #231; no duplicate
issue or production corruption claim is warranted.

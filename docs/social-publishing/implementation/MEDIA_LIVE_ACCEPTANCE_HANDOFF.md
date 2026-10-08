# Media live acceptance and operator preparation (#490)

Status on 2026-10-08: **live acceptance incomplete; media remains disabled by
default**. This scope builds on #513 and #517 at review base
`bd46832156cb921173fea32d9d9698d696a676dc`. It adds bounded database observations,
a disposable browser fixture, and strict receipt/signer/operator boundaries.
It creates no live verifier, scheduler, bucket, credential, migration,
deployment, production write or enablement decision. Keep #490 open.

## Read-only provider discovery

These are actual UI/configuration observations, not authenticated acceptance
receipts. Times are UTC on 2026-10-08. No secrets were revealed, and no provider
configuration or object was changed. The scope is only the visible account,
service and project below; absence there is not an account-wide discovery claim.

| Time | Source and identity | Observation and remaining gap |
| --- | --- | --- |
| 19:57–19:58 | Local configured variable names and repository variable metadata | No configured `SOCIAL_MEDIA_*` names were found. Source-evidence R2 variables describe a different workload; their values/tokens provide no social-media authority. |
| 20:00 | [Cloudflare R2 overview](https://dash.cloudflare.com/6929fa03fad58c2f93c70196ec498c69/r2/overview), account `6929fa03fad58c2f93c70196ec498c69` | The complete visible table (pagination disabled) has `audit-source-evidence-recovery-v1` (5 objects, displayed 53.56 MB) and `audit-source-evidence-v1` (9 objects, displayed 53.57 MB). Displayed MB are rounded UI values. Neither is a designated social bucket. Token metadata concerns source/recovery workloads; no token secret was accessed or reused. |
| 20:01; environment names rechecked 20:15 | [Render service](https://dashboard.render.com/web/srv-d6hr3t5m5p6s73bomqu0), `srv-d6hr3t5m5p6s73bomqu0` | Docker Starter web service, Frankfurt, live deployment `dep-db3oskc9v7es73dtuvc0`, commit `2d3cd5959df1914bf068cb0381057d1bcbbabf81`, URL `https://audit-app-4pwa.onrender.com`; automatic deployment shown off. The 31 visible environment names contain source-evidence names and no `SOCIAL_MEDIA_*` names. This build predates the review base. This web service has not been designated or accepted as the always-on inspection host. |
| 20:07 | [Vercel domains](https://vercel.com/rodgers31s-projects/audit_app/settings/domains), project `audit_app` | `https://www.auditgava.org`, `https://www.auditgava.com` and `https://auditapp-nine.vercel.app` show valid production domain configuration. Naked domains show redirects/DNS recommendations. The exact social upload origin is still undesignated; this observation establishes no current frontend build or CORS policy. |

There is no actual social bucket policy, bucket-bound least-privilege credential,
signed PUT/browser CORS, complete object inventory, backup/restore, retention,
quota, native host, API request-limit or #481 hosting/egress receipt. No synthetic
hashes or fixture identities have been substituted for those receipts.

The next read-only step needs an explicit social bucket/account designation,
one exact HTTPS browser origin, and the intended Linux/Python 3.12 inspection
host/build/configuration identity. Then retain bounded policy/public-access,
credential-binding metadata, exact-origin CORS, complete inventory and reviewed
backup/retention/quota/profile artifacts for that scope. Do not repurpose the
source-evidence buckets or credentials.

## Database-only reconciliation preparation

From `backend`, `python -B -m social.media.maintenance --help` documents the
explicit operator port. `--prepare-reconciliation --limit 20` with an explicitly
authorized database connection emits one report; `--after-asset-id <UUID>` reads
the next page. Supply a private DSN through the reviewed operator environment,
not a retained/public command transcript. No application DSN or `.env` is loaded
implicitly. Help/invalid inputs open no engine; parse errors never echo arguments.
The existing ordinary mode remains report-only; cleanup still requires its
separate explicit opt-in. Preparation and cleanup cannot be combined.

Each PostgreSQL page uses its own repeatable-read, read-only transaction with a
five-second statement timeout: database time, ledger aggregates, then at most
21 candidate rows to produce at most 20 observations plus a UUID cursor. Aggregate
work still scales with the database; a timeout fails safely rather than inventing
a partial ledger. Successive pages are separate observations, not one frozen
multi-page inventory. Recheck versions/epochs at the reconciliation port.

Reports expose asset IDs, versions, grant/finalization/lease epochs, deadlines,
storage target, held bytes/pending capacity, historical-reference status and
reason codes. They compare global and exact actor ledgers against upload rows,
flag missing/surplus ledgers, unmanaged asset rows and released legacy hazards.
They contain no actor identity, filename, object key, signed URL, credential or
receipt subject. They perform no object I/O or database repair. A zero ledger
does not establish zero physical bytes. All reports have false
`write_quiescence_proven`, `quota_release_authorized` and
`ready_original_deletion_authorized` fields.

Receipt commands, nested receipts and verifier-returned evidence are revalidated,
including Pydantic constructed/copied instances. Signed-header declarations must
be bounded, lowercase, canonical, sorted and unique; required Content-Length,
Content-Type, If-None-Match and host bindings remain mandatory. Production
`UnsupportedWriteQuiescenceVerifier` still returns no evidence.

## Required write-drain proof

Neither age, expired DB lease, a positive/negative HEAD, a DELETE result nor a
matching hash proves an earlier writer stopped. An accepted verifier must obtain
independent, retained authority for **all** browser grants and server attempts
in the exact asset/provider/bucket/upload-version/grant/finalization scope,
including grants created but never returned to the client. Expiry alone is
insufficient: a request admitted before expiry may complete later. Establish
drain or irreversible fencing of those admitted requests, synchronized expiry
semantics and bounded SDK attempts; a new writer/epoch must invalidate old proof.

Operator preparation only identifies the scope. The existing reconciler freezes
renewal, checks its lease/epochs and receipt freshness, then rechecks historical
references. Settlement retains quota; only separately eligible, proven cleanup
can reduce reservations. Unknown outcomes keep durable markers, pending capacity
and both-copy actor/global accounting. A legacy released hazard needs inventory
and a separately designed accounting repair, not another forced release.
Ready cleanup retains the original, checksum/version/ETag and historical audit
references. Automatic original deletion still needs a shared revision/deletion
locking contract; this change supplies no such authority.

## Disposable local browser and host evidence

`python -B -m scripts.social_media_browser_fixture --seconds 90` starts only
private loopback HTTP servers. CLI lifetime is 1–120 seconds, connection timeout
three seconds, accepted body ceiling 512 KiB, six possible object paths and a
64-parsed-request cap across supported/unsupported methods. Controlled tokens
are fake grants, not SigV4. It accepts no provider URL, configuration or
credential. Open the printed app origin and run its button, then the printed
foreign origin plus `/foreign` and run that button. Stored bytes exist only in
memory and are discarded with the fixture.

Executed in real Chrome: eight app checks and one separate `localhost` foreign
origin check passed. JPEG (661 bytes) and PNG (133 bytes) totaled 794 bytes;
the fixture reported two objects/23 requests and then exited with all bytes
discarded. Actual File/fetch requests exercised visible PUT/GET responses,
repeat create rejection, changed type/length, missing guard, private unsigned
read denial, exact readback and browser foreign-origin denial. This validates
the loopback harness only. Local boto3 signer tests independently exercise the
real SDK; neither lane proves actual R2 signed requests or provider CORS.

Real JPEG/PNG inspection and timeout/reaping/adversarial controls pass on the
local macOS Python 3.13 lane. A separately executed cached production-image
probe (`auditapp-prod:proof`, Linux amd64 emulated on ARM, Python 3.12.14,
Pillow 12.3.0, network disabled/read-only) found no ffprobe and the resource-limited
child refused both images with the existing limits. This is a local emulation
limitation, not an intended-host success or an observed Render-host defect.
Limits were not weakened. Native intended-host Pillow/ffprobe/resource/reaping
and request limits remain unverified. The fixture's 512 KiB body bound does not
establish the FastAPI metadata request limit or deployment ingress limit.

## Proposed separately authorized live capture

First complete the read-only scope/policy/inventory/host review. A subsequent
explicit authorization must name that account/bucket/origin/host/build/config,
run UUID, test actor and exact allocated asset/key identities before writing.
Proposed initial slice: two ≤1 KiB objects, one PNG and one JPEG, one fresh PUT
per key plus the planned rejected variations; TTL at most 300 seconds. Reserve
up to 4 KiB across quarantine/final copies in **both** actor and global ledgers,
and two pending slots. Service keys must be the allocated
`quarantine/<actor>/<asset>/source` and `ready/<asset>/original`; no arbitrary
existing key or unrelated workload prefix is eligible.

Retain actual scoped signed-request, browser preflight/PUT/GET/foreign-origin,
readback hash, host metadata operation/size/response, inventory and quota
artifacts. Record uncertain attempts and retained probes in the accounting.
Default disposition is retained and reserved. DELETE, expiry or HEAD cannot
authorize removal/release; any removal needs its own bounded authorization and
write-drain proof. Connect independent artifacts to the existing offline #517
evaluator for declaration review, then obtain an explicit owner decision. Its
review-ready result still authenticates no evidence or enables operations.

## Verification and review record

Retained observed-red defects: constructed receipt/evidence bypass (#522),
malformed signed headers (#523), private CLI parse output/empty cursor (#529),
and duplicate HTTP fields/unsupported-method request-cap bypass (#530). Tests
preserve the before-fix failures and verify the repaired boundaries. The real
PostgreSQL lane is an isolated, owned loopback container/database/schema on port
62249; it never uses the coordinator's fixed lane. Snapshot tests force a
concurrent epoch/ledger update between aggregate and page reads and verify
consistent old then fresh reports.

The final scoped PR records exact suite counts, independent adversarial and
Standards/Spec verdicts, commit and managed worktree. No billable bot review,
ready-for-review transition, merge, scheduler or live mutation is part of this
handoff. #490 and #481 remain operational gates.

After the final code changes, the complete media cohort passed **739 tests**,
with **15 explicit skips** for other unassigned PostgreSQL lanes and two existing
SQLAlchemy deprecation warnings. The two owned PostgreSQL report tests ran and
passed. The independent adversarial suite passed **104 tests**, no skips,
including all 29 observed-red regressions, with one existing deprecation warning.

Independent Standards review found zero documented violations; its one optional
duplication finding was resolved by sharing strict page validation before either
entry point accesses a session/service. Final Standards review has no remaining
findings. Independent Spec review found no in-scope defect or scope expansion,
reran 79 tests, and confirmed the storage, host/request and backup/profile gaps
above remain external gates. A fresh-process PostgreSQL preparation CLI also
passed on the owned empty database with no invented ledger or authority.
Changed Python sources parse with Python 3.9 grammar; a Python 3.9 runtime was
not exercised. The owned PostgreSQL container was stopped and removed; no
volumes were created. Disposable browser servers exited and discarded bytes.

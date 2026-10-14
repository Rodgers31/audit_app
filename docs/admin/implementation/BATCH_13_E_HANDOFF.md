# Batch 13 Lane E durable audit release handoff

Lane E delivers the admission repair and owned release acceptance in
[draft PR #656](https://github.com/Rodgers31/audit_app/pull/656). Production
migration, certification, activation and authenticated deployed acceptance remain
pending under #611; #545, #583 and #554 remain open. This document and the
[release runbook](BATCH_13_E_RELEASE_RUNBOOK.md) grant no production execution
authority.

## Source and publication identity

| Identity | Exact value |
| --- | --- |
| Chat | `01a1372d-f0b8-7eb0-a517-7113460e1fbb` — Batch 13: durable audit release acceptance |
| Owned managed checkout | `/Users/roger/.codex/worktrees/dfc2/audit_app` |
| Exclusive branch | `codex/batch13-durable-audit-release-acceptance` |
| Assigned accepted base | `c8970e3953717fc0f0ca3a54e22f7e3e509eec0f` |
| Assigned accepted tree | `1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8` |
| Final implementation commit | `cc9a7ab661c9415fc31ed92a69a708ffa7b28cd2` |
| Final implementation tree | `4d80ee5a2104f5b53c1a9deb04e5693800d921d8` |
| Additive audit revision | `a611b12a0001`, directly after `e602b11a0001` |
| Migration SHA256, unchanged | `4f496ff1993c2f1155b8b938f6364bc377d15315112dc082edae490a09d4dc20` |

The final implementation commit contains all product, test and runbook changes.
The subsequent handoff commit adds this document only. Its exact published
head/tree, PR readback, complete source inventory, replay receipts and contract
hashes are bound by the external `PUBLICATION_V1.json`; a commit cannot contain
its own hash. The final `MIGRATION_CONTRACT_V2.json` binds that publication and
the separate baseline contract. Both documents are in the evidence root below.

Initial Lane E preparation contract `MIGRATION_CONTRACT.json` has SHA256
`fcc0b749eb23aaf1914ae66ae271b62efb68d005a1627c45d245d877fa01f828`.
Lane D `BASELINE_RELEASE_CONTRACT_V3.json` has SHA256
`6ef6eb0bf7d5fb0d3ed6b03e8ee43f4ad8426fab5ac17b7daf6215a80eec3c14`,
published source `9cb9cfc37d7c8881e857892171eb38e8bac4ca62`, tree
`72874dec40bb0455802219748c331a70b73e2d15`, draft PR #651. Its target is
exactly `e602b11a0001` and excludes audit. These hashes were exchanged through
the shared preparation packet before owned rehearsal. The coordinator must
refresh both final contracts before a combined freeze or operational decision.
No shared source edit was required.

## Implemented behavior

Audit admission now refuses elevated reader flags, unsafe reader/writer group
flags or parent memberships, missing required writer grants, and effective
authority beyond the private audit contract. It includes schema CREATE,
sequence SELECT/UPDATE, audit ID INSERT, protected table/column mutations and
REFERENCES, including REFERENCES granted directly to the connected reader.
Native role and privilege regressions returned HTTP200 before repair and the
private sanitized HTTP503 after repair.

The existing migration, root xid8 capture, append-only triggers, RLS, router,
models, writer transactions and frontend are unchanged. New tests execute the
actual independent general helper and Users provider writes, shared dispatch
acceptance, and reconciliation Core INSERT. The source census includes the
general helper even though no current production caller was found. An owned
writer invocation does not establish deployed caller effects or discover
external writers.

## Acceptance and retained failures

Evidence root:

`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH12_CONTINUATION_V1/NEXT_AUTHORS_V1/E_durable_audit_release_acceptance`

| Executed selection | Outcome and evidence |
| --- | --- |
| Exact accepted-base privileged-role regressions | 9 failures, no skips/setup errors, `ROLE_RED_CURRENT_V1` |
| Effective group-grant regressions on the initial role repair | 8 failures, `ACL_RED_CURRENT_V1` |
| Connected-reader REFERENCES regression | 1 failure, `READER_REFERENCE_RED_V1` |
| Final current Python 3.13.9 / SQLAlchemy 2.0.54 | 246 passes, zero failures/errors/skips, `NATIVE_CURRENT_FINAL_V2` |
| Final minimum Python 3.12.14 / SQLAlchemy 2.0.23 | Same 246 case identities and outcomes, `NATIVE_MINIMUM_FINAL_V1` |
| Affected frontend unit selection | 70 passes / four suites / no pending cases, `UI_UNIT_FINAL_V2/jest.json` |
| Actual migrated API and browser journey | One pass, no skipped/unexpected/flaky/retried execution, `BROWSER_CURRENT_V1/browser/report.json` |
| Independent Spec and Standards reviews | No remaining actionable finding; source-bound normal/optimized transport and actual fixture AST controls |
| Independent acceptance-reader review | 36 actual CLI controls: four valid accepted, 32 hostile refused under normal and optimized Python, `reader-review-v1/RESULT_V2.json` |

The final publication packet additionally binds clean published-head native
replays to these exact product bytes. Complete commands, environments, stdout,
JUnit/JSON case identities, generator/source hashes and cleanup readbacks are
retained. Counts overlap and are not additive unique coverage.

Native execution used PostgreSQL 17.11, Linux aarch64, digest
`public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.
Current/minimum labels refer to the supported Python/SQLAlchemy runtimes, not a
PostgreSQL version matrix. No native amd64 or production 17.6 claim follows.
The owned epoch reset and five actual SQL xid8 boundary controls do not claim
natural rollover through billions of transactions. All 32 new acceptance cases
execute, including more than 64 subtransactions, writer ownership, empty legacy,
continuous capture and retained/fresh incarnation revocation. The retained cohort
also covers the lower-ID late-commit race, snapshots, expiry/scope, freeze/rewrite,
restore, append-only retention, roles and malformed/partial storage refusal.

The frontend used Node 22.19.0 on macOS arm64 and 902 borrowed installed packages
verified against exact lock SHA256
`46569a23bd8d750b57e2d0dc44b0ddf6c8498a27c22ea82d0a8e5c80b88858dc`.
Two unchanged `test.each([Overview, Audit])` cases share one displayed Jest name;
the source-bound file and ordinals 17/18 distinguish the executions. Literal
component-specific display identity is not claimed. The earlier `UI_UNIT_V1`
command passed but lost its temporary JSON, so it is insufficient identity
evidence. Frontend command-recorder counts of zero mean no JUnit was parsed;
the retained Jest and Playwright reports supply the actual counts.

Earlier native UUID/search_path/timezone fixture failures and a reconciliation
teardown error remain NOT_ACCEPTED. The fixture repair uses an independent
NullPool connection, protects setup, independently attempts close/dispose/
admission restoration and preserves all primary/cleanup errors. Both complete
final runtime replays pass those repaired bytes. The failed database's identity,
rows and provenance were retained in `retained-v3-case-cleanup.json` before
normal DROP; database and roles were read back absent.

Acceptance reader V1 refused the duplicate Jest family. V2 wrote an internally
successful diagnostic then exited 1 on tuple/JSON-list readback mismatch. Its
unchanged inner verdict is not accepted evidence. Author classification is
NOT_ACCEPTED in `ACCEPTANCE_V2_REFUSAL_SUPPLEMENT_V1.json`, SHA256
`a4009e9a1f64006b3aa7620383c210268c14523d794e4eafc0364325b3a18d4b`;
the supplement identifies the historical exit source and performs no new child
execution. V3 requires
typed outcomes, exact runtime/source/recorder bindings, unique native identities,
the narrowly qualified Jest occurrences and one browser execution without retry.
`ACCEPTANCE_V3.json` and the publication replay acceptance are scoped owned proof.
No old failure, verdict, generator or receipt was overwritten.

## Resource accounting and operational limits

Initial storage checks failed on the 180-second legacy measurement timeout and
the first V2 cache-binding mismatch. Both remain preserved. The coordinator's
superseding V2 policy and corrected Python invocation permitted resumption on
the unchanged baseline and shared 10GiB limit. Fresh pre/post phase measurements
are retained; no rebaseline or allocation relocation occurred.

Both original owned clusters were disposed through the unchanged guarded helper;
their container/network/reset IDs and helper absence verdicts remain retained.
The original minimum cluster's anonymous volume ID was not separately retained
before cleanup, so independent exact-volume absence for that historical cluster
is unproven. The published-head replay records its volume before cleanup and
verifies that exact resource absent afterward. `RESOURCE_CLEANUP_V1.json` records
final exact IDs, process/temp absence and free permitted ports 55545/18045/13045.
No peer resource, borrowed runtime or protected storage-cache input was cleaned.
The managed checkout, compact evidence, read-only dependency symlink and owned
frontend build output remain available for review.

Unknown pre-trigger provenance makes the entire population unavailable, including
filters hiding unknown rows. Do not backfill from xmin, IDs or timestamps.
Same-identity restores, physical clones and privileged forged/deleted history
cannot be certified by catalog checks alone. External authority must be revoked
before restore/import/PITR/promotion; separately witnessed continuous custody is
required. Backup restoration, every deployed writer/reconnect/privileged channel,
provider feasibility, actual production revision/roles and authenticated deployed
API/UI acceptance remain coordinator release prerequisites. No production mutation,
paid review, Actions enablement, merge, financial source write or certification
was performed in this author phase.

Next: freeze the combined reviewed source; refresh both contracts and operational
identities; complete baseline `e602b11a0001` independently; then follow the
runbook's separately authorized audit backup, migration, refusal/certification,
deployed acceptance and staged reopening steps. Abort on unknown/ambiguous state
with custody revoked, writers fenced and immutable evidence retained.

Concrete proposed skill lessons for coordinator deduplication: recheck special
role flags independently of inherited ACLs; inspect group authority as well as
the current reader; put connection setup inside protected cleanup and preserve
all cleanup failures; bind duplicate displayed test names to exact source and
occurrence; refuse a receipt when its generator fails after writing it. The red,
fault and malformed-reader packets above reproduce each lesson. Global skills
were not edited.

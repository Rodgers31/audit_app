# Round18 exact correction integration — 2 October 2026

CPI recovery now requires both original shared sources, in the reviewed identity
order and with their source-authority fields intact. Previously a caller could
remove `plan.original_sources`, or replace an original source with its changed
current row, recompute the receipt digests, and recover the three CPI facts despite
protected source drift. The intact receipt correctly refused the same drift.
This is a conditional correction-tool defect under #319, not observed production
corruption. The guard runs in `recover()`, shared by direct `run()` callers and
the CLI's `--recovery` path; forward preparation already checked these sources.

Four committed/dry-run omission/replacement regressions failed on baseline
`4acd7c0270a78a035557575125d77743ac2dbd5d` with `DID NOT RAISE`. The fixed focused
CPI/OAG/connection selection passed **122 tests, zero skips**, in 41.10 seconds.
Independent review executed 22 final controls: 20 context refusals before
receipt/writes, healthy allocated recovery, and healthy source/extraction reuse.
All 15 current issue snapshots were searched; this belongs to #319's existing
shared-source preservation requirement. No separate issue is proposed.

## Fresh prospective inputs

S02's one READ ONLY REPEATABLE READ rollback capture ran
**2026-10-02 21:37:17.981292–21:37:53.515834 UTC**. Its immutable
`ROUND18_SESSION_2_DATABASE_READONLY.json` SHA256 is
`4d6da7c1a48a6b1fc95d5a19ebe21698ed6c7ddac3e28af52d27b27fcf4f83f5`.
The shared marker, all three declared capture hashes, generators, section hashes,
counts and full row column sets were checked. No section was omitted.

The capture supplies the formerly missing country/period, CPI national type/date
peers, PDF URL/page reuse candidates, sequence observations, OAG reference and
extraction-identity peers, complete shared2541 audit/extraction rows and1823
dependencies. Each exact CPI/OAG identity has one peer; both reviewed CPI source
URL candidate sets and their page2 extraction set are empty. These are observations
at the recorded times, not reservations of future IDs. Sequences and active-session
observations are not MVCC snapshot state.

The existing tools produced fresh full CPI/OAG before/after plans. Publisher
proposals bind current1840/2383 complete rows and source FK sets; existing guarded
SQL changes only their publisher columns, retaining loan426. County proposals bind
all47 complete identities/metadata and the same four Nairobi/Mombasa cells; their
SQL preserves legacy routes and all other metadata. Existing SQL guard facts still
match, so no alternate executor was introduced. Full plans/SQL are retained0600
outside the repository/shared bank; `ROUND18_CORRECTIONS_PREPARED.json` indexes
their hashes and scope for the coordinator.

Publisher authority remains the dated1October CBK/Treasury observations. Retained
Treasury/Constitution bytes were hash checked; exact KNBS/OAG PDFs were hash checked
and replayed by the existing preparation tools. No new publisher request occurred
in S03. Sources1707/1718/1836 are retained; zero FKs are not retirement authority.
Population79's accepted criterion remains satisfied and untouched.

## Executed operation integration

Owned PostgreSQL17.11 at loopback5593 materialized complete captured government
row subsets: 608 audits,583 extractions,77 economic indicators,20 sources,47
entities,64 population rows, two GDP rows and loan426. Source FK relationships
were projected as NOT VALID constraints to preserve captured rows whose other
parents lie outside the capture. Relation types/enums, roles, RLS, extensions and
triggers are not a full production schema/restore claim.

**21 operation controls** passed: actual preparation/default rollback, exact
publisher/four-cell forward/inverse, OAG three-text/extraction/hash correction,
CPI source allocation and inverse, forged financial-plan/full-after-image drift
refusal, archival source reuse, and full materialized inventory comparisons.
The unchanged cohorts include all579 other2541 findings, captured73 annual/World
Bank economic rows, all64 population rows, all47 project arrays and1823 dependents.

**Eight additional serialized controls** passed. Applying code cells makes the
original full OAG entity plan stale: the tool refused it before receipt/writes.
A fresh local plan then applied OAG and CPI alongside publishers/codes; reverse
CPI → OAG → codes → publishers restored the complete local baseline plus already
retained CPI archival rows. These modeled after-images are prospective only.
No cleanup or five-source catch-up state was synthesized for production use.

CPI prepare/default dry-run left rows and allocation sequences unchanged. Forward
allocated two source rows and two extraction rows from captured sequence state;
inverse restored facts while retaining those archival rows and advanced sequence
state. Independent injected allocating-forward failure rolled back rows but
consumed sequence values and retained intent without a resolved receipt. Rollback
must not be called read-only proof; intent alone does not prove a commit.

The first test launch had44 passes/74 setup errors because Docker's internal
network did not expose the recorded host port. Correcting only the owned network
made the original118 focused tests pass, then the fixed122 selection passed.
Failed receipts remain immutable. No skip, retry, timeout or quarantine changed.
All runs disabled dotenv/Pydantic files before imports, used allowlisted synthetic
configuration, blocked provider HTTP/application-engine connections, and kept
lifespan/seeding/warmup inert. Application-engine connection attempts were zero.

Receipts are `ROUND18_SESSION_3_TESTS_RECOVERY_RED.log`, `TESTS_FINAL.log`,
`INTEGRATION.json`, `COMPOSED_INTEGRATION.json`,
`INTEGRATION_PROVENANCE_DELTA.json`, `ADVERSARIAL_PATCH_RECEIPT.json` and their
immutable generators in the shared bank. The provenance delta clarifies that the
integration receipt's `code_commit` field is baseline HEAD plus the tested
uncommitted fix, and binds the actual tested file hashes.

## Remaining original acceptance

#319/#273/#379 remain open for actual approved correction, recovery and
source/API/rendered acceptance. This capture is neither a complete backup nor
production readiness. The coordinator still needs consistent full acquisition
and compatible isolated restore, agreed writer window, independently accepted
operation recovery and final approval of exact current actions. Reprepare affected
plans after preceding real writes; recapture cleanup after actual code/OAG
correction/catch-up. Actual CPI must generate its own resolved allocation receipt;
the local one is not a production inverse. Actions remains OFF. S03 performed no
production/provider/GitHub write, seed, cache, configuration or service operation.

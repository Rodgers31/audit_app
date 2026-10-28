# County aging continuity and selected producer boundary — 28 October 2026

Related acceptance issue: #800. This change does not activate acquisition or
establish production adoption. Historical B83/B86 disable statements saying that
every ordinary stock write clears pointers are superseded by this narrower rule.

The two existing `SEED_PENDING_BILLS_AGING_ENABLED` and
`SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED` switches independently select **new
acquisition** only when their value is the literal `true`. They are not reader
visibility switches. Unset, `false`, and `TRUE` acquire neither selected cohort.
Neither default, repository variable nor workflow forwarding changes here.

After an accepted acquisition, an ordinary stock-only reread may retain that
population's immutable extraction pointer only if it was selected by the current
stock **before** the write, the source/batch/coverage are unchanged, all incoming
stock cells qualify against the same reviewed PDF artifact, and the retained
cohort independently still qualifies. County locks serialize this decision with
stock replacement; source metadata is refreshed from PostgreSQL, including in a
long-lived Session. Another source, stock amount, fiscal year, absence statement,
artifact, failed source, corrupted receipt or invalid extraction cannot elect an
old historical cohort. A same-day A→B→A retry does not revive A's old pointer.
Failed writes roll back with the existing savepoint and caller-owned commit.

The fetcher bypasses only the stock **parse-result** cache when this exact source
has an active cohort. This supplies fresh stock cell evidence without acquiring
unselected aging cohorts, redownloading on public requests, or treating cached
JSON/sidecars as authority. Inactive source history does not force the heavy
parser. Original acquisition time stays unchanged; retained validation and native
report record IDs remain separately bound to the exact current ingestion job.
No source bytes, acquisition dates or old extraction rows are rewritten.

The reader also checks current source availability, Kenyan publisher identity and
any legacy MD5/current PDF artifact metadata against the reviewed edition before
returning a cohort. Both reviewed hashes identify the same retained report:
SHA256 `919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20`,
MD5 `dfafc8c1d53ea3258ea485ddec0b3fd6`, 53,561,130 bytes.
This is an edition contract, not permission to accept a publisher reissue without
review. Missing bands and source discrepancies stay explicit. Assembly/executive
populations remain separate; national/combined aging remains unavailable.

## Capacity and rollout

Use the existing separately selected native producer (#504). Full PDF parsing is
not supported on the 512 MiB Render API/worker. B103's 768 MiB full-native attempt
was OOM-killed; its separate retained-parser component used about 889 MiB peak
under 2 GiB. The B116 external receipts measure the complete offline producer,
private migrated PostgreSQL and API replay under a 2 GiB, one-CPU bound. These
local Linux/Python3.12 results do not certify serving-runtime parity, GitHub runner
performance, production storage, egress, quotas, live 600s domain/1320s total
budgets, or current official HTTP authority. Keep those gates distinct.

Before rollout, coordinator must verify reviewed release and selected runner,
perform authorized bounded dry-run and write admission, acquire a genuine county
HTTP receipt if none exists (never promote local JSON), verify current edition
and publisher post, commit exact successful-job lineage, and reconcile the actual
public API and Chrome UI. Persist the intended independent flags on that selected
producer for future editions; a correction clears old aging until the correction
is separately qualified. Existing source selection, time limits, grants, workflow
states and repository variables remain unchanged by this PR.

To stop new acquisition, leave both flags off. This intentionally preserves
already qualified unchanged historical facts. To hide an adopted cohort
immediately, coordinator must use a separately authorized pointer invalidation or
reader rollback; do not manufacture an unqualified stock refresh as a revocation
mechanism or delete receipts/history. A future valid new cohort requires a fresh
in-process acquisition envelope. No activation, production write, merge/deploy,
Chrome control, publishing/upload/worker enablement or new paid service occurs in
this engineering lane. #800 remains open for live adoption/browser/capacity gates.

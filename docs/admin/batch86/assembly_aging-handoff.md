# B86 county-assembly aging handoff — related #800

Base/main at author start: `a459834e31280b1e81b0604d16d687bc9ad7fffe`.
Branch: `codex/b86-assembly_aging`. This is a draft author delivery for coordinator
integration. No production ingestion, migration, configuration, grant, source-plan
selection, admission SHA, merge or deployment was performed. B87 adds only
default-off workflow flag forwarding as described below.

## Implemented source-to-reader chain

The existing bounded county pending-bills acquisition can now prepare a separately
scoped assembly cohort alongside the executive cohort from the same PDF. Both
opt-ins use freshly parsed same-download payables. When both are selected, the
aging parser opens that PDF once and reads only PDF pages 53–55. Page requests
query stored evidence only; no PDF/object/HTTP read runs on a page request.

Assembly uses schema version 2, scope `county_assembly`, extractor
`pending-bills-assembly-aging-v2`, and source metadata key
`pending_bills_assembly_aging_v2`. Executive version 1,
`pending-bills-aging-v1` and `pending_bills_aging_v1` remain readable. The
existing `SourceDocument`/immutable `Extraction` storage is reused: no model,
migration, dependency or access-policy change is needed. Assembly has its own
fingerprint, extraction pointer and source-cell population identities; executive
observations cannot be substituted or relabelled.

The existing county writer savepoint/row locks cover stock, receipts, both
cohorts and their active pointers. It never commits the caller's transaction.
Ordinary later stock writes clear both pointers, retaining extraction history.
Replays validate the incoming acquisition before deduplicating a cohort; receipt
history can append across reopened sessions under the existing receipt adapter.
Same-date replacement titles bind new source/batch authority; old pointers remain
historical. Older stock and unreviewed byte reissues refuse. Current stock source
and publication batch, immutable caller stock context, and refreshed persisted
cohort/receipt evidence remain required. Reads use one bounded document query and
up to two extraction/receipt query pairs (five queries for both populations).

The existing summary/county API `aging_observations` map serves the actual
assembly population. Legacy unscoped `aging_buckets` and complete totals remain
null. National and combined populations retain structured absence. The debt panel
uses separate assembly source/table/version checks, EN/SW/plain scope/caption/
qualification copy and active-language dates; it distinguishes printed-total
coverage from all-four-band coverage. Loading and request failure remain separate
from source absence. Missing cells are text, never invented zero bars. The
assembly summary chart is withheld because its bands do not equal its printed
total. Existing executive presentation and Nandi refusal remain intact.

## Independently qualified retained source

Official CoB [FY2025/26 report](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482),
53,561,130 retained bytes, SHA256
`919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20`.
Both PDF pp.54–55 / printed pp.20–21 were independently viewed and extracted.
This reused B83 bytes; no fresh source transport or acquisition receipt was
claimed. The small attributed JSON fixture contains only the two assembly table
extractions, source URL/hash/size/caption/pages; the full PDF remains outside Git.

Table 2.12 caption explicitly identifies county assemblies as of 30 June 2026.
Its publisher header is truncated to `County Ass )`; the total header explicitly
states Kshs millions on both continuation pages. Four raw source year bands are
Under one year / 1–2 years / 2–3 years / Over 3 years. Table 2.11's executive
continuation and executive-only Nandi note on p.54 are excluded from assembly.
The narrative above Table 2.12 confusingly references that table while discussing
executives; it does not override the explicit assembly caption or cells.

All 47 assembly printed totals are present; only 36 counties have all four bands.
The 11 missing-band counties are Bungoma, Kajiado, Kericho, Kilifi, Kirinyaga,
Kisii, Kisumu, Kitui, Kwale, Narok and Uasin Gishu. Narok prints 17.92 million with
four blanks. Uasin Gishu prints 0.00 with four blanks; Kirinyaga/Kisumu print zero
totals with four dashes. Those totals never authorize zero-filled bands. Assembly
Nandi and Lamu print zeros throughout, which remain zero. Executive Nandi remains
unavailable under its separate publisher note.

| Assembly source measure | KES |
| --- | ---: |
| Under one year, printed | 2,481,980,000 |
| 1–2 years, printed | 1,780,020,000 |
| 2–3 years, printed | 639,070,000 |
| Over 3 years, printed | 1,402,370,000 |
| Printed total | 6,321,350,000 |
| Sum of printed bands, calculated comparison only | 6,303,440,000 |
| Table 2.10 known assembly sum, separate source comparison | 6,375,350,000 |

The KES17.91 million band/printed-total difference and KES54 million
Table 2.10/Table 2.12 difference remain explicit. Publisher asterisks on p.55
identify discrepancies versus Table 2.10. Row arithmetic/missingness and known
column sums are retained without silent reconciliation. These are reported
source accounts, not complete county liabilities or a certified combined total.
Neither August2026 report month nor 30June stock date is a full publication date.

## Default-off and activation matrix

| Executive flag | Assembly flag | Future native fetch behavior |
| --- | --- | --- |
| absent/false/TRUE | absent/false/TRUE | Existing payables path; no aging cohort |
| literal `true` | absent/false/TRUE | Existing executive-only cohort |
| absent/false/TRUE | literal `true` | Separately scoped assembly cohort |
| literal `true` | literal `true` | Both cohorts, one shared download/aging PDF open |

Names are `SEED_PENDING_BILLS_AGING_ENABLED` and the new
`SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED`. B87 coordinator review adds the
root-owned workflow forwarding with a literal `false` fallback, independently
of the executive opt-in. The existing workflow contract test reproduced the
missing forwarding before this change and passes afterward. No repository
variable, schedule, domain selection, runtime budget or admitted revision was
changed. Source/runtime/download qualification and live rollout remain separate
acceptance work; both aging producers stay off in production.

No duplicate publication-date store or social eligibility adapter was added.
Lane802's proposed native authority interface remains a future separately
accepted dependency. A stock date or assembly aging amount cannot qualify a
publisher-date notification. Publishing/uploads/native workers/dispatch/automatic
approval/scheduling/publication remain outside this change.

Disable/rollback: keep both producer opt-ins off; an ordinary subsequent county
stock publication clears both pointers. Reverting this additive code restores
the old executive reader while retaining assembly extraction history. No data
purge, backfill, schema rollback or production rollback was performed.

## Executed reviews and evidence boundaries

External evidence directory:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_86_BUILD/assembly_aging`.

Unchanged-base RED observed assembly parser rejecting the new scope argument,
with executive positive control passing. Actual helper/component RED rejected
assembly and rendered observation absence; GREEN shows the proper cohort in
English and Swahili. Final genuine-PDF parsing separately confirms both source
tables and all summary cells without an acquisition claim.

Two independent executable reviews used their own controls. Spec independently
read the actual retained source/fixture/native parser, exercised26 hostile
source controls,16 flag cases,32 actual helper/component cases, and22 malformed
reader-schema controls. Standards executed17 actual-PG cases,2 additional stock
batch/caller-context cases and30 direct hostile parser/schema cases. Counts
are separate inventories and overlap author tests; they are not added together.

Standards found two valid P2s, both author-reproduced RED then fixed GREEN:
missing/malformed notes/reconciliation could escape structured absence, and a
synthetic PostgreSQL BEFORE INSERT trigger changing the cohort version could
allow a successful writer result with invalid stored evidence. Full consumed
shape validation and refreshed post-flush cohort/receipt qualification now
refuse these cases within the writer savepoint. No deployed trigger is alleged;
this is a local storage-failure invariant. Review receipts preserve preliminary
failures and corrected source hashes. Final commit/tree binding is external.

PostgreSQL controls use an owned loopback container at host127.0.0.1:55800,
database `b83_b86_800`; Docker tests share that owned PG network namespace on
127.0.0.1:5432. Each case creates/drops its isolated schema. This tests actual
JSONB, commit/reopen, rollback, concurrent writers and two-session authority;
it is ORM-created-schema verification, not Alembic/RLS/grant or production
maintenance acceptance. Runtime is Python3.12 with the accepted base requirements
and constraints, trusted cached image layers, no production env or credentials.

Chrome used logged-in Chrome/CUA with the shared atomic lock and an inert
loopback fixture importing the actual panel/provider/styles. Actual PostgreSQL
HTTP summary and Narok responses supplied genuine source cells with explicitly
synthetic acquired bytes. English/SW/plain, assembly source amounts, missing
bands, loading/failure and combined absence were observed. Screenshot/DOM
receipts are retained. This is no claim of full keyboard/screen-reader/narrow
viewport conformance. Owned tabs and Chrome lock were released.

The production frontend build uses an owned real copy of matching frozen
node_modules (no install), passes guarded prebuild/type/lint/compilation, and uses
inert loopback API/auth values. Its expected refused API prefetch logs do not
certify live prerendered data. No hosted Action, bot review or paid preview ran.

Final author gates: **456 backend tests passed**, including all owned PostgreSQL
cases, with zero skips; **88 targeted optimized-interpreter controls passed**
(overlap the normal suite); **113 frontend tests passed** across six selected
suites. TypeScript, scoped ESLint and guarded production build passed. The two
independent review inventories above remain separate and are not summed.

Preliminary harness failures remain retained: reused sealed/bound receipts,
wrong working-directory frontend invocation, missing browser-fixture fiscal-year
metadata and an overly strict receipt-row replay count were corrected before
final gates. The browser fixture's lifespan emitted unrelated queue-schema
diagnostics against a separate inert SQLite startup database; both selected HTTP
handlers returned200 from the owned PG override. No application startup or live
operating acceptance is claimed from that fixture.

Final command/count and resource-cleanup receipts are in `STATUS.json` and
`FINAL_BINDING.json` outside Git. Source-qualified retained cells, locally tested
synthetic acquisitions and live accepted ingestion are different: only the first
two are established here. Live aging enablement/real ingestion/deployed readback
remain unaccepted coordinator work; #800/#545/#699 stay open.

## B87 review corrections

The Copilot review body on frozen head `e390793f252387ba6bfb5eb6461dae542b7ce99e`
identifies backend reconciliation/reader-note gaps and optional assembly coverage,
despite having zero inline threads and saying "No open issues". Classified as
**valid, understated**: the shared validator serves both populations. Sixteen
executable backend regressions were observed red before the fix. Ten additional
hostile comparison operands were accepted by the frozen validator and refused by
the corrected validator; these overlap the committed regression inventory.

The validator now compares all reconciliation sums, printed amounts, counts and
statuses against the retained rows. It requires the derivable missing-cell,
band-discrepancy and executive Nandi warnings, and validates supported note codes,
population/table/locator fields, duplicate warnings, comparison operands, bounds
and reported totals. The retained cohort does not contain the original asterisked
county labels or the complete companion Table 2.10 population; this validation
does not independently re-extract those source facts or recreate an omitted
external-comparison warning.

The frontend requires assembly all-band coverage in its runtime decoder and type.
Its source-shaped fixture now discloses the actual 36 complete band sets and all
11 missing-band counties alongside 47 printed totals. A related decoder defect
also admitted unsupported years for the fixed v1/v2 source contracts. Frozen
executable controls accepted 2025/2027/0000 dates and missing assembly coverage;
the corrected decoder refuses them while accepting both versions at 2026-06-30.

Focused final checks: **98 backend tests**, **8 actual PostgreSQL controls**,
**67 overlapping optimized-interpreter controls**, and **32 frontend tests** passed.
TypeScript and scoped ESLint passed. These are focused review checks, not a new
full-suite, production-build, browser, live-source transport or deployment claim.
Source discrepancies, missing cells, separate population authority and null
complete totals remain intact. No live enablement or #800 acceptance is claimed.

Evidence: `BATCH_87_REVIEW/805` under the external visualization evidence root.
The owned PostgreSQL container used no external network or host port, left zero
test schemas and was removed with its anonymous volume. The temporary read-only
frontend dependency link was removed; the shared runtime image belongs to the
coordinator. An initial wrong-directory Jest invocation and an inconclusive
frozen-module mapper attempt are retained as harness diagnostics; the final
frozen probe transpiles and directly executes the exact frozen decoder bytes.

# Five deferred OAG county volumes: readiness and publication acceptance

Prepared 1 October 2026 from `355c057a6138ed47212a5aab865f4bdf26a02177`
for [#234](https://github.com/Rodgers31/audit_app/issues/234). This is a
bounded release proposal. No live catch-up, production connection, migration,
correction, configuration change, refresh or Actions run was performed.
Actions remains OFF. The owner/coordinator controls the later release window;
Session 4 owns the shared correction/freshness decision packet.

## Evidence and scope

The inherited production observation is **30 September 2026, 22:15:02 CDT**
(`2026-10-01T03:15:02.595642+00:00`), not a fresh Session 3 measurement.
It records 141/376 cells and 2,898 findings across the three completed newer
county volumes, with audits job 3176. The latest #234 comment was read on
1 October and retains this acceptance gap. The source/coverage matrices,
not the issue's original FY2020/21 narrative, define this proposal's baseline.

The brief's `docs/operations/2026-09-30-oag/` directory does not exist at the
pinned base. Its available evidence is
[Round 6 acceptance](../2026-09-30-oag-round6-acceptance.md),
[boundary correction](../2026-09-30-oag-boundary-correction.md),
[source matrix](../../verification/2026-09-30-round6-oag/source-coverage-matrix.csv),
[production cell matrix](../../verification/2026-09-30-round6-oag/county-coverage-matrix.csv)
and the [existing serial runbook](../2026-09-29-oag-catchup-refresh.md).
No competing packet or prior receipt was edited.

[manifest.json](manifest.json) fixes the five labels, exact URLs, SHA256/MD5,
periods, source scopes, inherited source IDs and chapter receipts.
[coverage-plan.csv](coverage-plan.csv) joins **all 376** accepted
county/year/institution keys with the inherited production matrix. The
five-volume subset has 235 rows. Database county IDs are inherited identity
keys, not official three-digit county codes; local replay source IDs are not
production IDs. No prospective audit/extraction ID is assigned here.

| Order / exact outcome label | Inherited source ID | FY / audit year | PDF pages / chapters | Accepted local findings / conditional new cells |
| --- | ---: | --- | --- | ---: |
| 1. `2023/2024 assemblies` | 2540 | FY2023/24 / 2024 | 217 / 47 | 541 / 47 |
| 2. `2022/2023 executives` | 2537 | FY2022/23 / 2023 | 504 / 47 | 1,041 / 47 |
| 3. `2022/2023 assemblies` | 2536 | FY2022/23 / 2023 | 219 / 47 | 513 / 47 |
| 4. `2021/2022 executives` | 2535 | FY2021/22 / 2022 | 546 / 47 | 1,082 / 47 |
| 5. `2021/2022 assemblies` | 2534 | FY2021/22 / 2022 | 222 / 47 | 532 / 47 |

All five were registered/not fetched in that observation: `FAILED` is the
provisional source registration status, not proof of a failed download. MD5,
extracted MD5 and latest attempt were absent. Keep absence distinct from a
sourced zero or an actual partial/refused attempt.

The conditional delta is **3,709 findings and 235 cells**: 541 + 1,041 +
513 + 1,082 + 532, each backed by 47 unique accepted matrix keys. With the
same editions and a fresh unchanged baseline this yields **6,607 newer county
findings and 376/376 cells**. It is not a global audit total, a guaranteed live
write count or a new preservation receipt. National findings and legacy
FY2020/21 rows are excluded from this total. The 27 September replay's
2,338 → 8,945 global rows belong to a different disposable baseline and must
not be used to predict production totals.

Fresh preparation checked the eight cached PDF byte hashes and page counts
against the accepted manifest, including the three already ingested sources.
Their complete 47-chapter extraction receipts are inherited exact-byte
evidence; the full replay was not repeated. Five distinct bounded HTTP200
official HTML captures confirmed the parent and four year pages still link
the eight exact URLs (six raw GETs including one helper retry; final assembly
reused captured pages without polling).
This does **not** prove the publisher has kept live PDF bytes unchanged:
cache hashes are fresh; live PDF hashes must be checked during release.
See [verification-receipt.json](verification-receipt.json) for timestamps,
input/HTML hashes, local paths and limitations. The
[OAG listing](https://www.oagkenya.go.ke/county-executives-assemblies-reports/)
and [FY2023/24 page](https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/)
establish the year association even where filenames only contain `2024`.
Listing absence of a later edition is not a zero-finding assertion.

Each FY covers 1 July–30 June and `audit_year` is the ending year. Retain
the separate Executive/Assembly auditee and subreport/opinion, canonical
county, PDF page, printed page when present, source URL/edition/hash and
extraction provenance. Do not collapse both institutions into one county
record, turn missing printed pages into guessed offsets, or infer wrongdoing
or a scalar amount from a multi-amount finding. Preserve sourced zero, absent,
withheld and conflicting values and the source's units separately.

## Actual path and budget contract

The actual workflow is [seed.yml](../../../.github/workflows/seed.yml): manual
`domain=audits` selects the audits domain, **not a five-source allowlist**.
It runs migrations/schema parity first, county volumes first, then eligible
national/legacy candidates if start budget remains. Bootstrap must be off.
Session 4 and the release owner must review this broader eligible source set;
if authorization permits writes only to five exact URLs, this dispatch alone
does not enforce that boundary. Stop and resolve the execution scope through
the existing release process; do not point the loopback-only rehearsal tool at
production or invent another ingestion path here.

Code inspected at the pinned base:

- `backend/seeding/domains/audits/__init__.py`: registration and descending FY,
  Executive-before-Assembly ordering; elapsed cutoff before fetch; per-volume
  commits; explicit processed/current/deferred/failed/partial outcomes; older
  sources remain eligible afterward. Covered per-county PDFs are not offered
  alongside the combined volumes, preventing duplicate FY2021/22 findings.
- `backend/seeding/extractors/reconciliation.py` and
  `backend/seeding/extractors/oag_county_volume.py`: unchanged extracted MD5
  with stored extraction evidence uses the current-source path; changed
  evidence goes through reconciliation. Do not clear MD5s/metadata to force
  re-extraction or approve retirements to make a run green.
- `backend/seeding/domains/audits/loader.py`: source/extraction chain and
  existing county/period resolution; fact rows keyed by extraction ID. The
  shared `services/publication_gate.py` controls public eligibility.
- `backend/seeding/county_audit_coverage.py` and
  `backend/seeding/staleness.py:check_county_audit_coverage`: attributable
  institution/year evidence, exact discovered inventory and run gaps remain
  separate from counts. Presence is not complete text extraction.

The fresh local settings readback was: start window **240s**, per-domain hard
timeout **600s**, county download timeout **120s**, generic download cap
**120 MiB**, OCR **off**. The workflow defaults OCR **on** (30-page OCR cap)
and total seed budget **1,320s**; actual release settings/overrides must be read
back from the approved run. The inherited local rehearsal instead imposed
**40 MiB/download, 900s/worker and 6 GiB sampled RSS**, OCR off. These are
different contracts. Local parse timings or synthetic 100s-per-volume costs
are not production duration/memory forecasts or permission to enlarge budgets.

## Coordinator execution, resumption and recovery

Use [decision-checklist.md](decision-checklist.md) as the decision ledger. All
live gates are pending; no token, credential or signed request is prepared.

1. Freeze the reviewed merged main/backend/frontend SHAs and current migration
   graph. This docs-only change adds no migration. The existing workflow
   performs `alembic upgrade head` and schema parity even for audits-only seed;
   independently review any intervening migration/data effect with Session 4.
   Never stamp a schema to bypass parity. Capture the actual live revision and
   parity receipt only through later owner-approved release access.
2. Reserve one exclusive writer window under `seed-production-database`
   (`cancel-in-progress: false`). Confirm billing/access/runtime budget and
   cache/storage capacity. No correction, bootstrap, source retirement or
   concurrent seed may overlap. Record the owner and the exact permitted
   national/legacy behavior before enabling Actions for the final batch.
3. Take a fresh encrypted baseline and recovery backup of every audit,
   extraction and relevant source/job row, related country/entity/period
   identities and sequences, including columns absent from the ORM. Bank
   per-ID full-column fingerprints and immutable source URL/edition/MD5/
   SHA256/current-extraction/attempt state. Resolve current IDs by exact URL
   and identity rather than assuming the inherited IDs remain authoritative.
   Record the current five-source deferred set and the 376-cell receipt.
   Verify restore on an owned disposable copy; keep backup contents out of
   GitHub/repository receipts. A count-only baseline is insufficient.
4. Check official year association and hash live bytes once per selected
   edition, bounded by the approved downloader limits. Stop on changed bytes,
   URL/period/institution identity drift, new listing scope, missing access or
   inadequate budget/recovery. An accepted local edition cannot authorize a
   silently replaced live edition.
5. After the owner's later explicit final-batch approval, dispatch **one** run
   on the reviewed main and retain its run ID/head SHA:

   ```sh
   gh workflow run seed.yml --repo Rodgers31/audit_app --ref main \
     -f domain=audits -f dry_run=false -f run_bootstrap=false \
     -f run_validation=true
   ```

   This command is a proposal and was not executed. Confirm the resolved main
   still matches the frozen review before dispatch; record the run's actual
   head SHA and stop on drift. Do not enable or rerun Actions in this session.
6. After each pass, retain the entire audits job/source ledger: discovered
   count and labels, processed/current/deferred/failed/partial sets, discovery
   errors, `documents`, deferred older documents, source hashes, committed new
   audit/extraction IDs and all prior-row comparisons. Account for every
   discovered volume exactly once. Reconcile each new source to 47 chapters,
   47 canonical counties, nonempty findings, complete attempt, no unreadable
   chapter pages/refusals, source/extraction/page/period/institution identity,
   public eligibility and the conditional cell/count comparison.
7. Earlier completed sources should be current on a later pass, subject to
   cache/download/check costs; a cutoff can defer even a current check. Require
   actual committed progress across the bounded series, not a fixed number
   of passes. The existing synthetic scheduling control gives
   `3 processed/5 deferred → 3/2 → 2/0 → 0/0`, but real runs may differ.
   Do not raise limits or disable validation to obtain that sequence.
8. A failed/partial new source, malformed outcome, unexplained count delta,
   prior-row field/ID drift, source drift or unchanged backlog without
   attributable committed progress stops further dispatches. Keep failures
   visible and diagnose with one retained run ledger/timing receipt; zero-step
   billing failures establish no ingestion/parser result. A deliberate deferral
   is neither a new code bug nor completed publication.
9. A timeout after completed-volume commits does not roll them back. Inspect
   actual source/extraction/audit state and attempt metadata before resuming;
   an absent final job summary or receipt is not proof of no writes. Resume
   with the existing downloader cache and extracted-MD5 checks. Preserve
   completed IDs, richer prior findings and explicit partial attempts. Never
   delete a cache, extraction set or current rows to restart the queue.
10. Catch-up has no generic inverse. Bank exactly which rows/fields each run
    added or changed. Recovery needs a separately reviewed reversal of those
    banked changes against the **current** full snapshot, with preservation of
    intervening evidence, references and ID/sequence integrity. Rehearse on an
    owned copy before authorizing it. Do not use whole-database before-images,
    broad source deletions, sequence resets or the three-row boundary recovery
    tool as a county catch-up rollback. After interruption, establish commit
    state first; after recovery, repeat coverage/preservation/source/public
    checks and the separately authorized refresh.

## Independent operations and publication acceptance

Preserve the existing three current source IDs **2542, 2541, 2539**, all prior
audit/extraction fields and IDs, source **1823**, population row **79 =
51,202,827**, current project arrays and later unrelated metadata. Session 4
must integrate these boundaries into its authorization ledger.

Source 2541's separate #379 correction covers audits **5545/5679/5716** and
extractions **6023/6158/6196**, three text/source-hash pairs, zero count delta.
Unchanged-MD5 seeding will not repair those stored texts. Its source, source
ID, period and other fields remain fixed. Keep the before-state until the
exact correction plan is separately approved; if that correction runs between
catch-up passes, capture a new reviewed baseline and its exact changed-field
ledger instead of waiving preservation globally.

National source **2392** has **335 proposed retirements/two revisions** and
813 inherited published findings. The proposal remains unapproved and outside
county deltas. Legacy sources **2395/2396** retain partial/refused attempts and
986/512 inherited findings. #347's historical inflation **15 → 11** acceptance
also remains separate. Full validation must address their actual reviewed
state; 376 populated cells cannot override those refusals. Do not weaken a
gate, blanket-accept reconciliation or restore old fixture arrays.

Final #234 acceptance requires all of the following fresh release receipts:

1. The existing `county_audit_coverage_receipt(session)` through approved
   read-only access yields all **47 counties × four FYs × two institutions =
   376** cells, no unexplained run/discovery gap, valid source state and
   attributable published evidence. Inspect full receipt fields, not only the
   verdict string; presence alone is not text completeness. Require actual
   complete 47-chapter source receipts and resolve changed listing scope.
2. Match actual new finding counts and per-cell identities to the same edition
   in the manifest. Differences require source-backed row-level review, not
   forced equality or count adjustment. Verify every pre-existing row/ID/
   field fingerprint and approved independent correction delta separately.
3. Review representative beginning/middle/end finding pages for **each of the
   five editions**, across counties and both institutions, plus all parser
   refusal/exception/boundary pages. Record institution, FY, finding reference,
   exact PDF/printed page, raw excerpt and units/zero/withheld distinctions.
   Follow rendered page → API → audit → extraction → exact official PDF.
   A link alone or `unverified` provenance response is not successful evidence.
4. Require migration/parity, actual seed and **full validation** success,
   including #347 and national/legacy refusals reviewed by their owners.
   Configure one server-only `REVALIDATE_SECRET` consistently in Actions,
   Render and Vercel via the separately approved owner process; record resulting
   deployed SHAs without secret values. Old missing-secret receipts are
   inherited, not fresh configuration inventory.
5. The existing revalidate job must show API **HTTP 200 + `invalidated: true`**
   before the frontend call, then exact acknowledgement of
   [paths.json](../../../frontend/lib/revalidation/paths.json) with
   `rejected: []`, including `/audits` and `/counties/[id]`. No signed mutation
   is sent as a readiness probe. A failed validation/refresh stays failed.
6. Before catch-up, select a newly expected source/page-backed finding from a
   deferred edition and capture its API absence/rendered before-state. After
   successful seed/validation/refresh, record the **first** rendered `/audits`
   or actual county page read, matching API value/ID/reference/institution/FY,
   citation and source text, response time and refresh/job IDs. Also review
   both institutional scopes and each affected FY, and #379's three texts when
   that separate correction is authorized. Keep backend/frontend SHAs fixed
   across this data transition: a deploy, restart or TTL expiry cannot substitute
   for the requested no-deploy refresh proof.

Local parser/scheduling acceptance cannot close #234/#231/#378. Keep #379 open
until its corrected public texts are separately observed. Session 4 supplies
the owner/access/budget/correction/freshness decisions; this packet supplies
the exact county source scope and acceptance controls.

## Executed local verification

Focused existing tests executed the audits caller, resumption, registration,
per-volume commits, timeout retry, zero-start cutoff, covered single-report
exclusion, malformed/empty/partial/refused outcomes, wrong attribution and
coverage negative/positive controls: **116 passed, 0 skipped, 2 warnings**,
exit 0. No application behavior changed, so this is verification of the current
mechanism, not a new regression fix. The safe external launcher read back
synthetic loopback application settings without connecting, retained SQLite
fixtures, disabled dotenv/env-file loading, Redis/seeder/warmup/lifespan and
blocked TCP/HTTP. Fixture parser/network calls and 100s costs are synthetic;
no production migration/driver/performance parity is claimed.

External scripts, raw HTML, source front-matter, captured issue and logs are in
`ROUND11_SESSION_3_EVIDENCE_2026-10-01/` beside the Round 11 briefs. Initial
helper imports failed because `pypdf`/`fitz` were unavailable; a bytearray HTML
input and raw relative-link assumption also failed during evidence assembly.
The final helper uses existing `pdfplumber`, byte HTML and URL/fragment
normalization, with no installation or shared dependency change. These were
helper setup errors; no application defect is asserted from them.
No full eight-PDF replay, live source ingest or live database query was run.

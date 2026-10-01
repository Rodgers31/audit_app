# Economic source acceptance and web debt status — 30 September 2026

This is a review-only source correction proposal and a local status repair. No
production update, deletion, seed, dispatch, secret edit, baseline change, push
or PR was performed. Repository Actions remain disabled. Issue bodies and
comments for #389, #380 and #293 were read on this date; #390's completed
population/economic ownership fixes are preserved.

## Web debt status repair (#389)

The real background loop previously credited `_seed_debt_live()`'s normal
no-op return as a successful debt refresh. Boot did the same. Seven regression
cases failed against base `cfde074`: idle periodic debt success was 1 instead
of 0; boot success was 3 instead of 2; both direct debt calls failed to refuse;
the successful and failed county controls both gained a spurious debt success;
the actual public endpoint still promised the next debt refresh.

The repair removes debt from boot and periodic schedules, retains a rejecting
legacy method, and identifies dedicated `national_debt` and `debt_timeline`
domains. Idle and failed periodic checks no longer advance `last_full_refresh`.
The web status adds `external_job_owner.job_health=not_checked_here`; this
field does not query or certify the dedicated runner. Only the seeder note
in `main.py` changes. County reference success, exceptions, retry cadence,
consecutive-failure accounting and weekly scheduling remain covered.

All writers/triggers of web debt status were searched: boot calls
`seed_all_domains`, start calls `_initial_seed_and_loop`, the hourly loop calls
`_check_and_refresh`, and direct `_seed_domain("debt")` reaches the rejecting
legacy method. None dispatches debt or credits it after this change. Historical
in-memory debt timestamps injected manually into `last_refresh` remain visible
unchanged but cannot acquire a new next-refresh schedule. Fresh workers have
no such timestamp; rollout must restart workers, not carry their old state.

## Publisher evidence (#380/#293)

The downloaded KNBS PDFs were parsed and PDF page 2 was rendered and visually
read. Dates below describe calendar months, not fiscal years or annual averages.

| Observation | Current public row | KNBS national Overall CPI | Exact source |
|---|---|---|---|
| January 2025 | IDs 86 (`CPI`) and 67 (`cpi`): 143.08 | 142.68 | [January release](https://www.knbs.or.ke/wp-content/uploads/2025/01/Kenya-Consumer-Price-Indices-and-Inflation-Rates-January-2025.pdf), PDF p.2, Table 1 |
| December 2024 | ID 87 (`CPI`): 142.47 | 141.66 | [December release](https://www.knbs.or.ke/wp-content/uploads/2024/12/Kenya-Consumer-Price-Indices-and-Inflation-Rates-December-2024.pdf), PDF p.2, Table 1; also January release p.2 |

Both tables explicitly use **February 2019 = 100**. These are index levels,
not the inflation-rate column. Their values and series basis do not support
the three currently published observations. No alternative official measure
supporting 143.08 or 142.47 was established by this bounded review.

January PDF SHA-256:
`ca9654579a2a0b8d14301de005cea70f1db2943c8d40cb111be3b8b1e0ccd44d`.
December PDF SHA-256:
`75e6f741704874180edd8378ec6219c5920f15082496e6bf47aa00e0f7570614`.
MD5 values and exact full row/source before-images are in
[`cpi-correction-proposal.json`](cpi-correction-proposal.json).

Bounded current live queries explicitly executed `BEGIN READ ONLY`, verified
`transaction_read_only=on`, set `statement_timeout='8s'`, limited every result,
and ended in `ROLLBACK`. Credentials were explicitly read for these queries
from existing local discrete DB configuration; no credentials/config values
were printed and no tests loaded that configuration. The Python environment
has psycopg2; psycopg v3 is unavailable.

Source 1823 is `CBK Public Debt Report & KNBS Economic Survey 2025`, publisher
`Central Bank of Kenya / National Treasury`, type `LOAN`, status `FAILED`, with
null URL, file, MD5 and verification date. It has no extraction rows. IDs 86/87
have bootstrap metadata and no page/hash/extraction. This is a misattributed,
untraceable CPI citation, not a KNBS monthly source receipt.

Lowercase row 67 cites source 1715, `Economic Indicators Time Series`, a generic
KNBS landing-page URL with no file/hash. Its metadata explicitly states the
wrong February 2009 basis. All three rows have `publishable=false` but are
currently returned by `/api/v1/economic/indicators`; that reader does not honor
this flag. The actual `/api/v1/provenance/verify/economic_indicators?year=2025`
returns HTTP 400 `Unknown table`, so there is no completed verifier chain for
these observations. Merely adding a quarantine flag would not withhold them.

The proposal preserves each exact case/type/date/entity/ID. It changes index
values and units coherently, allocates or reuses exact PDF source/extraction
records, records Table 1/page/hash/basis, and replaces stale provenance. It
leaves shared documents 1715/1823 intact. It also proposes a prerequisite
fixture correction, because the dedicated supplement still supplies 143.08
and February 2009. **Nothing in the proposal has been applied**, including the
fixture edit. Fresh preflight, review, disposable PostgreSQL rehearsal and
release approval are required. Rollback is full before-image restoration
conditioned on matching the actual approved after-image; restoration would
reintroduce unsupported observations and requires withholding/review.

## Dedicated runner and acceptance boundary

`seed.yml:467–544` runs Python 3.12 with backend requirements, `cd backend` and
`python -m seeding.cli`; it does not run the web's obsolete root extractor.
The registered economic domain calls its backend fetcher/parser/writer and
stores an `ingestion_jobs` row. Its parser lowercases `CPI` to `cpi`.
World Bank `cpi_index` is an annual **2010 = 100** measure. These three stored
identities must remain separate; this review authorizes no merge/rescaling.

The current live ledger's latest relevant entries are September 29:

| Job | Domain | Recorded result | Source detail |
|---|---|---|---|
| 3180 | economic_indicators | COMPLETED, non-dry, 322 processed, 0 created/updated, errors [], 0 removals | 73 World Bank observations; 248 CBK months, newest 2026-08, 12 withheld |
| 3185 | national_debt | COMPLETED, non-dry, 47 processed/updated, errors [] | CBK bulletin rows=4, WB IDS rows=2 |
| 3179 | debt_timeline | COMPLETED, non-dry, 13 processed/updated, errors [] | CBK Statistical Bulletin 4.1.3, 4 years |

These are recorded past-run outcomes, not post-#390 source/deployed acceptance.
Historical Actions run [36512696196](https://github.com/Rodgers31/audit_app/actions/runs/36512696196)
corroborates those job IDs on head `1d5fa9f`. The newer September 30 run
36660207026 is failed; its seed job is **skipped**, on older `c76ad748`.
No successful dedicated execution of current `cfde074` was observed. Actions
permissions were read as `enabled=false`; they were not changed.

The actual Render-context Docker image was built and run with `--network none`,
synthetic SQLite and an injected HTTP transport. The real economic CLI,
fetcher, parser, writer and ledger ran. A synthetic live pull recorded
`completed/live` while also writing the unsupported fixture `cpi=143.08`.
Synthetic source failure recorded `completed_with_errors/fixture`; the CLI
still returned 0, so exit status alone is not a job-health receipt. The World
Bank zero-value control remained zero with `index_2010_100` and coherent World
Bank provenance. The image imports/refuses obsolete economic/debt web paths
without a root `extractors` package. This is packaging/behavior evidence,
not evidence that the synthetic publisher responses are real observations.

## Validation and closure recommendations

Tests used the existing `.venv313` Python with `PYTHON_DOTENV_DISABLED=1`, a
unique synthetic SQLite `DATABASE_URL`, `REDIS_URL=''`, `TESTING=true`,
`AUTO_SEEDER_ENABLED=false`, `AUTO_WARMUP_ENABLED=false`, `PYTHONPATH=backend`.
The new regressions were **7 failed before / 7 passed after**. Focused web,
reference/economic ownership, endpoints, inflation and provenance suite:
**92 passed, 4 warnings**. Independent adversarial probes executed the real
loop/writer/endpoint with failed and successful controls. Compileall and
`git diff --check` passed. Ruff is unavailable and was not installed.

- **#389:** code acceptance is locally supported. Keep open until deployment
  shows no debt boot/periodic success or next schedule and dedicated health
  remains explicitly unqueried at the public status endpoint.
- **#380:** keep open. CPI source discrepancy is now confirmed; exact stored
  and fixture correction is proposed only. Require reviewed correction,
  coherent source/API evidence, and no competing-writer regression after
  approved release.
- **#293:** keep open for dedicated current-version job/source acceptance.
  Retired web packaging passes the image check; the root extractor must not
  be restored. A completed historical job is insufficient.
- **#347/#378:** historical 15→11 loss still lacks the original IDs/source
  metadata/authorization. The requested September 26 snapshot or prior backup
  remains necessary. No original receipt was recovered in this bounded work;
  no restoration was fabricated from tuple values. Do not lower the baseline,
  rerun nightly or start catch-up while Actions is paused.

Rollout of this code needs worker restart and bounded public status checks;
it requires no data migration. Reverting the code restores false debt success
and unconditional full-refresh timestamps, so prefer a forward correction
for consumer incompatibilities. The source proposal has its own independent
release/rollback requirements and does not license a production write.

## Deduplicated adjacent candidate

Both independent probes reproduced an existing false county success: with no
KEN country row, the actual county writer returns without creating entities,
then the loop credits success and postpones retry seven days. Base `cfde074`
does the same. With a KEN row the writer creates all 47 counties; with a DB
exception it correctly counts failure. Proposed narrow follow-up: raise on
missing required country in both reference writers and test the actual boot
and loop paths. No county behavior was changed in this debt patch.

Open **and closed** issue searches for `"Kenya country not found"` and
`"missing country"` returned no matches; broader false-success search found
#389/#137 and unrelated items. Current #137 body/comments were inspected and
do not describe this missing-country control. The coordinator should verify
and file the candidate. The bad fixture/lowercase row belongs to existing
#380/#293 source acceptance; no duplicate CPI issue is recommended.

Full command outputs, source PDFs/page images, read-only receipts, Docker
probe, and adversarial probes are in the external Session 5 receipt directory
referenced by the coordinator handoff; no publisher PDFs or full Actions
logs are committed here.

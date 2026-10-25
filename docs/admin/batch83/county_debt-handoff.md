# B83 county borrowing handoff

Frozen base: `7c7b309158480e61206a453e7d844fcf5075b3b9`. Branch: `codex/b83-county-debt`. This is an author candidate for a draft PR. It does not establish production ingestion or complete county liability coverage.

## Implemented contract

`county_borrowing` is an explicit opt-in native seeding domain. `SEED_COUNTY_BORROWING_INGESTION_ENABLED` defaults to `false` and accepts literal `true`/`false`. The built-in fifteen-domain cohort and default daily/weekly selections remain unchanged. The source plan can select the domain manually or include it in a future explicitly enabled weekly plan; this PR changes no workflow or live setting.

The producer uses the existing durable claim, nonce and continuous PostgreSQL lock owner, re-proves ownership after acquisition and persistence, and calls `record_county_debt_observation` for reviewed actual contract mappings. The shared non-writing validator and positive-key guard run before preview returns and in the existing direct writer. Pending bills, inherited obligations, proposals, guarantees and national creditor aggregates are refused as direct county stock mappings.

Transport has one attempt, no redirects/proxy inheritance, a 60-second elapsed check on each raw response fragment and 15-second I/O timeouts under the native domain deadline and 40MiB per-response ceiling, further limited by the edition's exact size. The inventory is nonempty, at most eight editions and at most 64MiB in aggregate. Actual PDF SHA256, MD5, page count, visible-page text hashes and extraction/parser lineage must match the reviewed edition. Reissues or stale/wrong editions refuse. These are dated historical source checks, not discovery of the newest publisher edition.

SourceDocument and Extraction retain identity, scoped coverage and locators. The configured receipt store retains and reads back actual bytes. Financial/source rows share the caller's transaction/savepoints. Deferred constraints fire before independent Core readback of complete source/extraction identities, the complete source-bound observation set, and every intended instrument/stock field. Replays do not duplicate observations. Caught refusals preserve unrelated caller work. An aborted DB transaction can leave an immutable content-addressed receipt object; rollback does not delete evidence. Default local receipt storage does not establish provider durability across deployments.

## Official evidence and limits

| Checked edition | Binding and locator | Supported conclusion |
| --- | --- | --- |
| [Treasury Annual Public Debt Management Report FY2024/25](https://newsite.treasury.go.ke/sites/default/files/Annual-Public-Debt-Report-2024-2025.pdf#page=53) | 1,611,766 bytes; SHA256 `871bf6b38ed579e9abc8e6f4fe0cd21ad979116118bde109329dcb35b88e8d48`; PDF/printed p53, Table16:7.1-2; reporting period end 30 June 2025 | No county borrower appears in this guaranteed-stock register. This limited register does not establish no other county borrowing or liabilities. |
| [OAG county executives FY2023/24](https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf#page=499) | 34,055,119 bytes; SHA256 `bf36d9e65b7403f9ce66eaf32890834f546ca3674c331a2d5f734f9e68c59bcd`; PDF pp499–500 / printed pp485–486, Kisii finding980; report year ends 30 June 2024 | Obtained borrowing is described, including an assembly component; a bank name, explicit contract reference, issue date and dated outstanding stock are not supplied. Regularity was not confirmed. Retain withheld coverage, not a loan balance. |
| [Laikipia DMSP2026](https://laikipia.go.ke/wp-content/uploads/2026/06/DMSP-2026.pdf) | 5,654,869 bytes; SHA256 `19c51468a7c19f618b84e5b3283d90d1e120cb608a76807ba90fe1021f0fb831`; 36 image-only pages | Research candidate only. No qualified stock extraction or zero is admitted. A bond proposal/guarantee would not establish issuance or stock. |

The two implemented official editions emit **zero instruments**. Their local PostgreSQL roundtrip creates two source/extraction accounts and leaves borrowing totals NULL. There is no genuine official positive balance qualification in this delivery. Synthetic contracts exercise the positive, zero, correction, competing-account and latest-null paths; they are not Kenyan financial evidence. No 47-site crawl or complete liability census was performed. The supported checked scope is the Treasury register plus the identified Kisii audit finding; all other county borrowing sources remain unintegrated.

## Coverage and UI

The bounded coverage helper makes two queries for the entire requested cohort (maximum47 counties; maximum8 source accounts), validates complete source/extraction identity and returns dated scope/citations. It distinguishes not integrated, not reported in checked scope, and withheld/conflicting evidence. Stock summaries separately distinguish selected eligible stock and a genuinely dated explicit zero. Neither source absence nor missing stock can manufacture zero or restore an older nonzero balance.

The county overview and home panel explain the selected scope and separate pending bills. Malformed metadata cannot crash the note, conflicting absence metadata takes precedence, and invalid calendar dates cannot certify dated zero. The home formatter now preserves measured zero. EN, SW and plain-English messages no longer claim most counties have no debt or that nobody publishes it.

**Reserved integration dependency:** `backend/main.py` belongs to the aging lane. This PR deliberately does not edit it. Existing endpoints receive the generic summary status; source-specific checked-scope citations require the coordinator's batched helper projection. Exact proposed call sites and workflow input/environment wiring are in the external lane `DEPENDENCIES.md`. Source-specific API/UI acceptance remains incomplete until those hunks are integrated and verified. The producer, helper and existing public stock-reader/API contracts were exercised independently.

## Verification and review

- Observed frozen-base producer gap: two expected behavioral failures and one unchanged-daily-plan control pass. The source note also failed before its wording repair. Additional confirmed review findings have retained failing-before/passing-after receipts.
- Final focused backend regression:110 passes. This includes77 new source/producer/ownership/PostgreSQL/API/adversarial cases and33 existing county publication cases. Eight MockTransport controls execute the actual transport success/refusal/closure, fragmented-stream deadline and encoded-response refusal paths without more official downloads. The targeted legacy financial absence cohort passes82 cases using the existing canonical `bind_package` ownership mechanism. An earlier mixed-cohort import failure is retained as a harness diagnostic, not counted as a product failure or pass.
- Frontend:57 passes/one existing skip across six affected suites; TypeScript passes. Actual Chrome/Next/FastAPI fixtures show missing coverage on county/home and a synthetic dated zero on the county page. The home zero repair has an observed-red/green component regression and a Chrome accessibility readback showing KES0; the saved map-selection screenshot caught an entry transition and is not final visual acceptance. Browser CORS/fixture-ID setup diagnostics remain retained; the browser used the fixture's actual Mombasa link afterward.
- Independent Spec review:69 changed backend cases plus final eight-transport/three-PostgreSQL delta controls and original/extended source identity controls pass. Independent Standards review:77 changed cases and35 independent attacks pass. Counts overlap and are not additive. These are local executable reviews, not GitHub approving reviews or hosted checks.
- The owned PostgreSQL17 fixture was migrated to actual head `a756b20a0001`, using the cached image digest `2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`, loopback port55683,512MiB/0.5CPU. Python3.13 uses an isolated overlay satisfying the accepted base's requirements. Frontend dependencies have the same lock hash as this base and are consumed read-only.

Receipts, source PDFs, review reports, screenshots, runtime versions and cleanup readback remain outside Git under the lane's `BATCH_83_BUILD/county_debt` evidence directory. Full PDFs are not committed. Failed receipts are preserved. Product file hashes bind the final candidate and committed source; no live acceptance is inferred from fixture success.

## Adoption and rollback

No migration is added. A future authorized rollout requires the existing county instrument schema, Kenya/Kisii identities, trusted receipt-storage custody, coordinator API projection, source-plan workflow wiring, reviewed admission and production/operator acceptance. Missing/partial schemas refuse ingestion. Enabling the flag alone does not qualify a positive financial balance.

Rollback is the default-off flag plus the prior reader/UI code if needed. Keep evidence and dated observations; do not delete/rewrite them as a rollback shortcut. Same-key corrections remain explicit in the existing writer and increment revision; other source accounts remain competing, and changed PDF editions require fresh review.

Tonight's workflow, admitted write SHA, production records, publishing/uploads/approval/scheduling/provider settings and hosted Actions remain untouched. No merge, readiness change or deployment is part of this draft author delivery. Parent operational/financial acceptance remains with the coordinator.

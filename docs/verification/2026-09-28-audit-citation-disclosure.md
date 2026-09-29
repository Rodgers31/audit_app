# Audit citation and disclosure consolidation

Base main: `1d5fa9f664b16d40edfb1171aa9f8782b5ec2a71`. Consolidates Session 2 `97bccc6`, Session 1 `6202657` and Session 4 `61e8496`, plus a small source-unavailable cue and independent source-link test setup correction. Addresses #365, #366, #367 and the frontend disclosure subtask in #321. No migration, production seed or data mutation.

## Integrated behavior

County audit lists bind to the exact Kenyan county entity; known counties without matching entities return empty rather than other institutions' findings. Federal citations batch-load their actual linked documents and supply safe page destinations. The homepage consumes that destination without constructing malformed PDF fragments.

Audit publication validates supported numeric/range/textual locators and safe HTTP(S) URLs, with distinct withholding reasons. Canonical Roman/Annex references remain textual; malformed locators are not turned into invented page numbers. Fiscal/budget descriptive PDF references retain explicit compatibility. County accountability uses a truthful generic withholding message; the dashboard renders invalid-URL and unknown reasons in all three language modes.

Pending-bill displays distinguish complete totals, reported partial sums, qualified coverage, missing values and sourced zero. Dates and source links remain separate by national/county side; rankings disclose incomplete coverage. An invalid/missing source URL retains the title and explicitly says Source link unavailable.

## Executed coordinator checks

- 323 backend tests across citation eligibility, locator gates, county citations/source URLs/scope/identity/accountability, fiscal and county publication, pending completeness, federal findings, and citation conflicts. The actual publication SQL ran on both SQLite and PostgreSQL 16 in isolated schemas.
- 37 additional missing-funds, public-endpoint-withholding and query-payload tests passed, checking shared gate callers.
- 70 frontend tests passed across AuditReportsSection, DebtPagePendingBills disclosure and DebtPageClaims. The source-link regression also passes alone after fixing its preexisting dependency on a previous test's mock. The new unavailable-source cue was observed failing before correction, then passing.
- TypeScript, targeted ESLint with zero warnings, and diff checks passed. Production Next build completed.
- Playwright: ten complete/partial/qualified/missing/explicit-zero scenarios passed at desktop 1366px and mobile 360px. Used the real repository Python fixture server with isolated SQLite (not the worker's substitute stub). Pending-bills scenarios themselves are intercepted synthetic HTTP payloads, so this is rendering acceptance, not production-data acceptance.
- Independent verification executed endpoint attribution/source controls and locator/URL parity probes on SQLite and PostgreSQL with no mismatch. Separate backend pending-bill contract tests passed 65/65; three independent frontend probes using the backend's ranking row shape passed for partial, qualified and complete coverage.
- The other PR's ingestion suite passed 290 tests against integration tree `0f6fa11`, which contains both PRs' behavior before the final copy/test-setup-only correction. No application conflict occurred.

Test environment: PYTHON_DOTENV_DISABLED=1, unique SQLite DATABASE_URL, REDIS_URL='', TESTING=true, AUTO_SEEDER_ENABLED=false, AUTO_WARMUP_ENABLED=false. PostgreSQL was disposable, bound to loopback with synthetic test credentials. Browser fixture ran at ports 8125/3125, leaving the user preview alone. No production environment file or database export was used.

## Release acceptance and limits

Before merging/deploying the stricter publication gate, assess currently published production records with a bounded read-only before/after eligibility count and sampled IDs/reasons. URL syntax restrictions and the nine-digit numeric page limit can newly withhold records; current production distribution was not measured. A syntax check is not proof of link liveness, document authenticity or page accuracy. No cleanup/backfill is authorized by these tests.

Deploy backend and frontend together, accounting for the federal payload's one-hour cache and the new source_page_url field. Confirm live affected surfaces after deployment. Keep #321 open for remaining data/source/writer/rollout acceptance. New Swahili messages need the existing #307 language review. Inflation #347 and newer OAG coverage #234 remain unresolved production work.

## Adjacent findings and dispositions

Coordinator independently reproduced and logged #374: malformed stored provenance can crash the entire federal endpoint. #375 separately records accountability's unchanged lookup accepting a foreign namesake; the repaired county audit-list route does not have that defect. Both are synthetic reachable findings; production occurrence is unmeasured.

Unknown county severity currently being ignored is a preexisting contract question rather than a confirmed requirement violation; no speculative issue was filed. Malformed coverage/date payload probes did not match the current backend contract, which emits complete coverage structure and validated dates; they are not claimed as observed production defects. No broad audit or historical cleanup was performed.


## Copilot review corrections

Reviewed both inline findings and the complete review body at head `0d3fde2`; both findings were valid. PR #377's current-head Copilot review had no findings and its CI passed.

- Integer locator parity: the coordinator reproduced integer 1000000000 being accepted while its equivalent string was refused. The central page_number bound now matches the SQL nine-digit policy. Five surface assertions failed before correction; integer/string boundary, boolean/nonpositive and named-locator controls pass afterward. The caller fix covers citation_page, report_page_url and Python publication checks without widening SQL casts.
- Pending-bill snapshot disagreement: rendered regressions failed for unequal partial sums with identical coverage, zero versus missing, and apparently complete but contradictory sums. The page compares validated reported sums, discloses mismatch beside the total and ranking, and avoids a full-ranking claim. Matching zero remains zero. This comparison detects the demonstrated inconsistency; it does not certify that equal aggregates came from an identical snapshot.
- Full CI run36513703410 exposed two fiscal-outturn regressions (5871 other tests passed). A legitimate `Annex 2a p63` fiscal shorthand was rejected by the shared citation tightening. A narrow fiscal-only full-match exception restores it; malformed/zero/reversed/trailing-junk controls still withhold. The current fiscal writer's `Annex Table 2a, PDF p.63` was already supported. No audit gate loosening or source/reconciliation check removal was used to make the tests pass.

Final coordinator checks for these corrections: 288 targeted backend tests passed, including actual SQLite/PostgreSQL gate execution and the two previously failing CI tests; 73 frontend tests passed. TypeScript, targeted ESLint and diff checks passed. Independent direct calls confirmed fiscal shorthand remains invalid for the audit citation policy. Every changed behavior has observed failing-before/passing-after evidence. A fresh full CI run is required on the pushed head; these local checks do not represent its outcome.

No additional unaddressed confirmed issue emerged in this review round. Previously logged #374/#375 remain open. The premerge production impact assessment for #366 is still required; no production data access, mutation, seed, merge or deployment was performed for this review.

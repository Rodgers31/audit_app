# Standards

Reviewed the actual full `git diff bcb5ff99854de595bbe3f7d60cc8796b7ada5a20...HEAD` and four-commit list at `6fcaed18327d4ebdb91b475c016d81ca624deda8`, tree `958d72062130267d0916ad14f9ab7ab6afb0af71`, including the final published corpus. No repository edits were made by this reviewer.

Documented-standard findings: **0**. `frontend/README.md:240–246` requires existing style, TypeScript, responsive design and JSDoc for complex functions. `CountiesPageClient.tsx` keeps structure/styles and documents its typed query helper. Both new browser-test files follow existing Playwright usage. `countiesUrlStateSsr.test.tsx` observes real native history through a pass-through spy, while captured original history handles only external harness inputs; row, SSR and hydration assertions remain and actual URL/no-router assertions are strengthened. `CONTEXT.md` and both ADRs govern data concepts outside these hunks. Tooling-enforced details are excluded.

Fowler judgement-call findings: **0** after considering all twelve required smells. The shared query helper removes duplicated navigation logic, retains meaningful URL/hash responsibilities and introduces no unused abstraction.

Independent execution: six fresh focused browser cases passed with two actual workers, viewport 1280×720, zero retries/skips/flaky/unexpected cases, using the supported portable replay. Actual Node 22.23.3, Next 15.5.27, Playwright 1.58.2 and Chromium 145.0.7632.6 were captured. Thirty actual-report/malformed-input controls also passed. Source, checker and manifest stayed unchanged. After the browser run, the actual committed diff/commit list and all 755 packet files were rechecked: default verification exited 1 for the known full-suite failures; integrity-only exited 0 with `local_recorded_acceptance:false` and 316 passes / 2 unexpected / 11 fixmes. Active source/docs whitespace checks passed; five spaces-only lines in an archived raw transcript remain preserved.

Reviewer wrapper setup/post-processing errors are recorded separately; the completed browser result was consumed without rerunning it.

**Limits:** full behavioral acceptance remains false. #601 is unresolved, and the historical naturally delivered-200 #607 cause remains unmeasured. No hosted or production acceptance is claimed.

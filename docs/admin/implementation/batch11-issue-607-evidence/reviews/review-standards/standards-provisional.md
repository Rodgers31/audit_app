# Standards review — provisional

Reviewed `git diff bcb5ff99854de595bbe3f7d60cc8796b7ada5a20...HEAD` and commit `09fd3c150032e8595678ddf2046948651a260b96` (`fix(counties): publish pagination URLs without server navigation`). Current tree: `f3a254d87655cbba42365684f1c611cae5b1312e`.

Documented-standard findings: **0**. `frontend/README.md:240–246` requires existing style, TypeScript, responsive design and JSDoc for complex functions. `CountiesPageClient.tsx` keeps the component structure/styles, uses a typed `URLSearchParams` helper, and documents why publication is synchronous. Both new browser-test files follow the existing Playwright API and fixture selectors. `CONTEXT.md` and both ADRs govern data-publication concepts outside these navigation hunks. Tooling-enforced formatting/types are excluded from this axis.

Fowler judgement-call findings: **0**. All twelve required baseline smells were considered. `replaceListQuery` has a meaningful responsibility: retain pathname and fragment while replacing only query state. Sharing it between pagination and View All removes duplicated router replacement without introducing an unused abstraction. No changed responsibility is scattered into unrelated modules.

Independent execution: 30 actual-report/schema controls passed, including six focused results, 100 original cases, three controlled red cases, untouched original smart-back source, duplicate/empty case identities, hidden retries/errors, malformed primitive types/counters, nonfinite durations, unsafe paths and duplicate JSON keys. Actual source and checker bytes were unchanged; command/runtime/output receipts are in this review directory.

**Limit:** focused browser execution and final full-diff/packet verification are pending explicit release of the author's resources and publication of the final corpus. This is not an all-clear or hosted/production acceptance.

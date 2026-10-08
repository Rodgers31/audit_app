# PR #514 review follow-up

Review base: `d0e018b3c3fe47604f56ca9590ca70a4c61e597c`.
The complete saved PR body, review threads and pending comments were read before
classifying the findings. Existing approved components and styling are retained.

## Findings and resulting behavior

| Review evidence | Classification | Resolution |
| --- | --- | --- |
| `4220760836`: stricter schedule decoding allegedly breaks old mounted fixtures | Not reproduced; incorrect fixture premise | The cited tests pass their overrides through the shared `post()` helper, which supplies every required publication field. The unchanged baseline passed all 474 frontend tests. Keep the strict decoder and existing fixtures. |
| `4220760934`: schedule inputs retain stale publication values | Confirmed | Synchronize civil time and timezone when publication identity or version changes; clear the old DST choice and warning acknowledgments. Same-version polling and draft edits preserve the user's in-progress input. Mounted tests include accepted publish-now followed by another schedule action. |
| `4220761013`: attention hides current delivery failures | Confirmed symptom; proposed removal of historical attention conflicts with the frozen contract | Display current failed, blocked, reconciling and outcome-unknown targets alongside matching historical receipts. Prefer current results when IDs overlap. A capped history preview cannot hide current failures; older historical results retain the existing inspection notice. |
| `4220761079`: handoff commands embed one machine's Python environment | Confirmed | Use `python` from the existing configured backend environment, with repository-root instructions and no package installation. |
| Body-only note: impossible civil dates can pass the decoder | Confirmed; also affects absolute receipt timestamps | Validate Gregorian dates and clock fields before JavaScript date parsing, for both local civil values and absolute timestamps. Reject normalized impossible dates, year zero, invalid leap days and out-of-range clocks. Preserve valid leap dates, offsets, minute precision and microseconds. |

No backend API, DTO fields, publication authorization rules, migrations or
operational publishing gates change in this follow-up.

## Executed receipts

The initial new mounted/parser regression suite failed **15 tests** against the
unchanged review base, with **5 positive tests passing**. After implementation,
the expanded suite passed **27 tests**. It exercises refreshed publication props,
accepted mutation receipts, same-version edits and polling, draft edits, all four
current and historical attention states, duplicate receipt IDs, full previews,
hostile civil/absolute timestamps and valid date boundaries.

The full frontend suite passed **501 tests in 27 suites**. Whole-frontend
TypeScript and lint for edited components, decoder, tests and responsive harness
passed. Selected backend schedule, history, validation and review tests passed
**103 tests**, with **4 PostgreSQL fixtures skipped** in this SQLite-only run;
the integrator owns the assigned PostgreSQL lane. `git diff --check` passed.

The actual component exports passed **48 mounted tests**. The Playwright harness
checked schedule, history and attention fixtures at **1440, 768, 390 and 320px**:
all **12 combinations** had no horizontal overflow, no unlabelled inputs and no
visible button below the accepted 44px size tolerance. The attention mobile
rendering was visually inspected. External browser requests were blocked; these
are fixture and mounted-interaction receipts, not live provider or authentication
verification. Reproduction commands remain in `SCHEDULE_MANAGEMENT_HANDOFF.md`.

An independent reviewer ran **47 targeted tests** plus **19 separate probes**
outside the changed PR test file. These included hostile dates, duplicate clicks,
successive mutations with fresh identities/versions, refreshed civil inputs,
current attention behind a full history preview, deduplication and the older
history notice. The reviewer reported no defect. The integrator also reviewed
the product source before authorizing this commit.

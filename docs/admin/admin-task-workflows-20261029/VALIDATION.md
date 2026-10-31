# Validation record

31 October correction: the component preview below replaced the product root
layout and omitted public Navigation. It did not establish production shell
composition or header reachability. The resulting production header collision
is reproduced and repaired in the [admin shell release record](../../releases/admin-header-20261031/VALIDATION.md).
Future admin UI releases must also pass the actual-root `npm run test:admin-shell`
gate; component-preview screenshots alone cannot satisfy it.

All project execution used owned capped offline Docker. PostgreSQL tests used the assigned current-head synthetic database; browser inspection used Chrome and a loopback byte bridge. No production run was performed.

The 19 source-selection backend cases pass, including an actual native writer/current committed reader, read-only transaction, no social writes, stale and wrong-job refusal, private auth responses, bounded pagination and operational-error distinction. The optimized Python run is retained in `admin-task-source-selection-final.txt`.

The frontend run on candidate 2 passed 200 suites / 2,716 tests with one existing skip. After the Studio/Privacy review findings, candidate 4 passes **201 suites / 2,726 tests with one existing skip** (`admin-task-full-frontend-candidate4.txt`). Earlier failures and intermediate runs remain retained rather than replaced.

Candidate 4 also passes the production build and its type checks, plus full lint without warnings or errors (`admin-task-production-build-candidate4.txt`, `admin-task-lint-candidate4.txt`). The initial production build compiled and type-checked, then hit a process cap during static generation (`EAGAIN`). A separate network-off container capped at two CPUs, 3 GiB and 512 processes completed successfully. This changes only the owned validation environment. Expected offline public-fetch failures are not live API acceptance.

Chrome inspection covered source/job → preview → held detection, uncertain data-vs-draft outcomes, people entry/detail, worker holds, dark mode and tablet/phone layout. Source page widths 1,728 and 375 and overview width 768 had no document overflow. All six fixture Run Now buttons stayed disabled. Temporary viewport overrides were reset.

## Frozen final candidate

Candidate 4 has 2,224 frontend/backend/dependency files. Manifest SHA256: `1f3892207d90fadb1862cf49185bde5fb5d1329826b2d7b4d1e2fd04ee0f4770` (`admin-task-review-manifest-4.json` in the task evidence directory). Candidate 3 → 4 changes only PrivacyReview, privacy read cancellation and privacy hold regressions; backend source-selection bytes are unchanged.

## Retained failures and repairs

- Detection sent preview-only `reports`: the backend correctly refused the extra field. Explicit detection now builds the exact command shape; financial/report route selection stays distinct.
- A late detection acknowledgement crossed an actor transition: keyed local workspaces retire old results, reasons and errors.
- Prototype-named source domains returned inherited object/function values: registry lookup now requires an own key.
- Accessible names diverged from visible labels: People uses its visible label; the ingestion action name starts with its visible text.
- Studio global cache keys could retain a previous actor: private actor keys, read cancellation and local retirement now cover all Studio tasks and blob completions.
- Privacy retained-plan decisions could enable with a closed workflow or failed refresh: fresh request/policy/capability guards now apply to buttons and handlers.
- The overview calendar failure notice was initially buried in disclosure: it is now prominent and links to Run & recover.

Regression receipts include `admin-task-source-regressions-red.txt`, `admin-task-label-regressions-red.txt`, `admin-task-studio-boundary-red.txt`, `admin-task-privacy-holds-red.txt` and their green follow-ups. No backend permission bypass or production effect is claimed from the UI findings.

## Independent reviews

Standards independently executes 64 UI cases across three external suites and 47 backend cases including the guarded PostgreSQL/API path on candidate 4. All pass. It verifies the 2,224 source hashes and exact staged-source delta; positive current-policy review, stale/missing-policy and failed-refresh holds, actor/late-result retirement, and unknown/error operational surfaces are included. The final scoped report is retained in `admin-task-standards-review/FINAL.md` in the task evidence directory.

Spec independently accepts candidate 4 with 43 independent UI cases, 513 broader UI cases across 28 suites, and 53 backend cases under optimized Python (also 53 normal cases on identical backend bytes). The captured UI command is validated unchanged; the actual PostgreSQL route uses real owned source/job identities to verify drafts-off refusal, a silent baseline and same-key replay with no post/publication. All 2,224 final digests match. Report: `admin-task-spec-review-r4/REPORT.md` in the task evidence directory.

Both reviews report no remaining actionable finding in the executed increment. Their owned PostgreSQL fixtures were stopped and removed; root fixtures and production were untouched. Review findings and failing/green controls are retained above. Neither review is production acceptance or a complete WCAG/security certification.

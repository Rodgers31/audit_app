# Independent reviews and validation records

The committed initial review records concern `d3be02e6ed10830d0722d8696f911714cf7b56af` and the subsequently inspected runtime correction documents. Their source/generator identities and raw outputs are preserved under [reviews](reviews/index.json). Final committed-head rechecks remain separate external records, with their own actual source identity; they are not substituted into these older reports.

## Standards

[Standards](reviews/review-standards/STANDARDS.md) found zero documented breaches or actionable heuristic smells. It executed the archive checker, all 32 tests and three independent malformed controls. Its [runtime addendum](reviews/review-standards/STANDARDS_RUNTIME_ADDENDUM.md) found no additional Standards issue and independently checked the retained executables. A first correction-review harness overcounted `x86-64` occurrences because loader paths repeated the string; the original failure and generator remain preserved, and its corrected check passed.

## Spec

[Spec](reviews/review-spec/SPEC_REVIEW_D3.md) identified one unsupported ARM64 executable label. The author reproduced it, corrected the narrative and added [the correction](RUNTIME_CORRECTION.md) without rewriting the archived annotation. The reviewer independently executed runtime checks and found no remaining handoff defect after correction. It executed 32 tests, 18 hostile package/parser/partition controls, a valid lossless recompression control and both trace inspections. #601's causal reproduction/repair acceptance remains pending, explicitly acknowledged in the handoff.

## Adversarial

[Final adversarial review](reviews/review-adversarial-sealed/REPORT.md) executed 136 controls: the original 70 attacks, 22 expanded attacks, 38 direct archive/original-parser controls and six publisher controls. The first two reviews found 14 and then 18 malformed integrity successes. The author independently reproduced both sets, preserved previous checker/publication versions, and repaired the archive boundaries. All 32 former malformed successes now reject. The unchanged original harness still records a mutated zero-duration expectation mismatch: the frozen byte census rejects the modified publication, while the separate actual parser correctly accepts zero duration. This is recorded, not silently relabeled.

Restoring the first checker in an owned temporary package makes all 14 exact regression subtests fail. Restoring the pre-seal checker makes command/measurement/prerequisite/diagnostic regression controls fail. The current published test module passes all 32 tests with zero skips. These red/green controls concern the archive checker, not the application's scroll defect.

## Author validation and final readbacks

The original full Chromium run remains bound to the author base: 323 inventoried cases, 312 passes, 11 unchanged fixmes, no unexpected/flaky/retried outcomes. The later unchanged Node 22 100-repeat record preserves 99 passes and one pagination prerequisite failure under #607. Production builds completed in all six original cohorts. Frontend lint passed; standalone TypeScript checking passed on stable source at `d3be02e`.

Raw author command receipts and hashes are indexed in [reviews/index.json](reviews/index.json). `types-node22` and `evidence-controls-v3` had child exit 0 but verification exit 1 because documentation/checker bytes changed while their broad source inventories were monitored. Those records remain invalidated and preserved. Stable reruns `types-node22-stable` and `evidence-controls-v4` passed with no source drift.

After publishing the final documentation branch, inspect the separately generated `final-published-controls.json`, `final-published-smart-back.json`, `final-published-smart-back-results.json`, final source readback and cleanup receipt at the external raw root named in the handoff. They bind their actual branch HEAD/tree, source bytes, command, generator and result identities. The final smart-back replay uses the unchanged original seven cases, production configuration, verified Node 22 x64 and zero retries. These output names identify the final verification location; this committed document does not fabricate an outcome before those executions.

Final review rechecks are retained under external `review-standards-final/`, `review-spec-final/` and `review-adversarial-final-head/`. Read their actual committed-source identifiers together with the final replay receipts. A valid artifact does not establish hosted/deployed acceptance. #601 stays open, #607 stays open, and no repair PR or issue closure is represented by this branch.

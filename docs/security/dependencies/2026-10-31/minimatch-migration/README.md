# Legacy matcher migration evidence — 31 October 2026

The [migration report](../../../DEPENDENCY_MATCHER_MIGRATION_2026_10_31.md)
explains the change, preserved lint policy, limits, maintenance and rollback.
The [final author acceptance](author-acceptance.json) binds seven executable
inputs to nine completed canonical-root command receipts, with no source changes
during each command. It records 217 dependency controls, nine runtime controls,
2,904 Jest passes in 215 suites with one existing pending case, fourteen browser
cases and their production build, clean install/tree, TypeScript and no-cache
lint. Exact command outputs are retained as JSON strings under `author/`; output
hashes refer to their decoded UTF-8 contents. The runner and original source
inventory are retained there too. The test runs used staged candidate bytes on
the recorded preceding HEAD; the executable hashes identify the tested change.

The unmodified raw [full audit](npm-full.json) has five low entries, all
propagated from deepmerge's unchanged registry version, whose installed code is
locally repaired. The [production audit](npm-production.json) has zero. The
[lock delta](lock-delta.json) retains the version and production-inventory
comparison. No npm advisory is suppressed.

Independent executable reviews: [Spec report](spec/FINAL_REPORT.md) and
[final document binding](spec/FINAL_DOC_BINDING.json), plus
[Standards report](standards/REPORT.md), [portability review](standards/ROOT_CANONICALIZATION_REVIEW.md)
and [final acceptance binding](standards/FINAL_CANONICAL_ACCEPTANCE_BINDING.json). Those reviews distinguish their own executions from the author's
broader acceptance. Earlier 216-control / helper `068a93d7` records are historical
review stages. Final portability and acceptance addenda bind helper `fbff08a0`
and the 217-control final result; do not use the historical receipts as the final
candidate acceptance. Counts overlap and are not additive coverage totals.

`artifact-sha256.json` inventories the exact published evidence bytes, excluding
itself. Upstream tarballs, original installed fixture trees, caches and temporary
hostile installations remain at the recorded external evidence locations; they
are not added as application dependencies. Curated replay scripts identify their
required research fixtures and official archive provenance. Package manifests
retained solely as research inputs use a `.txt` suffix. Packaging preserves the
reviewers' original reports and receipts, including labelled setup failures and
RED results; neither is counted as passing implementation validation.

No hosted test/review, merge, deployment, production write, source admission,
publishing or worker/financial opt-in was performed for this migration. Python,
Windows, deployed image and native worker qualifications retain the limits of
the original remediation reports.

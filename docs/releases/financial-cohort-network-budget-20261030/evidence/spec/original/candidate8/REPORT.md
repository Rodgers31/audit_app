# PR858 phase-guard Spec review

**Scoped pass on immutable candidate 8. No remaining findings.** The original hard-phase finding was independently reproduced and is repaired. No production, provider, GitHub or worker action was performed by this reviewer.

## Original result and classification

Candidate 7 matches `d0da4996327213049614cd8f09b373bcaa856a23`. Its CLI placed the hard alarm around the common envelope; its integration still enforced the cooperative 600-second financial deadline. This was a valid P2 hard-backup contract gap, not a source-authority or publication bypass.

Real SIGALRM evidence: scale the financial phase to 1 second and cleanup reserve to 3 seconds. The resulting 4-second envelope allowed an inert 1.5-second financial dispatch to finish after 1.500279 seconds with no timeout receipt (desired RED). A 5-second inert dispatch was interrupted after 4.004722 seconds, proving the old envelope alarm was active. Three additional desired PG regressions independently failed for the financial phase, report phase and subsecond shared remaining time. Original XML/logs/results remain in the parent evidence directory; none was rewritten to appear green.

## Final input and executed result

Candidate: `pr858-review-candidate-8`, **5,815 files**, mapping SHA256 `f8d4806e68dfbbe08980baa273264fed1850697f147cdd34a416284429ceb2f5`. Every hash and exact file set verified before/after. Relative to candidate 7, the sole product delta is `_post_commit_generation` in `backend/seeding/cli.py`; query, generation-limits, source qualification, cohort witness and integration bytes are unchanged.

**29 distinct independent cases passed normally and the same 29 passed with Python `-O`; zero failures/errors/skips.** These are 29 cases in two modes, not 58 distinct cases.

- The unchanged pure real-alarm controls and all three unchanged desired PG REDs are now green: a phase cannot borrow the other phase's allowance or cleanup reserve.
- Financial and report alarms are sequential, with no nested SIGALRM contexts. The financial hard cap is `min(phase, bounded envelope)`; the report hard cap is `min(report phase, floor(shared absolute deadline - now))`.
- When less than one whole second remains, the report phase never starts or arms a zero alarm. Its known-zero outcome preserves the exact financial result.
- Actual fresh PG write/readback preserves committed source status, dates, counts, errors and existing metadata. An interrupted financial phase remains unknown; an interrupted report preserves confirmed partial financial work. An already-uncertain financial outcome retains null counters and its exact confirmed prefix. Exhausted global time records known zero work and report-not-started.
- Actual whole-CLI caller tests retain the original run deadline. Malformed/nonfinite/boolean inputs refuse before work; dry/default-OFF boundaries open no factory.

The prior deadline-control test has one declared adaptation: its alarm-list assertion now expects separate financial/report contexts. Its source/receipt assertions are unchanged. The original desired real-alarm/PG test files are byte-identical in the repaired execution.

## Performance carry and limits

The candidate-7 independent 130-ms-per-SQL full-baseline result remains separately source-bound: 46 completed baselines in 186.508 seconds, 1,366 SQL calls, no drafts/refusals, followed by 46 unchanged rows on a fresh retained job. That test supplied a 300-second original global deadline and disabled reports, so its first financial hard alarm is still 290 seconds under this patch. The relevant query/integration/qualification/budget files are byte-identical. No expensive full-cohort replay was repeated for this CLI timer-only delta. The separate worst changed-account 150-ms run remains Standards evidence, not this reviewer's execution.

These are owned offline fixture results, not a production throughput guarantee. Inert dispatch stubs in the short alarm tests perform no generation/provider work; real PostgreSQL handles persisted outcome readback. Existing source qualification and hold behavior were not weakened.

## Provenance and cleanup

All project execution used capped network-off owned Docker and a separate guarded PostgreSQL 17 current-schema fixture. Original desired REDs, final commands/logs/XML/tests, manifests and source receipts are retained adjacent/one directory above. The owned `rollout-spec-phase-pg` container was removed successfully and all mode-600 private credentials were deleted. Parent/other fixtures were untouched. No product files were edited by this reviewer.

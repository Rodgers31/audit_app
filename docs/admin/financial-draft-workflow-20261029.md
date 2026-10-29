# Financial draft workflow binding — 29 October 2026

The existing native financial adapters require a separate literal
`SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED=true` ceiling. Before this repair,
`seed.yml` passed the global/report hook switches but omitted this ceiling.
Setting a repository variable could not reach the runner, so financial admission
and dispatch remained disabled. The workflow now forwards the variable with an
explicit `false` fallback. Empty/unset remains disabled; malformed values are
forwarded unchanged and refused by the existing runtime checks.

This code change does not set any repository variable, change a generation
policy, promote a business row, publish, upload or activate a worker. Existing
source/current-job, figure/retained-byte, report-date, global-hook, draft-policy
and human-review gates remain necessary. Financial admission is prospective in
the native writer, separate from numerical public-page qualification. A normal
successful ingestion or positive update counter does not by itself grant draft
eligibility. Initial source cohorts establish silent baselines; meaningful fact
changes or an explicitly reasoned backfill can produce pending-review drafts.

The regression resolves the actual workflow/job/Seed-planned-domains environment
precedence, then executes the existing dispatch bridge. Its source reader,
consumer and telemetry are controlled test doubles, not evidence of production
source adoption. Existing PostgreSQL financial-change tests separately exercise
producer/reader, baselines, corrections, review drafts and replay.

## Remaining production acceptance under #802

1. Merge/release the reviewed binding and verify actual source/admission parity.
2. Under a separately scoped rollout, admit only qualified current-job figures
   through the native writer. Begin with one supported source; keep publication,
   uploads, automatic approval/scheduling and all workers off.
3. Verify committed source/date/cell/receipt lineage and an actual restricted
   worker financial-kind witness, including missing/changed witness refusal.
4. Verify the existing admin preview, one reasoned human-review backfill and a
   fresh replay with zero duplicate drafts. Restore temporary rollout flags.
5. Admit continuing source-specific draft generation only after that evidence
   is accepted. Report-only KRA catalogue evidence cannot grant monetary claims;
   fixtures and unsupported domains remain ineligible.

These steps are operational gates, not claims this workflow-only PR completed
them. The actual production read-only census, primary-source inspections and
red/green/independent review receipts are in the coordinator's external
BATCH_121_NOTIFICATION_DATA_COVERAGE evidence directory. No financial backfill
or additional hosted refresh was performed during this repair.

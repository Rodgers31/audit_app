# Nightly runtime qualification (#836)

The scheduled run [40619863092](https://github.com/Rodgers31/audit_app/actions/runs/40619863092)
validated its plan, URLs and database connection, then exhausted the shared
1,320-second processing limit during `fiscal_summary`. `national_budget` and
`revenue_by_source` did not start. Those three jobs correctly remained failed;
post-run database validation passing did not mean all sources had refreshed.

The twelve completed handlers took about twenty minutes together. A bounded
read-only sample of successful live jobs showed `fiscal_summary` taking up to
469 seconds, `national_budget` 154 seconds and `revenue_by_source` 123 seconds.
Combining those observations, rounding up and allowing three synthetic seconds
per domain for orchestration gives a conservative replay of 1,988 seconds
(33 minutes 8 seconds). This combines different runs; it is not an actual
complete-run duration or a guarantee about future publisher latency.

The defaults now allow 2,400 seconds (40 minutes) of processing, with a
45-minute execution-step cap and a 50-minute seed-job cap. Individual domains
still have their 600-second alarm, and existing download, retry, rate, ownership
and source-authority rules remain in force. Slow useful work gets more total
time; a hung source still fails. No source is removed to make the run green.
Local explicit `SEED_TOTAL_TIMEOUT_SECONDS=0` retains its existing meaning.

The result check uses the retained pre-seed job-ID floor and selected domains,
without its former 30-minute age filter. Early current-run failures and hollow
results therefore stay visible in longer runs. A missing planned source or
nonterminal job also fails the check; recent healthy jobs cannot stand in for
unobserved work. Previous jobs below the floor remain excluded. This preserves
the existing boundary and is not a new cross-run lineage guarantee.

The workflow's optional `SEED_TOTAL_TIMEOUT_SECONDS` repository variable
overrides its fallback. Recheck its resolved value at release; an old override
would retain the old failure. When increasing it, also increase the step and
job caps to preserve cleanup, setup and result-check time. The current default
profile is qualified for the observed daily scope, not a proof that every
weekly opt-in will finish within it.

`tests/test_nightly_runtime_profile.py` replays the retained timing envelope
through the real scheduled source plan and CLI, with simulated handlers and
clock, and real isolated ownership/job persistence. It verifies complete
admission under the new profile, failure and explicit dropped jobs under the
old profile, and continued 600-second individual-source enforcement. The
fixture records provenance and distinguishes observed durations from its
synthetic orchestration allowance. This test does not qualify HTTP retrieval,
new records, source freshness or draft generation.

Before closing #836, admit the reviewed release and observe one complete live
run: every planned domain must have a terminal job, failures and fixture/stale
fallbacks must be explained, new/updated counts must reconcile to stored data,
and ownership must be released. Keep publishing, uploads and social workers
off. Preserve the failed run's history; a retry does not erase its evidence.

The repository is public and uses the standard `ubuntu-latest` GitHub runner.
[GitHub's billing policy](https://docs.github.com/en/actions/concepts/billing-and-usage)
makes that runner time free. The longer timeout does not buy a runner or change
any plan. Existing database/storage/egress usage still depends on actual work;
measure it after the live run rather than infer zero usage from free compute.

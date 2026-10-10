# Batch 10 IMF actual-only headlines — #595

Author lane: `codex/batch10-imf-actuals`; managed checkout:
`/Users/roger/.codex/worktrees/batch10-imf-actuals/audit_app`.
Pinned base: `f6c31e271297eece52f34102dc40a1e2ed7069a8`, tree
`69ddfad6deb814dd08fdaee2db2d512d73e14c78`. Live issue body/comments matched
the frozen launch snapshot (no comments). Remote main matched the pinned base
at launch. No applicable AGENTS.md/CLAUDE.md or issue-tracker document was found;
the explicitly authorized `gh issue view 595` routing was used.

## Behavior and scope

`_latest_imf_debt_to_gdp` requires `is_projection is False` and a finite,
nonnegative numeric value. Zero remains a reported value. SQL orders years;
the most recent valid actual in the selected vintage wins. The existing newest
**Kenya-wide** vintage selection across indicators is preserved. An older
vintage's actual is never substituted when the chosen vintage has only forecasts
or lacks the debt indicator. No parser/model/projection flag or observed data
changes are included.

The complete production caller inventory (`rg _latest_imf_debt_to_gdp backend
scripts docs --glob '*.py' --glob '!test_*'`) is fiscal summary, national debt,
and sustainability. All three execute the guarded helper. Fiscal summary adds
source/vintage/absence fields and retains `above_anchor=None` plus the reason:
nominal general-government debt is not comparable to the present-value anchor.
National debt retains its approximate, explicitly dated CBK/World Bank fallback;
missing/invalid/nonpositive GDP now withholds the ratio rather than reporting
zero. The computed quotient must also be finite (a positive finite denominator
can still overflow). Sustainability retains its separately labelled CBK timeline fallback and
publishes the declared IMF projection series even with no actual headline.
When debt/fiscal inputs and the IMF table are absent, it preserves the existing
no-data response. Table presence is checked before any failed IMF query can
abort a PostgreSQL transaction; catalog failures still return HTTP 500.
No fallback is presented as a comparable PV ratio. Peer reference-year behavior
is unchanged: only an IMF actual supplies Kenya's override/reference year.
The broader cached reader retains its explicitly flagged forecast contract.

Owned product hunks are limited to these four functions in `backend/main.py`.
New tests: `backend/tests/test_batch10_imf_actuals*.py`. Evidence and handoff:
this file and `docs/admin/implementation/batch10-imf-evidence/`.
Startup/readiness/bootstrap, general imports, writers, registries, seed data,
frontend, workflows, and shared skills were not edited.

## Executed evidence

Portable manifest: [manifest.json](batch10-imf-evidence/manifest.json).
Artifacts are external under
`/Users/roger/.codex/visualizations/2026/10/10/01a123ab-860a-79f2-89a5-9d575b40fabc/batch10-imf-evidence`.
Copy that artifact directory intact to relocate it; `verify_evidence.py`
checks its published manifest and optional final replay against the checkout.

The actual pinned-source helper returned `(69.3, 2028, '2026-10-01T00:00:00')`;
the actual fiscal FastAPI route published 69.3/2028. `red-valid-fixture` ran
43 cases: **29 failed, 14 passed, 0 errors/skips**. `green-original` ran the
same test/input bytes: **43 passed**, no errors/skips. Failures included
projections, nonfinite/negative/bool values, ambiguous flags and real callers.
`green-expanded` adds absence/vintage consistency, invalid GDP and the declared
broader projection controls: **50 passed**, no errors/skips.

The initial selection (`cohort-selection.json`) contained 41 entries for 40
unique files, including 11 duplicate cases: **769 passed, 6 skipped**. Its raw
record is retained. The repaired selection (`cohort-selection-final.json`)
contains 41 unique files and no duplicate cases: **779 passed, 6 skipped,
0 failed/errors**. The six unchanged
`test_county_debt_release_compat_postgres.py` cases require
`COUNTY_RELEASE_TEST_URL` and an owned PostgreSQL predecessor/partial/adopted
schema fixture. They did not execute; this lane used SQLite, not that unrelated
release fixture. Repo-required critical flake8 selection for changed product/test
source returned zero findings. There is no frontend build change in this lane.

Final lane fixtures contain 53 financial/API cases and 18 evidence CLI controls:
**71 passed**. The final fixture replay on the pinned base, using the preserved
earlier verifier, produced **49 failed, 22 passed, 0 errors/skips**. These include
new metadata and evidence requirements; they are not 49 reproductions of the
original financial defect. The Spec review separately proved that the earlier
missing-table HTTP/no-data contract passed on base and failed on the initial
candidate. Author review-repair red runs and all four reproduced findings remain
separate historical records.

The verifier now requires the complete measured checkout inventory and Git
state, hashes for raw/JUnit outputs, and declared JUnit counts that agree with
actual testcase nodes and outcomes. CLI refusal controls execute under ordinary
Python and `-O`; real executed passing output is the positive control. Hashes
establish correspondence with recorded inputs, not authenticity of a publisher.

The first two historical runs are preserved, including malformed fixture
failures (page locator and NOT NULL operands). They are explicitly superseded
for behavioral acceptance by the valid red run; do not aggregate them into the
red/green count. Their pre-format generator bytes were not retained; the
manifest labels this limitation. Every later receipt has its exact generator
hash, full source inventory at start/end, runtime, environment, raw log, JUnit
case inventory and child exit. None is relabelled as final published acceptance.

## Runtime, resources, and limits

Owned venv: adjacent `batch10-imf-runtime`; Python **3.12.14** on macOS arm64.
Exact dependencies: external `packages.txt` and `install.log`. Installation
was into this owned environment/cache only. `pytest_entry.py` disables both
dotenv sources and socket connections before application imports, uses an
explicit file SQLite import URL, inert signing key, test environment, default-off
seeder/warmup/parliament transports, and verifies resolved runtime inputs.
API tests use actual in-process FastAPI routes without lifespan/startup.
New cases own file SQLite per test; other existing cases use their established
inert fixture. No actual IMF/provider request was made.

Loopback 55521 was verified free, but no service was launched. Redis attempts are
intentionally blocked and use the existing uncached path. No PostgreSQL,
Docker container/network/volume, listener, server or background worker was
created. Test subprocesses have a 180-second deadline. Owned test DBs dispose
their connections; reviewer processes must finish before scratch cleanup.
Primary checkout and historical coordinator acceptance remain read-only.

This is local synthetic-fixture behavior evidence, not a production observation,
publisher verification, hosted CI, or deployed acceptance. The five tracked
workflows were read back disabled; dynamic Copilot workflows were present and
left untouched. No paid reviewer was requested.

## Independent review and coordinator action

Separate Standards, Spec, and adversarial execution reviews are required before
draft delivery; final report pointers and final package replay will be recorded
after they execute. Findings must be reproduced by the author before repairs.

Initial Standards review passed with no findings. Spec found one missing-table
regression; adversarial found the infinite fallback ratio and two evidence
acceptance gaps. The author reproduced all four before repair. Initial reports:
external `standards-initial-7e931f/STANDARDS.md`, `spec-review.md`, and
`adversarial-review.md`; their generators and raw records are preserved. Final
committed-source reviews remain pending in this candidate commit.

#589 owns startup/readiness and is the first integration owner. Coordinator must
preview both final heads, integrate #589 first, reconcile this lane onto that
accepted integration, and rerun both real caller and readiness cohorts. No
unpublished sibling commits are included here. #595 remains open. #583 and the
parent/operational tickets retain their separate coordinator acceptance gates.

# Automatic county cohort timeout — offline repair evidence

Scope: #849's automatic post-commit pending-bills generation path. This change does not acquire a report, backfill production, enable generation, publish, deploy or start a worker. The source and financial ingestion result remain separate from generation telemetry.

## Cause and repair

Each native financial record previously performed a complete fresh read-only qualification and then repeated that full read under mutation locks. The 46-county cohort shares a report, but those checks include real database round trips for job chronology, lineage, publisher authority, measure receipts and retained origin. A single 30-second CLI alarm covered financial and report phases, while the integration also imposed a 30-second deadline.

The automatic native financial seam now accepts record/job/domain identities and loads current facts once, **inside** the transaction after taking generation and delivery admission locks. It still takes the native domain/source/record locks and performs the existing current job, publisher, exact-value, qualification and retained-origin checks. The returned typed source must match the requested identity. Cursor, event, draft and audit commit together for each record. No authority cache, skip-verification switch, truncation or retry was added. Manual supplied observations still undergo the full comparison with current source evidence. Worker-authority capture still rechecks current meaning and the digest dependencies independently.

Shared limits give pending-bills financial generation 120 seconds, other phases 30 seconds, and the CLI 10 additional seconds for cohort selection/result receipts. The hard CLI envelope is 130 seconds with reports off or 160 seconds with reports on; report and financial outcomes remain separate. Existing per-transaction statement and lock limits remain capped at five and two seconds, preserving stricter inherited settings. The default nightly plan allows 2,400 seconds within a 2,700-second seed step and 3,000-second job. The largest final generation envelope fits within that step headroom. This checks repository defaults; a repository-variable override needs its own admission review. `SEED_TOTAL_TIMEOUT_SECONDS` was absent at the read-only check on 2026-10-29. No workflow or remote setting was changed.

## Controlled performance evidence

All source HTTP envelopes, tiny PDF bodies, 46 sealed extraction cells, jobs, accounts and databases are owned synthetic fixtures. The real writer, migrated PostgreSQL schema, current source readers, qualification, admission, transaction and automatic CLI post-commit path execute. This is not an actual CoB acquisition, a production network measurement or a production acceptance run.

The fixture injects **20 ms after each actual driver call**, and records the calls instead of inferring performance from source text. Root runs used two CPUs, 2 GiB memory, 256 PIDs and no external network. The PostgreSQL container uses an isolated network namespace; no host port is published.

| Case | Root elapsed | Observed result |
| --- | ---: | --- |
| Original 30-second path | 30.14 s | Partial baseline, unknown execution totals, no posts |
| Single-read seam with original 30-second cap | 30.15 s | 33 county baselines committed, still incomplete; no posts |
| Fresh acquisition, first automatic cohort | 38.35 s | 46 silent baselines, no drafts |
| Retained acquisition bound to a new job, first automatic cohort | 43.64 s | 46 silent baselines, no drafts |
| All 46 values change, retained receipts, optional worker port absent | 48.75 s | 46 drafts awaiting review, no publication |
| All 46 values change, retained receipts and installed worker-authority views | 90.94 s | 46 drafts awaiting review, every revision has a current financial worker witness; no publication |

The final case includes the extra full source revalidation during witness capture; the earlier absent-port case cannot establish that cost. The 120-second phase is based on this executed case, with finite remaining margin. Slower or blocked work still ends in a truthful partial/unknown outcome rather than being relabelled completed.

## Correctness and failure controls

Root PostgreSQL controls cover same-job replay; unchanged retained refresh; one changed county while the other 45 remain unchanged; concurrent replay; a body deadline that rolls back the current record and retains 11 confirmed baselines; silent replay of the remaining 35 records; lost commit acknowledgements for evidence, deadline and database exceptions; and a changed original retained acquisition refusing all 46 records. Each control also checks that no publication or dispatch target was created.

The broader current-schema selection initially passed 93 cases and exposed a test injector still matching the old literal 30-second envelope. The injector now derives the actual shared envelope and again executes a real one-second SIGALRM; its focused rerun passed. The complete selected PostgreSQL/budget run under `python -O` passed **111 cases**, with four long performance cases deliberately excluded because they were executed and recorded separately. The ordinary unit selection passed 133 cases, with two legacy SQLite approval cases failing identically on accepted-base code because their sources lack a valid current worker witness. Those existing failures are retained; production authorization was not weakened to make them green. No full-backend green claim is made.

Independent Spec and Standards reviews accepted the scoped repair. Spec executed 41 independent controls, an accepted-code timeout comparison and its own complete cohort profiles, including installed worker authority. Standards executed 65 independent controls, including actual SIGALRM and restricted-connection witness checks. Both verified the final two test changes and the accepted workflow dependency; each ran 18 focused final checks. Product bytes are identical between their first and final snapshots. Final manifest: `cohort-review-manifest-2.json`, 1,417 files, SHA-256 `a8c5efda04948d650467ab1452d8df0a16655ae30252d445585a45592b9d0b73`. Reports are `cohort-spec-review-r2/REPORT.md` and `cohort-standards-review/FINAL.md` under the evidence root. Local proof does not authorize release.

Spec also reproduced a pre-existing root-only `PYTHONPATH` package-launch failure in the unchanged qualification reader on accepted code. This repair is qualified for the normal backend working-directory/bare-module CLI launch; it does not claim to repair that separate package-launch limitation.

## Reproduction and receipts

Regression fixture: `backend/tests/social/test_automatic_cohort_timeout_postgres.py`. Budget/CLI coupling controls: `backend/tests/social/test_generation_cohort_budget.py`. Current database guard: `test_b83_generation_postgres.pg` requires the explicitly assigned loopback database and Alembic head `a756b20a0001`; prepare an owned database before running. Tests refuse a different destination.

The local evidence root is `/Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign`. Key receipts are `cohort-profile-3.txt`, `cohort-final-accepted-base-red.txt` (the final fixture on accepted backend bytes), `cohort-seam-profile.txt`, `cohort-retained-profile.txt`, `cohort-all-changed-profile.txt`, `cohort-worker-witness-profile.txt`, `cohort-pg-check.txt`, `cohort-timeout-control-green.txt`, `cohort-optimized-check.txt` and `cohort-existing-generation-baseline.txt`. Setup failures and historical failing attempts remain there. No credentials are included in this document.

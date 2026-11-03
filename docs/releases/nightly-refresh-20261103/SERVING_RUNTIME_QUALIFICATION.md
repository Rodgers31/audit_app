# Serving-runtime and PostgreSQL qualification addendum

Prepared 3 November 2026 after the parent release lock cleared. This extends the runtime limit recorded in [INVESTIGATION-v2.md](INVESTIGATION-v2.md), which remains unchanged as the historical packet for `c3800934151373e35c5404dcf5b241b346091cc1`. Current executable source is `e326c6227a2e124da3f43e0f05ff8bbe1981a9c9`; a later documentation-only commit carries this addendum.

## Result and scope

The frozen candidate passes **285 distinct cases per mode**, normal and optimized, on Linux Python **3.12.16** using all **81 exact shipping dependency versions** from the reviewed release image. Both modes have zero failures, errors, skips or unexpected successes and identical testcase inventories. The count is **279 regular cases plus six auxiliary PostgreSQL cases**; independent review selections overlap and are not added to it. The six auxiliary cases use actual **PostgreSQL 17.11**, while the regular suite retains its existing SQLite/inert-source fixtures. This is local qualification of candidate source on serving dependencies, rather than a candidate deployment or a full PostgreSQL suite.

The existing serving image is `sha256:b15108d0760de9cff227be59f25fb60997af1f37c5cdf3c3993b7ab4dbf7c477`, associated with the parent-reviewed `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39` release. Tests run from a fresh candidate copy, with test-only pytest/PyYAML tools; application dependencies resolve from the image's Python 3.12 site-packages. No image build, pull or package install occurred. The suite records optimization levels zero and one; optimized workflow subprocesses inherit `PYTHONOPTIMIZE=1`. The separate earlier gate review retains direct child optimization measurements on its historical Python 3.13 run.

## Failure found and repaired

The first PostgreSQL replay at `c380093` passed 279 of 282 cases and failed three intended-diagnostic assertions. A national-only loader refusal referenced `label`, assigned only by an earlier county path. It produced a NameError instead of the intended source-scope diagnostic. The guard refused the load, but the subsequent rollback assertions were not reached, so that run is **NOT_ACCEPTED** and its optimized mode was not run.

Commit `e326c62` identifies the document and expected/observed processed counts directly. The acceptance condition is unchanged. Three committed national-only regressions reproduce red before the fix, pass afterward, preserve rows after an attempted write, and pass both independent normal/optimized reviews. The final fresh runtime replay includes these cases and passes all six actual PostgreSQL cases in both modes.

Each PostgreSQL case starts with three retained extractions and three audit rows and records an actual server/database/schema witness. Controls exercise current-source/idempotent acceptance twice, wrong parser inventory, stale source stamp, and processed counts `0`, `2` and `True`. The three loader controls perform an actual SQL mutation, observe the intended refusal, and then compare the nonempty extraction/audit snapshots unchanged after rollback. All six schemas per mode are distinct and teardown leaves zero owned schemas.

## Evidence and resources

Evidence root: `/Users/roger/.codex/visualizations/2026/11/03/01a1a1aa-4937-7241-97b9-9bc3b183628c/nightly-audit-refresh/runtime-postgres-20261103`. `PREPARED-v2.json` binds 1,541 tracked candidate inputs plus the external six-case fixture, 513 test-tool files, dependency inventory and parent release marker. `RUNTIME-v4.json`, `normal-v4.log`, `optimized-v4.log` and each mode's `runtime.json`, `execution.json`, `result.xml` and `pg-contexts.jsonl` bind the executed source and outcomes. Sources and helper bytes remain unchanged. Two independent host-only evidence reviews reconcile the retained records and exercise malformed-receipt refusal in normal and optimized Python; their exact receipts are linked by `FINAL-RUNTIME-v2.json`.

The earlier lowercase Docker-error preflight failure and failed v2 run remain retained. Unexecuted v3 had stale mount paths; versioned v4 corrected them before execution, without rewriting its producer or preparation record. Original native Python 3.13 results remain historical at their original source. These are new measurements after a source repair and stronger PostgreSQL instrumentation; earlier failures have not been converted into passes. Pre-publication controls exposed Boolean/numeric and duplicate-review gaps in the report tools; versioned replacements refuse them. No report was published by those failed control versions.

Docker readbacks confirm a combined ceiling of one CPU and 1 GiB: Python 0.75 CPU/768 MiB and PostgreSQL 0.25 CPU/256 MiB. The owned namespace has no external network or published host ports. All three owned containers are confirmed absent, fixture schemas are removed, and runtime controls remain off.

## Remaining acceptance

The independent official-transport owner still owns Treasury recovery with normal TLS verification. The exact document 2392 reconciliation still requires independent source/content and PDF/OCR completeness review; its 335 retirements, two revisions and 1,389 additions remain unapproved. The parent owns any later reviewed merge/deployment/admission change and ordinary full scheduled acceptance, including source completion and cache/page refresh. Issues #868 and #888 remain open pending their acceptance criteria.

This lane performed no live source acquisition or seeding, production database/provider action, hosted rerun, merge, deployment, paid review, upload, worker activation, financial generation or source admission. The serving-dependency and six-case local PostgreSQL limit is now qualified; operational acceptance remains held.

Report producer SHA-256: `463ae09c4dfc068d77865eb79489ba927c99fca8ab70b91499235d7f48767fb8`.

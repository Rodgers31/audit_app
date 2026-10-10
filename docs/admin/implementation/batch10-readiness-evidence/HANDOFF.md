# Batch 10 #589 author handoff

Issue: https://github.com/Rodgers31/audit_app/issues/589. Parent #545 remains open; #583 remains the production gate. Base commit `f6c31e271297eece52f34102dc40a1e2ed7069a8`, tree `69ddfad6deb814dd08fdaee2db2d512d73e14c78`. Branch `codex/batch10-startup-readiness`. The author worktree is `/Users/roger/.codex/worktrees/batch10-startup-readiness/audit_app`; the primary checkout was read-only.

## Result

Actual startup now proves all 47 supported Kenyan county identities, with nonempty slugs and no duplicate official identity, using a fresh session after bootstrap returns. Missing, wrong-country, unknown, duplicate, malformed or failed reference checks stay HTTP503 with a static reason and a next-normal-start retry instruction. Readiness resets on every lifespan/startup and shutdown. Pool prewarming and the reference probe run outside the HTTP event loop; a real blocked SELECT1 barrier proves liveness can answer meanwhile. Reference readiness makes no financial coverage claim.

A real inert audits seeding CLI acquires its shared claim and reaches RUNNING, then waits at an input barrier. During that barrier, actual web startup leaves persistent counties/jobs/claims unchanged: an empty/partial database stays503; supported references stay200. Completing the actual writer releases its claim, and the next normal startup initializes references and becomes200. This lane does not introduce an in-process retry loop. Repair malformed reference identities before restart when needed.

Only bootstrap.py, main.py lifecycle/health functions, two new test modules, their unique fixture package and this evidence directory changed. No general import reordering or whole-main formatting. No sibling #595 code was imported. No models, migrations, domain exclusion, provider adapters, workflow files or production state were edited. Default-off automation flags remain off.

## Inherited boundary

Independent real interrupted audits controls found the existing age-based scheduling policy ignores the retained non-budget writer after60 minutes. Both pinned and candidate bootstrap exhibit this; no claims or RUNNING observations were modified to simulate completion. Author separately reproduced it and refreshed all297 open/closed issues plus relevant PR bodies. Follow-up #603 (https://github.com/Rodgers31/audit_app/issues/603) tracks durable non-budget bootstrap exclusion. This PR preserves the existing scheduling probe and introduces no expiry, reclamation or claim release. Do not interpret this readiness repair as every-writer ownership acceptance or production activation.

## Evidence and review

The external evidence root is `/Users/roger/.codex/visualizations/2026/10/10/01a123ab-83d1-77f1-86c1-cead165c4704/batch10-readiness-owned`. MANIFEST.json records original evidence hashes, classifications and source/generator identities; raw originals remain there. The archive is portable and contains receipts, raw outputs and historical generator bytes. Final acceptance is an external source-bound replay after the final documentation commit: HEAD/tree, complete tracked and untracked nonignored source bytes, command, interpreter, environment, child exit, timeout, disk-readback and raw-log SHA are recorded independently. verify_package.py rejects receipt tampering and changed source under normal and optimized Python.

Published fixture replay against unchanged pinned product source: 15 intended assertion failures, 1 pass, 1 deselected. cancel_check is the one deselection because the baseline lacks the new reference-check helper; its candidate cancellation path is exercised. This red includes actual false readiness, stale lifespan readiness and blocked prewarm liveness. Prewarm, six receipt-verifier type/identity cases and ten missing-metadata cases also have separate preserved red controls. A failure containing a diagnostic is insufficient: the current recorder requires the intended pytest assertion failure inventory and refuses setup/runtime errors.

The first broad baseline included two Postgres setup races (Unix-socket readiness saw the temporary initialization server) alongside ten behavior failures. Its initial recorder incorrectly accepted a diagnostic substring. Keep that original as historical mixed evidence, never acceptance. The corrected fixture waits for TCP readiness. Missing command paths, SQLAlchemy2.0.23 on Python3.13 import incompatibility, and a reviewer command-path failure are setup failures. None count as behavioral reds or passing checks.

Current supported runtime: owned Python3.13.9 / SQLAlchemy2.0.54. Minimum dependency replay: owned Python3.12.14 / SQLAlchemy2.0.23. Disposable Linux Python3.12.14 replays current/minimum SQLAlchemy lifecycle/session controls. Linux replay excludes host Docker-backed nonbudget writer cases; those execute against real PostgreSQL in both macOS runtimes. SQLite controls are used for lifespan/cancellation barriers and transaction regression only. This is local acceptance, not hosted workflow, production or combined sibling acceptance.

## Resources and next action

Reserved Postgres port55520 is verified free before use, with any ephemeral replacement recorded. Every test owns a unique schema. PostgreSQL image digest is pinned; exact containers, volumes, networks and ports are checked after cleanup. Linux uses a pinned image ID, a read-only source mount and owned runtime/output mounts. API18010 was unused. All live providers are blocked by a fixture loaded before imports; the new probe explicitly replaces only the unrelated ETL scheduler transport with an inert async seam because ENABLE_ETL_SCHEDULER is not consumed by that existing function; no source .env or shared interpreter is used.

Coordinator: preview final #589/#595 heads with merge-tree, integrate #589 first, reconcile #595 onto that accepted integration, rerun both actual startup/readiness and IMF/debt/fiscal/API cohorts, then run full immutable manual CI and fresh complete bot body/thread/request readback. Authors leave all operational and roadmap issues open. This PR is draft and cannot establish combined or production acceptance. No hosted Actions were activated or dispatched, no paid bot was requested, no deploy/restart/merge was performed.

At the documentation freeze, the final repaired submitted fixture passes52 controls; the previous broader source cohort passes493. These are historical precommit executions. Delivery requires fresh complete source-bound current/minimum/Linux replay and independent reports at review-standards/FINAL.md, review-spec/FINAL.md and review-adversarial/FINAL.md under the external root. Final actual committed-corpus results are in CURRENT_ACCEPTANCE.json there; compare its HEAD/tree/corpus with the published draft before relying on them.

Readiness503 response: status=starting, reason is one of starting/stopped/database_unavailable/reference_initialization_failed/reference_check_failed/required_county_references_unavailable, retry=next_normal_start_after_writer_completion_or_reference_repair. Exceptions stay in server logs; response text has no arbitrary database diagnostics. Health live remains200 during actual blocked database startup.

## Coordinator correction — 2026-10-10 (PR604)

Copilot comment 4237305207 identified a mismatch between the intended contract
above and the county check: it skipped unknown Kenyan county names. All 47
supported names plus an unknown row could therefore become ready. The check now
refuses that population. The actual audits-writer fixture covers both an already
complete population plus an unknown row and a 46-name/count-decoy population
that becomes 47 supported names plus the retained decoy after writer completion.
Both remain 503; the decoy is preserved for explicit reference repair.

Comment 4237305236 identified credential values persisted by the recorder.
`DATABASE_URL`, `JWT_SECRET_KEY` and `BATCH9_BOOTSTRAP_POSTGRES_URL` are now
redacted in portable environment metadata and have boolean presence fields.
The real child still receives the required inputs. Toy-secret controls execute
under ordinary Python and `-O`, prove unchanged child values without echoing
those values, and check that portable metadata/logs contain none of them. This
changes environment metadata; commands and raw child output remain records of
what was executed, so recording commands that deliberately echo secrets is
outside that redaction guarantee.

The pre-correction recorder bytes and identity are retained in
`history/copilot-2026-10-10/`. `COPILOT_CORRECTION_2026_10_10.json` declares the
old tool/receipts historical and superseded for current checkout acceptance.
MANIFEST.json, its archive and all original execution histories are unchanged.
Fresh current/minimum acceptance is external under the coordinator's
`BATCH_10_MERGE/604` evidence directory after the final committed corpus is
frozen. The recorder snapshots the complete source, command, interpreter,
environment metadata and actual exit; the receipt verifier must accept that
exact current source, rather than rebinding an old author run. #603, #583 and
the broader operational gates remain separate pending work.

## Hosted correction — 2026-10-10 (#591/#616)

The frozen combined f75 full hosted run failed five backend cases and ten browser
coordinator cases; it is diagnostic, not merge acceptance. The backend failures
are distinct: the financial context pin correctly required re-review after
PR604 changed main.py, and the receipt verifier's import wrote bytecode inside
its measured three-file inert Git fixture. The latter is not sibling historical
source copying. Local parent `PYTHONDONTWRITEBYTECODE=1` had hidden that import
side effect. The verifier now prevents only its import write and restores the
caller flag. It still measures every existing cache/source file and refuses
source/output/generator/verdict/provenance tampering under ordinary Python/-O.
The new controls explicitly set bytecode unset/0/1, including pre-existing
measured cache files, and preserve source/Git status and original receipt/logs.

The dated financial context review links exact old/new source/AST identities,
unchanged four raw sites and dispositions, all financial callers and changed IMF
publication/fallback paths. `HOSTED_CORRECTION_2026_10_10.json` and retained old
inventory/verifier/test snapshots preserve prior tool and history bytes. Old
receipts remain bound to their original source and do not certify this changed
candidate. New external current/minimum receipt and financial gate executions
must bind the final published corpus; frozen full hosted acceptance is separate.
#591/#616 track these repairs; #603/#602/#583 stay pending. The independent browser
fixture repair is tracked in #615 and owned in PR606.

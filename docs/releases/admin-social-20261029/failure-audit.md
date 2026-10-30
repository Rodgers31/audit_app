# Release failure audit — 29 October 2026

Follow-up: all 708 cases skipped in this audit have since executed and passed in their explicitly assigned fixtures. See the [skip audit and latest combined validation](skipped-test-audit.md). This document and its 93-case receipt retain the earlier execution history.

The earlier 60 failures and 33 errors required diagnosis even though the same IDs failed on accepted main. Baseline parity established that the UI/social changes did not introduce those failures; it did not establish release readiness. This audit re-executes the original cases and preserves the source, approval and publication safeguards.

**Final full native social run: 4,473 passed, zero failures/errors, 708 explicit historical-fixture skips and 84 passing subtests in 472.26 seconds. All 93 original cases executed exactly once and passed, with zero skipped or missing.** See the [case ledger and skip reasons](failure-audit.json), [runtime/input receipt](failure-audit-validation.json) and [production status](production-status.json). The unchanged frontend's 2,792 passing tests, types, lint and production build remain valid; those product bytes did not change in this audit.

## Causes and repairs

| Original cases | Cause | Repair and release implication |
|---|---|---|
| 46 failures | Historical SQLite unit producers fabricated `county:1:budget:2025` / `job:42` source identity and lacked a current worker witness. The real verifier correctly refused them before their intended policy assertions. | Named synthetic unit setups now explicitly install an exact observation-hash/SQLite-Engine-bound test port. The incompatible `UNIT_AUTHORITY_ONLY` marker is rejected by the real production verifier. Original assertion bodies remain; current PostgreSQL approval and refusal paths are exercised separately. |
| 33 errors | The offline Python image lacked FFmpeg/ffprobe. Thirteen cases additionally required their separate guarded Meta Reels database once media setup could proceed. | Add verified media/process executables through read-only mounts into the exact old Python runtime, and provision both named, isolated test databases. All 33 test bodies execute. Live production media binaries were checked separately. |
| 6 failures | The source archive lacked a Git index required by the bounded worker inventory. | Supply a private index for the exact test source. Preserve the production inventory guard. |
| 6 failures | The external test launcher lacked a `__main__` guard, so multiprocessing spawn recursively launched pytest. The descendant inspection also needed the missing process tool. | Add an empty repository `tests/__init__.py` to prevent an installed third-party `tests` package masking this repository; execute native `python -m pytest` with verified process tools. A guarded external-launcher comparison also passes all six cases. This was a defect in the earlier validation harness. |
| 1 failure | A test wrote its diagnostic receipt to absent `/output`. | Use pytest `tmp_path`; retain the actual worker/source gate assertions. |
| 1 failure | A target-safety test called a renamed crash helper and supplied an obsolete engine fake. | Call the current helper, model its schema-discovery read, and assert the child schema in addition to the existing validated endpoint/environment assertions. |

Only tests and release documentation change in this audit. Backend/frontend product files, migrations, workflow definitions, dependencies and activation defaults remain byte-identical to the previously reviewed candidate. No skip/xfail is added to close an original failure. A test-only authority marker never qualifies production evidence.

## Targeted and independent execution

The exact 93-case ledger links each old result to its cause and final executed outcome. Source group: all 46 originals plus 18 new fixture-boundary cases pass; the complete affected five-module neighborhood covers 137 distinct passing cases. Four direct identity diagnostics, three real current-PG approval/hold cases and 15 existing unmocked current-PG refusal/mutation cases pass. A genuine missing witness remains `SOURCE_REVIEW_REQUIRED`; attested unchanged current county/native evidence verifies; publishing remains paused with zero publish attempts.

The remaining 47 original cases pass natively with zero skips, including all 33 media cases, six metrics cases, six Git rehearsals and both test repairs. All 97 Python distribution versions match the previous runtime. The 171 read-only executable/library additions preserve the runtime's existing OS files; cached tool images with different Python distributions were not substituted.

Independent cross-review executes 89 endpoint/schema and unit-boundary cases plus ten fresh-PG/marker/package cases, with three additional independent owner/session-boundary attacks. Production verification directly rejects unit markers for every supported witness family. The final whole-suite run separately verifies all 93 original cases. Its 708 skipped cases require other explicitly named historical fixture/role environments; they remain unverified coverage, with every skip reason preserved in the ledger.

The outcome ledger is checked against the pinned original 93-case inventory. Each original must appear exactly once in the final JUnit output with no skip, error or failure, and the native process must exit with integer zero. Independent attacks exposed weaknesses in the initial aggregation script; the repaired script passes 24 controls, including optimized Python, substituted identities, missing/duplicate/skipped cases, boolean exit codes and stale-success removal. A failed audit cannot retain an old successful receipt.

## Read-only production verification

Backend Render deployment `dep-dbhm6regekts73ble1b0` on service `srv-d6hr3t5m5p6s73bomqu0` runs accepted SHA `7797ecb4266169c438ecd2c82e6d817d6577ff19`; auto-deploy is disabled. Health and readiness return HTTP 200. GitHub's latest successful Production frontend deployment is `7416253537` at the same SHA. This PR candidate has not been deployed.

The application login's PostgreSQL transaction was explicitly read-only, with statement/lock deadlines and rollback. Migration is `a756b20a0001`. Global publishing, automatic approval, scheduling and publication are all false (control version 1); both Facebook/Instagram accounts have publishing disabled; the target table is empty. `/proc` inventory positively identifies the Gunicorn master/web worker and finds no social worker or supervisor. The recorded social heartbeat is stopped and stale, as expected while workers remain off; it is not reported as healthy.

All four current native/report authority and snapshot views exist and grant SELECT to the current app login. This verifies prerequisites, not the publishability of any particular historical draft. Current evidence must still pass the real guard during preparation/approval. `/usr/bin/ffmpeg` and `/usr/bin/ffprobe` both execute successfully at version `7.1.5-0+deb13u1`.

`SOCIAL_MEDIA_ENABLED=false`; worker/native/operational-policy/financial-generation/studio/generation-hook/report-generation flags are absent with documented defaults off. A fresh authenticated production page loads publishing-paused status, no queued destinations, no available adapters, automatic publishing off, media storage disabled and per-account publishing disabled. The earlier unavailable status response is no longer reproduced after a full reload; no speculative cause is assigned.

No production draft, control, source, schema, grant, environment or deployment changed. No provider request, upload, ingestion, backfill or worker start occurred. CI/CD and Docker deployment workflows remain disabled; unrelated ingestion schedules are untouched. These observations confirm the held deployment state, not provider access or activation readiness.

## Local runtime recovery

An attempted diagnostic tool-image augmentation exhausted local disk and stopped Docker Desktop. Only task-owned redundant archives/caches and completed setup containers were removed; hashes and cleanup receipts are retained. Official Docker Desktop stop/start commands recovered the runtime without reset, update or global pruning. The local review server was restored and returns HTTP 200. Subsequent verification uses read-only tool mounts, avoiding another image build. Production was unaffected.

Owner PR review and a separately approved complete backend/frontend rollout remain outstanding. Preserve all publishing and worker holds through that rollout; production source acceptance and eventual activation remain separate work.

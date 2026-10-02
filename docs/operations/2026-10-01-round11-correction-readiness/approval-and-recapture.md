# Per-action approval and exact recapture contract

**Prepared review request; unsigned. No production authorization.** This document supplies what the release owner must review later; it does not ask the current session to connect or execute.

## Evidence recapture

Use approved operator tools and secure connection provision; never read default dotenv/production credentials from this packet. All preparation captures must start an explicit repeatable-read READ ONLY transaction, read back `transaction_read_only=on`, set statement timeout8s/lock timeout2s, and finish ROLLBACK. The banked bounded capture additionally proves refused INSERT(SQLSTATE25006) under a savepoint. OAG's tool enforces READ ONLY without an INSERT probe; coordinate the additional probe through the existing capture helper if required. Do not claim it probes when it does not.

Bind capture time, deployed commit/tree, actual database/schema/revision, complete reflected columns, all dependency catalogues/references, source URL/page/version/hash and full before-images to exclusive durable artifacts. Recapture *after* preceding writes, not from a predicted local manifest. Projection overflow/new catalogue columns/drift means stop and review revised bounds. The banked general capture used47 counties/25 audits/10 documents/3 population rows/30 source-FK columns/15,000 IDs per column and a2MB ceiling. Retain the full transport capture behind compact receipts; no partial/truncated result passes.

The existing tools remain the sole repair routes:

- OAG: `scripts/verification/oag_boundary_correction.py`, `OAG_BOUNDARY_DATABASE_URL`, reviewed manifest/PDF, `--output` new full plan. Validate with `--plan` and `--expected-plan-sha256`, without `--commit`. A separately authorized commit/recovery uses the exact same plan/digest and new durable intent path; `--recover` selects recovery.
- CPI: `scripts/verification/cpi_source_correction.py`, `CPI_CORRECTION_DATABASE_URL`, exact manifest and both `--january-pdf`/`--december-pdf`, new full plan output. Validate with `--plan`/`--expected-sha256` without `--commit`. Recovery uses `--recovery <resolved-receipt>` and its independently reviewed canonical digest; it cannot use a synthetic rehearsal plan.
- Remote PostgreSQL connection rules are inherited from OAG `cli_engine`: explicit host/database, pinned psycopg2, exactly one strong TLS mode(require/verify-ca/verify-full); no default DATABASE_URL/env-file fallback. No credential values belong in logs or approval text.
- Codes/publishers: the banked exact SQL and inverse SQL are **rehearsals ending ROLLBACK**. There is no production commit switch. Any future operator execution artifact must be separately reviewed as concrete SQL with its own byte digest and exact transaction ending, preserving every guard. Do not blindly change ROLLBACK to COMMIT or call a successful rehearsal a repair.
- Cleanup: run existing `tools/prepare_legacy_evidence_cleanup.py <actual-reviewed-postcode-manifest> <new-output-directory>` offline. Both rendered scripts end ROLLBACK. Review their complete byte hashes plus actual recaptured manifest; do not reuse the September27/30 whole-document snapshots against later metadata.

OAG requires baseline Git object `c76ad74877dcd29a284b548c928f59538553fa0f` and current parser replay. Its source SHA256 is `aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896`. Reviewed old live plan digest `57a73173edaa838a589c3e5e5a091042da801db3a23c6d8050ab6b0ced36338a` is inherited observation, not a permanent execution key.

CPI exact JanuaryPDF SHA256 `ca9654579a2a0b8d14301de005cea70f1db2943c8d40cb111be3b8b1e0ccd44d`; DecemberPDF `75e6f741704874180edd8378ec6219c5920f15082496e6bf47aa00e0f7570614`; bothTable1,p2,February 2019=100. Shared1715/1823 remain unchanged. Symbolic source/extraction refs become concrete allocated/reused IDs only in actual execution/resolved receipts. Plan digests use the existing normalized/sorted/indented JSON plus newline hashing; file hashes alone cannot substitute for a tool canonical digest.

## Owner decision fields — no default approval

For **each** ledger action proposed for execution, record:

| Required field | Review requirement |
| --- | --- |
| Decision and signer | Explicit approve/refuse/defer, authenticated release owner, UTC timestamp and approved time window |
| Scope | Action ID/issues, exact rows/fields/paths/counts; all excluded writes and protected records acknowledged |
| Code | Actual deployed release commit/tree, tool file hashes, schema revision and feature/settings parity receipt |
| Evidence | Source artifact/version/page/byte hashes, capture timestamp and complete full before/after/dependency manifests |
| Plan | Canonical plan digest where tool-defined; manifest/forward/recovery/execution byte SHA256s; fresh READ ONLY preflight receipt |
| Backup | Full backup identity/hash, secured location and independently successful full isolated restore receipt |
| Concurrency | Named writer freeze/window and short lock policy; no broad/shared writer executes concurrently |
| Recovery | Exact inverse plan/receipt/digest, uncertain-commit readback procedure, newer-metadata refusal/review process |
| Acceptance | Expected postcommit row/source/API/browser values and unchanged controls; next-writer check where applicable |
| Separate authority | Data write, recovery, platform secret/settings changes, cache request, migration/adoption and final Actions enable/run are separately named |
| Evidence expiration | Any drift, source reissue, deployed version/settings change or elapsed window invalidates approval; review refreshed artifacts |

The owner must approve the **actual post-code cleanup packet** after code application and recapture. A single pre-code signature cannot authorize a later unknown metadata image.

Configuration approval for231 must name platform owners and same secret provision on Actions/Render/Vercel through approved secure channels, actual endpoint variables, cross-worker generation storage/permissions and signed refusals. This packet records no actual current secret equality. Once configured, owner still separately approves final Actions enablement/exact domain run, subject to account access and source/history gates.

## Postwrite and recovery acceptance

Record exact transaction result and returned IDs plus new READ ONLY full after-images. OAG/CPI intent files are durable prerequisites, not commit receipts: independently classify exact before-state/exact after-state/mixed-or-unknown before any retry/recovery. Mixed/unknown/drift stops the operation. Do not erase later unrelated metadata; cleanup recovery needs a new reviewed rebase if newer JSON exists, while code/publisher inverses touch only their cells/column.

Verify public identities and source chain after separately approved signed refresh. For379 compare all three full public text hashes to manifest after-hashes, cited paragraphs and next loader;CPI checks value/unit/type/date/source/page/hash/publication and retained annual history;codes checks official code plus stable route identity;publishers checks labels and preserved references;cleanup checks selected absence and all preserved projects. A verification endpoint returning unverified/unknown is no evidence.

KRA acceptance retains separate publisher versions/bases/null publication dates. Any stored delta awaits its own concrete complete plan; this packet cannot authorize it. OAG catch-up follows Session3's source/coverage/preservation matrix and bounded serial runbook. National2392's335 retirements/two revisions are not included. Full seed validation failure prevents refresh.

For231 demand actual ordered success: source-approved seed, full validation, API invalidation across workers, exact acknowledgement of all paths in `frontend/lib/revalidation/paths.json`(including/counties/[id] and/accountability/unaccounted-funds), and visible changed data without another deploy. Save bounded before/after API and rendered receipts with retained source versions, valid zero/absence controls and timestamps. A local successful browser demo,TTL expiry,restart,or skipped job does not meet this acceptance.

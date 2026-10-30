# Pending-bills retained source identity — 30 October 2026

Nightly job 3531 processed the national half but refused the county write with `Exact retained PDF lineage required`. The preceding county-budget writer refreshed shared source 2549's display title. The pending-bills title lookup then created a different row from the one bound by the genuine retained PDF receipt.

Validated native report ingestion now selects the unique Kenyan source by its exact URL, preserves its existing title/type/metadata/publisher, and requires a retained receipt's source ID to match. Ambiguous URLs, conflicting publishers, malformed metadata and changed/reconstructed capabilities refuse before source mutation. Capability admission checks the constructor snapshot and sealed observation manifest; the full retained-proof/current-job/artifact guards remain unchanged and recheck after locking. Fresh native acquisitions create a source only when no matching source exists. Legacy unqualified title/edition behavior remains unchanged so aging replacement and nonresurrection rules retain their existing contract.

## Executed validation

- Actual county-budget title refresh → retained PDF → 46-row atomic pending-bills writer reproduced the exact pre-fix error, then passed with unchanged source identity and all balances.
- Normal wider pending-bills/aging selection: 503 passes, no skips. Final stricter admission/real-PG/publisher selection: 10 passes. Actual optimized Python full selection including the six new admission cases: 509 passes, no skips.
- Independent final real-PG scope: 19 passes; five earlier legacy-PG aging passes carry with verified unchanged legacy bytes. Forged proofs, duplicate URLs and post-commit source changes still refuse; one genuine Nairobi-only change creates one review draft after a silent cohort.
- Independent final helper scope: 54 passes, no skips. Its five direct-helper capability failures were reproduced before the final admission fix; all now refuse before SQL. These reports supersede the withdrawn generalized-helper findings: [spec](pending-bills-lineage-20261030/spec-review.md), [standards](pending-bills-lineage-20261030/standards-review.md).

No migration, permission, credential, service, source guard, financial value, workflow or activation flag changes are included.

## Release and production gates

The four admin/source PRs #850–#853 are already merged and deployed as `b7eadcb3dde3b7e5236222b8b981b9b0f3786510`, tree `dc8da34e06e1f1112d882d739f6afd4c0ffdcde6`. Backend Render artifact: `dep-dbi9a5flk1mc73fl9ovg`; frontend Vercel artifact: `2viCQgG8YyEmPNx9HLUhDxdmxSyU` (`audit-x0necs9r4-rodgers31s-projects.vercel.app`). Fresh production verification matched all 24 changed backend runtime files, unchanged migration a756b20a0001, all four global controls false, Facebook/Instagram publishing false, five posts and zero publications/targets/assets/uploads/attempts, and positive Gunicorn/no worker inventory. Public backend health/readiness returned 200; the authenticated production UI showed the redesign and paused controls.

This repair is not deployed by these local results. #849 production acceptance remains open. After reviewed merge/deploy, admit the exact repaired main SHA to the existing selected-domain runner. Use at most two bounded pending-bills refreshes to prove complete automatic cohort baseline and zero-duplicate replay, with real unchanged stock/aging readback. Temporarily enable only financial draft generation for those observed runs, then restore it off; publishing, media uploads, social/studio/retirement workers, supervision and the ordinary admin consumer remain off. A reasoned single-record backfill and a fresh duplicate command remain separate checks. No synthetic financial change may be introduced into production.

The pending-bills hook retains finite 120-second financial, 30-second report and 10-second source/receipt reserve bounds (160 seconds with both phases). Partial or unverified outcomes cannot satisfy cohort acceptance. The existing public GitHub runner handles the retained 53.56 MB PDF; do not parse it on the 512 MiB Render process.

Rollback: retain Render `dep-dbi9a5flk1mc73fl9ovg` / b7eadcb as the previous immutable backend artifact; no schema rollback is needed. Keep financial generation off if any lineage/amount/aging/duplication/hold check fails. The frontend files do not change in this repair, and its accepted artifact stays in place. Restore the original Vercel Automatic ignored-build behavior after the backend-only repair push/merge hold.

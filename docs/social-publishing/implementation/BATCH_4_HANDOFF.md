# Batch 4 status and next work

2026-10-08. Base: `f5239ed63e146650bee2d0fb1cec9b23616eb648`.
The reviewed media (#513), schedule (#514) and native (#515) changes are merged.
Feature issues #482/#483/#484/#491 are closed; operational issues #481/#488/#490
remain open. `BATCH_4_CONTRACT.md` records the current ownership and boundaries.

## Agent locations and assignments

All worktrees are under `/Users/roger/.codex/worktrees/<name>/audit_app`.
Existing branches were preserved; these new branches start from merged main.

| Owner | Worktree | Branch | Delivered scope |
| --- | --- | --- | --- |
| Media agent | `social-maintenance-batch3` | `codex/social-media-acceptance` | Strict offline social bucket/browser/host evidence evaluator for #490 |
| Native agent | `social-adapters-batch3` | `codex/meta-privacy-prerequisites` | Signed-request verification and declared ownership binding for #488 |
| Schedule agent | `social-schedules-batch3` | `codex/social-operating-acceptance` | Seven-day operating-budget and hosting/capacity evaluator for #481 |
| Root | `social-batch3-integration` | `codex/social-operational-integration` | Contracts, cross-agent adversarial review, combined verification and scoped PRs |

All three implementation assignments and root's code verification are complete.
The agents are idle after scoped commits: media `b36d260`, privacy `00b63bf`,
operating evidence `53dba78`. Root integrated each into the branch above.
No unfinished or interrupted coding assignment remains. Scoped draft PRs use
those head branches; the live PR links are recorded in roadmap
[#476](https://github.com/Rodgers31/audit_app/issues/476) after creation.

Detailed briefs are `MEDIA_OPERATIONAL_ACCEPTANCE.md`,
`META_PRIVACY_CALLBACKS_PREREQUISITES.md`, and
`docs/infrastructure/supabase-egress/OPERATING_ACCEPTANCE.md`. The dirty primary
checkout remains outside this batch.

## Executed verification

- Integrated backend social suite: **1,545 passed, zero skipped**, including all
  four explicit disposable PostgreSQL lanes. Operating evidence suite:
  **142 passed, zero skipped** in the integrated checkout. Two existing
  SQLAlchemy declarative-base warnings remain.
- Media: 170 authored tests; independent review exercised 261 cases, with the
  one-second configured timeout accepted as a legitimate positive. A second
  independent reviewer executed 169 checks. Root rejected 1,337 invalid-type
  mutations against the final schema and verified clean decoder contexts.
- Privacy: 207 authored tests plus 33 independent cases; root reran all 240.
  A malformed exact-type UUID finding was reproduced, fixed and retained.
- Operating evidence: 142 authored tests plus 55 focused independent tests
  passed together (197). The full independent matrix executed 357 cases,
  including threshold/DST, file, CLI, counter-history and protocol-zero cases.
  Root independently replayed the first five failures using reversed draft
  hunks, and absent counter history against an actual saved pre-fix source.
- Confirmed false positives now have observed-red regressions: copied daily
  receipts, understated capacity, 31-day social/growth overruns, omitted accrued
  charges, missing restart/history coverage and zero protocol measurement with
  an active worker. Named-pipe input, impossible child limits, raw decoder
  contexts and inconsistent probe/global accounting were also executed and fixed.

The owned PostgreSQL server was stopped after verification. No live provider,
storage, production migration, configuration, billing or deployment operation
was performed. There are no frontend changes in this batch. At the merged base,
frontend tests passed 501; three pre-existing TS2353 map-style errors reproduce
on main and remain a baseline limitation. Hosted required Actions checks remain
disabled under the existing setup; local receipts are not hosted CI evidence.

All tools validate declarations only. Synthetic fixtures remain blocked or
unverified; matching operator assertions authenticate no receipt and authorize
no production, publishing, storage, maintenance or deletion action. The privacy
helpers add no public callback or durable ownership lookup. Operational issues
#481/#488/#490 remain open.

## Remaining operational work

1. #490: identify the actual private social bucket, exact browser origin and
   intended host, then obtain separately authorized storage/browser/host and
   backup/retention/quota receipts. Source-evidence storage acceptance covers a
   different workload. Write-quiescence verification remains unsupported, and
   ready-original deletion remains deferred.
2. #488: establish app/host/key restoration/ingress-redaction/role receipts and
   provider-verified ownership. Implement durable indexed callback ownership,
   idempotent request tracking, response/status endpoints and reviewed retention
   policy before live privacy callbacks or OAuth acceptance.
3. #481: collect seven representative closed deployed days of provider egress,
   measured social transfer, workload coverage, accepted always-on hosting and
   verified database capacity. Synthetic fixtures do not establish actual
   operating headroom or a plan/downgrade decision.
4. Only after the receipts and an explicit enablement decision, assemble and
   validate the real runtime in separately authorized live acceptance.

Broader formats/platforms, generated drafts and automation remain later roadmap
items. The three offline scopes prepare the current native slice's remaining
gates; they do not activate live publishing or close the operational issues.

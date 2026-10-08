# Batch 4 status and next work

2026-10-08. Initial base: `f5239ed63e146650bee2d0fb1cec9b23616eb648`;
review closeout includes main `8ba731a5a76913abdb7ff2956e21731cd1cf445c`.
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
The agents are idle after completed implementation and review repairs: media
`c49d709`, privacy `6d40e8b`, operating evidence `7d3902e`. Root integrated each
into the branch above and independently replayed the observed failures.
No unfinished or interrupted coding/review assignment remains. Deliveries are
[#517](https://github.com/Rodgers31/audit_app/pull/517),
[#518](https://github.com/Rodgers31/audit_app/pull/518), and
[#519](https://github.com/Rodgers31/audit_app/pull/519).
Final merge state and squash receipts are recorded in roadmap
[#476](https://github.com/Rodgers31/audit_app/issues/476).

Detailed briefs are `MEDIA_OPERATIONAL_ACCEPTANCE.md`,
`META_PRIVACY_CALLBACKS_PREREQUISITES.md`, and
`docs/infrastructure/supabase-egress/OPERATING_ACCEPTANCE.md`. The dirty primary
checkout remains outside this batch.

## Executed verification

- Final integrated backend social suite: **1,574 passed, zero skipped**, including all
  four explicit disposable PostgreSQL lanes. Operating evidence suite:
  **163 passed, zero skipped** in the integrated checkout. Root also reran all
  **88 final independent operating cases** successfully. Two existing
  SQLAlchemy declarative-base warnings remain.
- Initial media: 170 authored tests; independent review exercised 261 cases, with the
  one-second configured timeout accepted as a legitimate positive. A second
  independent reviewer executed 169 checks. Root rejected 1,337 invalid-type
  mutations against the final schema and verified clean decoder contexts.
- Initial privacy: 207 authored tests plus 33 independent cases; root reran all 240.
  A malformed exact-type UUID finding was reproduced, fixed and retained.
- Initial operating evidence: 142 authored tests plus 55 focused independent tests
  passed together (197). The full independent matrix executed 357 cases,
  including threshold/DST, file, CLI, counter-history and protocol-zero cases.
  Root independently replayed the first five failures using reversed draft
  hunks, and absent counter history against an actual saved pre-fix source.
- Confirmed false positives now have observed-red regressions: copied daily
  receipts, understated capacity, 31-day social/growth overruns, omitted accrued
  charges, missing restart/history coverage and zero protocol measurement with
  an active worker. Named-pipe input, impossible child limits, raw decoder
  contexts and inconsistent probe/global accounting were also executed and fixed.

## Review closeout and newly tracked findings

All three inline Copilot threads and the review-body findings were evaluated.
The privacy dataclass options failed on actual Python 3.9; removing the three
unsupported `slots` options preserves ordinary frozen assignments, redaction
and declaration-only binding. The two helper sources execute on actual 3.9.6
and 3.13.9; 242 retained cases plus independent 88- and 156-case matrices pass
on both runtimes. Full application startup on the available Python 3.9 remains
untested because that interpreter lacks SQLAlchemy; no dependency was installed.

Media review repairs require raw lowercase HTTPS and two-copy capacity for a
retained probe. Independent review additionally found nonliteral browser origin
spellings, tracked in [#520](https://github.com/Rodgers31/audit_app/issues/520).
The fix rejects empty delimiters/default ports/numeric aliases; 197 authored
and 64 independent cases pass, plus 319 additional origin/type challenges.
Root replayed all 18 new direct/CLI regressions red against the reviewed source.

Operating review repairs preserve CLI provenance, consistent social measurement
bases and query receipt capture after its actual snapshot end. Protocol future
traffic remains an explicitly labeled planning proxy, never a provider bill.
Independent review found positive future worker units with a zero wire-cost
upper bound, tracked in [#521](https://github.com/Rodgers31/audit_app/issues/521).
Both inclusion modes now block that contradiction while provider-metered zero,
zero future units and rounded zero with positive uncertainty remain valid.
Root replayed the nine review regressions and four #521 regressions red, then
reran the final authored and independent suites green. Existing parent issues
#481/#488/#490 cover the remaining operational gates; no duplicate issue was
opened for those already tracked requirements.

The owned PostgreSQL server was stopped after verification. No live provider,
storage, production migration, configuration, billing or deployment operation
was performed. There are no frontend changes in this batch. At the merged base,
frontend tests passed 501 in the earlier merged-base receipt. PR #516 subsequently
fixed the map/build compatibility prerequisites under #511. Root's current-main
TypeScript check passes with its matching dependency set; the former TS2353
errors are historical. Hosted required Actions checks remain
disabled under the existing setup; local receipts are not hosted CI evidence.

All tools validate declarations only. Synthetic fixtures remain blocked or
unverified; matching operator assertions authenticate no receipt and authorize
no production, publishing, storage, maintenance or deletion action. The privacy
helpers add no public callback or durable ownership lookup. Operational issues
#481/#488/#490 remain open.

## Remaining operational work

1. #488: implement durable indexed callback ownership, idempotent request
   tracking, response/status endpoints and safe deauthorization behavior.
   Establish provider-verified ownership and an approved retention policy;
   supplied signature/identity matches do not complete deletion. App/host/key
   restoration, ingress-redaction and role receipts remain operational gates.
2. #490: identify the actual private social bucket, exact browser origin and
   intended host, then obtain separately authorized storage/browser/host and
   backup/retention/quota receipts. Source-evidence storage acceptance covers a
   different workload. Write-quiescence verification remains unsupported, and
   ready-original deletion remains deferred.
3. #481: collect seven representative closed deployed days of provider egress,
   measured social transfer, workload coverage, accepted always-on hosting and
   verified database capacity. Synthetic fixtures do not establish actual
   operating headroom or a plan/downgrade decision.
4. Only after the receipts and an explicit enablement decision, assemble and
   validate the real runtime in separately authorized live acceptance.

Broader formats/platforms, generated drafts and automation remain later roadmap
items. The three offline scopes prepare the current native slice's remaining
gates; they do not activate live publishing or close the operational issues.

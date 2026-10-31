# PR859 worker audit-head repair and deployment

Both [review comments](https://github.com/Rodgers31/audit_app/pull/859#discussion_r4428856764) [identify the same valid invariant gap](https://github.com/Rodgers31/audit_app/pull/859#discussion_r4428856833). The ORM reader selected one audit edition, while the restricted worker's current and owner-only snapshot views still exposed same-job historical editions. Retaining the receipts is intentional; authorizing an unselected edition is not.

## Repair

Both SQL views now require an audit receipt's own job to select that extraction under its exact scope. The scope must be a string containing 32 lowercase ASCII hex characters. The head must be a JSON number whose canonical text equals the integer extraction ID; JSON strings, booleans and floating-point spellings do not become IDs through coercion. The full audit series map is also a digest dependency, so later map changes invalidate a previously captured witness. Other native domains retain their prior fingerprint inputs.

The two accepted definition hashes change together:

| View | Prior SHA256 | Repaired SHA256 |
| --- | --- | --- |
| Current | `921b807c9637ae9541cf63e74313a4816875afef3de92d42cf6fc25226b09f4a` | `95c130e2106639dcaa3519951bfa9baa49b52c7fdd677b0dbfe1f0e744b3975a` |
| Snapshot | `f219c56c5f21622cfae0fe875e2020770859c90f2d1978625d21a40781aa6ba6` | `7549c1de87fb44bf1f00b1a9b0ca39b2859d8b1e9a3d898f9203ab4a496faf1e` |

No witness-format version, table, role, grant, RLS policy or migration changes. Old audit witnesses require renewed source review; unrelated native report/financial witness semantics remain unchanged. Existing production audits lack an accepted date/scope contract, so this repair does not manufacture an audit post.

## Executed verification

The 21 permanent restricted-role cases produced **17 desired failures / 4 positive controls** against the original PR head. The real SQL views returned an unselected historical receipt and the actual Core worker verifier accepted an old captured witness. Typed malformed maps and a later unrelated map mutation reproduced the same problem. Corrected SQL passes all 21 cases. Earlier fixture setup errors are retained separately and receive no regression credit.

The final application selection passes **608 distinct cases normally and 608 with actual Python `-O`**, zero failures/errors/skips. The preliminary 98-case worker/ACL selection overlaps this total. Independent Spec review accepts 24 cases per mode, including hostile scope JSON/Unicode, all twelve unaffected branch projections and a real qualified KRA financial witness. Original #802 source acceptance remains the earlier, separately scoped evidence.

Independent Standards review passes **55 PostgreSQL cases per mode** (29 operator/prerequisite controls and 26 worker controls) and **nine explicitly checked fresh-process upgrade/restore/reupgrade stages per mode**. It uses actual prior and repaired application modules, not an override of accepted hashes. The [Spec report](spec-review.md), [Standards report](standards-review.md), [installed-contract inventory](install-inventory.md) and [reviewed source hashes](reviewed-source-sha256.json) retain those limits.

Lossless [root](root-evidence.tar.gz), [Spec](spec-evidence.tar.gz) and [Standards](standards-evidence.tar.gz) archives preserve raw commands, logs, XML, case ledgers, historical failures, checksums and executable fixture inputs without adding discoverable duplicate Python tests. The [archive receipt](archive-receipt.json) pins their exact bytes and physical member inventories. Unpack only into a fresh directory outside the checkout. The Standards archive includes all 126 entries in its original `SHA256SUMS`; verify them before replay. These archives contain no credential env files or newly downloaded official articles.

Replay requires the separately pinned source trees and cached runtimes. Candidate1 can be reconstructed by selecting exactly the root archive's manifest entries from the final checkout, replacing only its historical operator with the archived candidate1 operator; verify every entry before use. The final operator remains the separately tested file linked below. Recorded absolute paths are historical provenance, not instructions to connect to an existing service. Create fresh owned fixture databases/env files using the archived launchers; preserve the original output directory. Archive integrity verification does not rerun tests or establish production acceptance.

Application candidate1 is pinned at 6095 files, mapping SHA256 `d6a204b8f7982d91756c7624afcfee99daf317f1c438e79882d55fd29901d1dd`. The final operator is separately pinned at SHA256 `4c401a7d403ce4ebaccd6a85ad5d8990b45cafbb100d11f5fe0a278511916253`; its reverse wrapper and explicit production seeder hold were added after the application freeze without changing application/test bytes. Documentation and evidence additions do not relabel the original whole-tree snapshot as the final Git tree.

## Explicit installed-view operation

The normal installer deliberately refuses old or unknown installed definitions; it does not silently upgrade them. The [release operator](upgrade_native_views.py.bytes) is an explicit, separately reviewed operation using the existing owner connection. It starts no worker and contacts no provider. Its default is a rehearsal that restores the exact original state.

The operator requires runtime generation/media/native/studio/supervision/admin-consumer flags off, global publishing/automation controls false and all accounts' publishing false. It requires literal `AUTO_SEEDER_ENABLED=false`: unlike the other default-off flags, the application defaults its in-process seeder on in production. The missing-variable control was observed RED before this guard. It locks both views in AccessShare mode before authoritative inspection. This blocks competing owner DDL while allowing ordinary application DML on the referenced tables. The fixed 5-second statement and 2-second lock limits remain.

Only an exact prior/prior or repaired/repaired pair is eligible. Mixed, absent, unknown or permission-drifted installations refuse. A prior pair is replaced atomically with both reviewed definitions, preserving OIDs, owners, relation and column ACLs and security options. The complete actual role contract must pass before commit. An already-current pair verifies without replacement. No grants are created or repaired. Failure after the first replacement or contention on the second rolls back both.

## Deployment and rollback sequence

1. Keep publishing, uploads, workers and financial generation off. Preserve the existing frontend artifact and its settings; suppress automatic frontend builds during pushes/merge. Do not request a paid bot review. The observed personal automatic/push/draft review settings are all off, and effective branch rules contain no automatic Copilot review rule.
2. After fresh review census and normal merge policy handling, deploy only the reviewed merge tree to the existing Render service. No compute/plan change, migration or hosted source refresh. The frontend has no code delta.
3. Verify the deployed commit and installed file hashes before any view operation. Run `main(merged_sha, dry_run=True)` from the exact operator bytes, then `main(merged_sha, dry_run=False)` only after the rehearsal passes. Each uses in-service credentials with certificate verification; credentials are never copied out.
4. Read both installed hashes and metadata through a fresh connection. Run the existing restricted login's role verification, which starts no worker. Require unchanged business/post/delivery/media state and the four requested holds. Then update only the existing ingestion-approved SHA to the accepted merge commit, retaining the other repository variables and absent financial flag. Dispatch no workflow.

The prior accepted application is `e1a0d6be0aa990064ab50b622c0e04570e84dd52`, Render deploy `dep-dbiem2etlv9c73cv1p30`. If deployment fails before view replacement, restore that existing artifact; the views remain prior. If rollback is required after replacement, keep all holds, restore the prior application first, then invoke the same operator's `main(prior_sha, operation='restore', dry_run=True)` and finally `dry_run=False`. Its reverse direction requires the real prior builder and complete prior role contract; it cannot downgrade views under the new application or override accepted hashes. Restore the prior ingestion-approved SHA only if it was advanced. Never rewind source rows, cursors, immutable evidence or posts.

Abort on source/tree mismatch, new unclassified review material, unexpected active flags/processes, changed grants, unknown view state, failed rehearsal, missing fresh verification or unhealthy deployment. An interrupted operation is unverified until fresh readback establishes the actual state. None of this accepts current KRA catalogue-only financial evidence, combined OAG volume scope, national financial production adoption, media/publishing activation or the remaining launch gates.

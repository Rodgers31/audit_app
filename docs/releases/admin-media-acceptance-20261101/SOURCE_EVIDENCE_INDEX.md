# Source evidence scope and authority

**Start here for source identity.** [SOURCE_EVIDENCE.json](SOURCE_EVIDENCE.json) is the authoritative scoped reconciliation receipt for this documentation correction. Its `authoritative_scope` names an exact, immutable combined Git commit. It also binds the original media-only PR, companion UI/notification commits and the earlier combined assembly separately. The receipt and its [executable verification output](source-reconciliation.txt) establish file/blob identity and preservation of historical evidence; they do **not** claim that old tests were rerun at a newly identified commit.

The current bound combined source is `831f8d2779ffba42a729879f5087e76791064a85`, the coordinator assembly after the UI documentation and notification health-description review fixes. Its dedicated evidence ref is `codex/admin-publish-reviewed-source-20261101`. This is an immutable reviewed runtime snapshot before the new index files, not current `main` or the final media PR. This index and verifier were uncommitted and absent from that tree at capture; they are the subsequent documentation correction.

In a fresh clone, fetch the original companion PR objects and the dedicated reviewed snapshot first. The original media/notification commits are not ancestors of their cherry-picked combined equivalents, so a single-branch clone needs those original PR heads as well:

```sh
git fetch origin refs/pull/884/head refs/pull/885/head
git fetch origin codex/admin-publish-reviewed-source-20261101
git rev-parse FETCH_HEAD
# Require: 831f8d2779ffba42a729879f5087e76791064a85
python3 docs/releases/admin-media-acceptance-20261101/reconcile_source_evidence.py
```

A successful result means the selected immutable Git blobs match their scoped hashes and the retained historical JSON bytes remain unchanged. Historical comparisons report matching, different and absent companion files explicitly. A media-only checkout is not required to contain another PR's UI or notification files. The Python verifier itself uses stdlib and local Git only; it refuses unavailable objects and never fetches them. The separate fetch instructions obtain evidence objects without selecting a checkout or enabling a workload. This snapshot supplies no hosted test, deployment, ingestion or publication authorization. The verifier reads no environment credentials, database, storage, provider or network and runs no product tests.

## Review #884 disposition

The body-only [Copilot review](https://github.com/Rodgers31/audit_app/pull/884#pullrequestreview-5730649331) is **half-right: valid source-scope/index ambiguity, different mechanism**. The three files were not all stale final manifests:

| Retained capture | Actual scope and disposition |
| --- | --- |
| `status-sync-review-after.json` | Its five-file `sha256` and `final_sha256` maps match companion UI commit `0bc78394a3bbb638ab1fd26aa103ece2f47c6a51` and the pre-review combined assembly. Comparing them with isolated media PR `bb3fa2bea4b652bcbca5898c01cf1c7560149dc5` necessarily finds absent companion tests/browser files and base UI versions. Its `changed_files` records a historical transition, not a new statement that these final five hashes differ from the companion UI. |
| `independent-review-source-after.json` | An earlier mixed, uncommitted review-stage capture. Seven of nine files match the pre-review combined assembly; the composer and browser fixture were subsequently changed and reviewed. The original independent review followed this capture with schedule, clean-status, final-browser and receipt refreshes. There is no asserted full-tree commit for that intermediate stage. |
| `final-reviewed-source.json` | The original nineteen-file final assembly capture, **superseded for current source authority by this index and SOURCE_EVIDENCE.json**. All nineteen hashes match pre-review combined assembly `7b0611a` (the receipt records its full Git identity). This is a later verified file-set equivalence, not a claim that the earlier tests executed on that commit. It includes companion UI/notification files absent or different in the isolated media PR. The notification health-description review fix is bound separately in the new final scope. |

The reviewer was right that readers needed one unambiguous current entry point. Regenerating the raw captures against a media-only checkout would destroy their original meaning and pretend that old tests exercised different sources. All original JSON captures stay byte-for-byte intact. Their original raw SHA256, preservation commit, field names, stage descriptions and explicit comparison targets are recorded in the new receipt. The verifier compares both their preserved Git bytes and their worktree bytes.

## How to read the retained stages

- `source-before-production-cohort.json` and `source-stability.json` describe the original local media cohort. The source list includes unchanged media runtime and existing tests, not an assertion that companion UI/nightly features are present in a media-only PR.
- `independent-review-source-before.json` / `after.json` are the initial other-lane review stage. Their unchanged raw bytes are superseded by the subsequent targeted refresh receipts for later UI source changes.
- `final-refresh-source-before.json` / `after.json` are the immediate-schedule gate stage, before the later clean-status repair.
- `status-sync-review-before.json` / `after.json` are the clean-status repair stage. The final owner suite and independent probes remain distinct, overlapping executions.
- `final-reviewed-source.json`, `final-browser-review.json` and `final-acceptance-bookkeeping.json` describe the original final assembly and receipt checks. They remain historical captures. `committed-build-log-normalization.json` separately reconciles the original raw log with the committed LF representation.
- The new scoped receipt records the subsequent review fixes. Old notification probe results remain bound to the earlier helper; [review-885-red-green.json](review-885-red-green.json) and [the new 481-case probe receipt](review-885-health-probes.txt) cover the health-classification repair. No earlier result is silently promoted to coverage of changed code.

Read [LOCAL_ACCEPTANCE.md](LOCAL_ACCEPTANCE.md) for original test commands and limits, [COORDINATOR_ACCEPTANCE.md](COORDINATOR_ACCEPTANCE.md) for the separately executed PostgreSQL/native compatibility selections, and [INDEPENDENT_OTHER_LANES_REVIEW.md](INDEPENDENT_OTHER_LANES_REVIEW.md) for the ordered review stages. Their counts are not added together.

This reconciliation neither supplies nor closes production restore, independent custody, retention, privacy/provider or representative capacity/cost acceptance. Publishing, uploads, all workers and financial generation remain OFF. File identity verification does not authorize activation or decide the owner's merge/deploy policy.

## Reconciler verification

The retained [30-case author controls](source-reconciliation-controls.txt) and [independent review](INDEPENDENT_SOURCE_RECONCILIATION_REVIEW.md) exercise the CLI and direct API. The independent reviewer ran 102 cases and the complete real receipt. Observed-red controls exposed three defects in the new documentation verifier before publication: a Git tree counted as a file, a Git failure classified as an absent companion file, and a historical map reopened after its raw hash check. All source lookups now require a regular-file blob, every Git error refuses, and comparisons parse the exact already-hashed byte buffer. Array/object authority names now return structured refusal instead of an unhandled fail-closed exception. The original raw captures remain unchanged.

These are verification-tool checks, separate from product tests. The absent-receipt control and initial local Python name-collision error are retained as their original outcomes; neither is counted as a product test or as a successful source comparison. No cold-restore or media runtime code changed during this correction.

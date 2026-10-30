# Independent Standards review — combined release candidate

**Scoped pass on final frozen candidate 4: 86/86 backend and 40/40 UI cases. Two helper-level findings were reproduced and fixed; no actionable finding remains in the executed scope.** This is a review of the frozen merged code and exercised seams, not production/deployment, live-source, paid-provider, full accessibility or complete repository acceptance.

## Identity and verification

| Snapshot | Files | Manifest-file SHA256 |
|---|---:|---|
| Final combined candidate 4 | 5,730 | `7a90b35eef28e40825392676344a4ffd2f6ed70f7eece1ef51419ae82cbad8e1` |
| Executed product candidate 3 | 5,730 | `58f9922b53dd73b98b9988abe660cdcf94aba2af6efdb323b73b231b6c7fe9bb` |
| Earlier combined candidate 1, seen red | 5,730 | `1657041ae2e421531db0be44ec1088dc2398e3754d20077d8872f7ea2c6467de` |

Candidate directory: `/Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-candidate-4`. Manifest: `/Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-manifest-4.json`. The manifest records accepted main `7797ecb4266169c438ecd2c82e6d817d6577ff19` and merged integration head `b6d58afa03f37f8233f40a85be3778b19d6da562`. Accepted renderer baseline modules are loaded from exact `47a1490` Git bytes for replay comparison.

Every manifest file hash was checked before execution and again after final execution: zero mismatches. `provenance-before.json`, `provenance-3-before.json`, `provenance-3-after.json`, `provenance-4-before.json` and `provenance-4-after.json` retain identities and inventories. Candidate1→3 changes exactly four paths: destination helper, social copy helper, helper regression tests and the corrected author national-writer FY-label assertion. Candidate2 was transient and was not used for a final verdict. Candidate3→4 changes only `backend/tests/social/test_universal_copy_postgres.py`, using the existing restricted PostgreSQL fixture for its new author test. Every product, frontend and other test-helper byte is identical to3.

The full frontend execution copy contains 813 source files, all exact frozen bytes. Candidate3 and4 frontends are identical to candidate1, so it is executed from the verified read-only execution1 copy. `ui-copy-provenance.json` records this. The national delta from the integration head has five product backend paths and seven test paths; the only other byte differences are two existing Windows batch files with equivalent CRLF/LF content. Unicode archive paths were resolved with NUL-delimited Git inventory; those archives are byte-identical to the integration head.

`boundaries.json` proves 18 exact unchanged authority/admission/API/HTTP/worker/readers/dispatch/CLI files against the integration head. No migration, provider runtime or configuration repair was introduced by this review. Neither candidate nor any dirty author worktree was edited.

## Executed final evidence

| Independent execution | Cases | Receipt |
|---|---:|---|
| Destination, source/version, current writer, policy replay and closed-default backend controls | **86/86 pass**, 4.01s | `backend-3.txt` |
| Actual queue/public components, API decoders and query hooks | **40/40 pass**, 1.305s | `ui-final.txt` |

The 86 independent backend cases ran on candidate3 and carry to4 by complete product and used-helper byte identity. The 40 UI cases ran on the verified frontend shared by1/3/4 and consume the actual candidate3 saved DTOs. Counts are final cases once, not sums across overlapping runs. They exclude author suites, broad social accounting, root Chrome checks and the root full-cohort timing run. The single corrected author test was separately executed on candidate4: **1/1 pass**, 1.04s (`author-test4.txt`). It is not added to the independent counts. Expected Pydantic warnings from intentionally invalid model-copy values and dependency warnings are retained, not counted as failures.

Backend cases comprise 67 destination/version/writer controls, three actual policy fixtures and 16 default/unknown/error controls. UI cases comprise 26 county public-card controls, 13 queue/status controls and one real public HTTP receipt replay.

### Versioned text, links and source fidelity

New report-availability-v3 covers county and all four native report families; catalogue-availability-v3 points to the exact qualified entry. National budget/revenue financial-v4 changes the CTA and destination to the qualified original source. The ten national financial amount/context comparisons show the rest of the copy remains identical to accepted financial-v3, including compact rounding, attribution and exact evidence preservation under reduced ambient Decimal precision. County pending bills keep financial-v3 and the actual Loan→Entity slug/day anchor.

Pinned factual-v1, financial-v2/v3, report-v1/v2 and catalogue-v1/v2 text replay against actual accepted-base modules. Legacy destinations remain the reviewed canonical application destination; county financial-v3 retains the county/day link. Version-selected legacy policy scope hashes match the accepted implementation. New copy does not inherit an old style scope. Unsupported/foreign version names, booleans and integers cannot choose a destination or silently choose a copy style. Saved metadata keeps exact JSON types and required identifiers.

The real owned national writer is executed through baseline then changed qualified facts and neutral-report backfill. It saves financial-v4 and report-v3 drafts as `pending_review`, with current authority and original source evidence. Both use the exact qualified publisher URL; financial attestation remains required. Actual private admin HTTP GETs return the saved DTOs and `private, no-store`. No publication or delivery target is created by this source-to-draft fixture. Changing the actual retained source URL/checksum invalidates current generated-revision verification.

`national-documents.json` contains the actual saved HTTP DTOs. Those unchanged responses run through the merged UI detail decoder/query hooks/queue preview and display the exact saved copy and source URL while the actual default status says publishing paused, worker unavailable and no registered adapters. No preview invokes a post/patch command.

Neutral report copy remains dated and attributed without invented financial claims. Catalogue text explicitly distinguishes catalogue day from an unstated publication day and retains human review. References and original evidence are not replaced by the new user-facing destination. The fixtures do not prove that a live publisher contains these facts: all PDFs, HTTP responses, qualified cells, jobs and source-mode metadata are closed owned test material.

### Actual policy replay and hostile receipts

Three fixtures execute the real qualified county-report writer, synthetic human outcome, operating evidence and version-bound snapshot for recorded report-v1, v2 and v3. Each actual worker gate, repository gate and candidate gate passes on the correct recorded text/link/version after the new default is restored.

Opposite-version scope/metadata refuses with `SOURCE_SCOPE_CHANGED`. Edited text **and wrong-version link** refuse with `GENERATED_COPY_EDITED`, even when the document/evidence hash is recomputed consistently. Boolean/float/null metadata and foreign source receipts refuse with `EVIDENCE_INTEGRITY_FAILED`. Gate calls do not change post/revision/publication/target counts. Exact results are in `policy-report-availability-v1.json`, `policy-report-availability-v2.json` and `policy-report-availability-v3.json`.

The policy setup contains deliberately synthetic human-published-outcome and queued-publication rows in the disposable fixture so positive gates can be tested. No provider, worker process or scheduler publishes them; they are not rollout or operational evidence.

### Closed defaults, absence and errors

Actual empty private status HTTP reports publishing/automatic approval/scheduling/publishing/generation/media upload false, no adapters, no queue and worker unavailable. It creates no control or worker records. Missing scan, stale and future worker receipts do not become healthy; stopped remains stopped. Status failure stays an explicit private error with safe message and no diagnostic canary; unauthenticated status cannot expose private data.

With no hook environment, financial and report paths stop before any database factory/source read. Native financial admission also stays closed for absent/false/invalid values unless exactly enabled. The default native runtime creates no registration/transport, and the default supervisor executes only the web command; a poisoned child-construction path proves it spawns no worker. These are **closed-default execution proofs**, not inspection of production environment variables or authorization to activate them.

The UI additionally holds loading/error publishing status unknown with controls disabled. Retained executable controls cover wrong post/revision/shape, late actor results, revision advancement, account overrides, unsafe link inertness, date-specific cache separation, malformed quantities/reader notes, zero versus absence, source/date/county binding and anchor focus. Previously captured owned county/public receipt fixtures are copied unchanged for these retained checks; the national DTOs are freshly generated by this candidate's real writer/API.

UI interaction is JSDOM/component execution. It does not certify physical keyboard/screen-reader behavior, browser paint/contrast/reflow, all admin workflows or WCAG conformance. No browser tab or viewport was used or changed.

## Resolved findings

| Severity | Exact reproduction on frozen candidate1 | Final repair and proof |
|---|---|---|
| **P3, internal helper contract** | `backend/social/generation/social_copy.py:31` accepts an unknown/non-string or foreign family `version`; `render_social(report, version='invented-v99')` returns normal report text. Five independent cases reproduce unknown/bool/int/factual/catalogue tags on ordinary report input. | Candidate3 explicitly validates string version and source family at lines34–38, also refusing native financial evidence passed as factual-v2. All six direct controls pass. |
| **P3, internal helper contract** | `backend/social/generation/destination.py:8` skips entry revalidation. Model-copy schema99, bool/Decimal amount and a `javascript:alert(1)` source URL return a destination; the last returns that unsafe string. | Candidate3 line10 revalidates Python-mode source data, preserving strict input types. Four unchanged hostile controls pass. |

`backend-1b.txt` retains **nine desired failures and 76 passing pipeline/default/policy controls**. The normal pipeline already validated before these helpers, and no externally reachable authorization bypass or saved unsafe link is claimed. Candidate3 closes the direct helper seam. The added financial-as-factual control is also green in the final run.

## Replay and cleanup

```sh
sh /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-standards-review/prepare-pg.sh
sh /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-standards-review/run-backend4.sh
sh /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-standards-review/run-ui.sh
docker stop combined-release-standards-pg
```

For the exact old helper failures, after setup run:

```sh
sh /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-standards-review/run-backend.sh -k 'direct_social_helper_refuses or direct_destination_helper_refuses'
```

This intentionally fails on candidate1. The final helper-only replay substitutes `run-backend4.sh` and passes. The separate author check is `sh /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/combined-release-standards-review/run-author-test4.sh`. The backend scripts forward pytest arguments.

PostgreSQL17 is uniquely named `combined-release-standards-pg`, network none, CPU1/memory1GiB/PIDs256 and a 512MiB disposable tmpfs. Port55412 exists only inside its namespace; no host port is published. The guarded database is `b83_social_test` at Alembic `a756b20a0001`. Private mode0600 env files hold generated fixture credentials; none are printed. Test containers share only this network-none namespace with CPU1/memory2GiB/PIDs256, readonly frozen code and writable external evidence. Backend image: `admin-redesign-python-runtime:local`. Frontend image: `admin-redesign-node-tools:local`, network none, same caps, readonly locked dependency volume and readonly Git metadata.

Setup mistakes are preserved rather than classified as product defects: the first verifier assumed an older flat manifest schema; four initial typed native-report fixtures used an unsupported fragment/query; four heartbeat fixtures omitted required deployment/start fields. External fixtures were corrected to the actual contracts. The initial Unicode Git inventory quoting issue was also corrected. These failures are retained in `manifest-schema-note.txt` and `backend-1.txt`; final executable results contain no setup failure. No accepted-baseline witness gate was weakened.

`receipt-hashes.json` pins scripts, independent probes, accepted-base modules, manifests/provenance receipts and final outputs. The final candidate4 manifest checks before and after its author test have zero mismatches. The owned PostgreSQL fixture was stopped and removed; `cleanup.txt` records its exact name. Root `admin-redesign-pg`, other fixtures, dirty worktrees, production drafts and hosted environments were untouched. No commit, hosted run, paid call, upload, provider connection, publication or production mutation occurred.

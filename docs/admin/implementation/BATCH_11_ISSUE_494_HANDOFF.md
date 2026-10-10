# Batch 11 dependency tooling handoff: issue 494

This lane supplies a bounded local repair for the actual locked braces and sprintf tooling callers. It retains the published package versions and the two audit advisory roots. **Issue #494 remains OPEN; coordinator acceptance and any residual-risk decision are pending.** This draft lane result is separate from integrated, hosted and production acceptance. Production remains #583.

## Measured source and ownership

Accepted predecessor: `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`, tree `9d0061928c16d173859f98cb6daa5f2f591b257c`. The published SPEC SHA256 is `80c2fb7c6741d43798f49555733655330f412d368e16d3c3983c8f4e0abbcd42`. The seven implementation paths were committed as `be1df5f3289d40a52703295a8a68efc054121662`, tree `e6e3bc020698e81312b8fb5b85c76e56f8f057d7`.

Most author platform receipts measured the accepted predecessor plus the recorded uncommitted seven-file delta. Their file hashes correspond to the implementation commit; their recorded HEAD/tree are not reassigned to that commit. Independent Standards and Spec controls measured clean `be1df5f`. Later publication checks describe historical packet integrity only. Exact final local/remote identity, draft PR, final artifact rechecks and cleanup live in a separate append-only external postcommit binder.

Owned worktree: `/Users/roger/.codex/worktrees/batch11-dependency-compatibility/audit_app`, branch `codex/batch11-dependency-compatibility`. External original captures: `/Users/roger/.codex/visualizations/2026/10/10/01a12626-7088-7411-8c73-aea89f48b5e1/batch11-494`. UI13033 and inert API18033 were the assigned endpoints. No database was needed. Linux used an exact named owned container without published ports or shared volumes. Worktree and evidence are retained for review.

No template/style/navigation hunk changed. The append-only coordinator request reports an empty overlap inventory; a request is not approval. Shared SPEC/skills and sibling source were not imported or edited. Accepted read-only test prerequisites were copied into the Linux fixture when existing controls required them.

The primary was intended to remain read-only. One command lacking an explicit workdir created a new untracked installer there. Its exact owned bytes were copied to this worktree, then only that exact untracked file was removed. The original bytes and `primary-recovery.json` are retained. Readback preserved all 20 pre-existing tracked modifications and unrelated untracked files. This is an actual isolation mistake, not a claim that the primary was never written.

## Repair and install contract

`frontend/scripts/apply-tooling-repairs.cjs` applies ten reviewed source/helper/distribution/map repairs. `tooling-repairs.json` binds the complete 27-file final inventories of braces3.0.3 and sprintf-js1.0.3, including package metadata, entrypoints and unchanged files. All 901 existing lock records and 173 production records equal the accepted predecessor. The only lock metadata delta is the root install-script flag; no dependency range/version/override changed.

The installer checks every root/nested locked copy before mutation, refuses unknown bytes, changed exports, missing/unexpected files, incompatible versions, absolute/traversal paths and package/parent/file symlinks, including dangling links. Exclusive lock and temporary creation, atomic per-file rename, readback and final verification protect publication. Existing lock/temp collisions are preserved. The whole plan is validated first; a later filesystem failure can leave a partially repaired install, which must be reinstalled or completed and checked. This is not a hostile-filesystem sandbox or a transactional multi-file rollback.

braces parsing rejects brace/parenthesis depth above64. Recursive AST traversal, parent chains, flattening and nested append arrays reject above128 with `ERR_BRACES_DEPTH`; an option cannot relax the ceilings. sprintf snapshots conversion and precision before callbacks/property access, validates numeric e/f precision0–100 and g1–100, and uses those captured values for the native operations. Invalid precision raises `ERR_SPRINTF_PRECISION` rather than the native precision RangeError. Distributed minified code and both maps are repaired too; actual Next-bundled Terser regeneration matches all three files, and both maps contain the actual repaired source.

`postinstall` applies the repair. `pretest`, `prebuild`, `predev` and `prelint` check installed bytes; existing tooling-input verification is retained. An install using `--ignore-scripts` visibly fails the repair gate. Production omit-dev installation validates genuine target omission, while refusing links presented as absence. The pruned runtime fixture now carries the actual install script/manifest, uses separate empty npm configurations and an owned home, and invokes the actual npm CLI through the selected Node runtime.

The reviewed caller inventory is Tailwind/PostCSS and Next ESLint → fast-glob → micromatch → braces, and NYC configuration → js-yaml → argparse → sprintf. Real declared caller resolution is exercised. No public application request pattern/format caller was found in the reviewed source search; that observation does not prove universal caller trust. The existing trusted tooling-input guard remains necessary.

This local patch is a maintenance obligation. Locked-byte drift deliberately fails installation and requires a fresh reviewed inventory/patch or supported replacement. It does not advertise a fictitious patched version or certify complete remediation of every advisory behavior. Fixed ceilings reject formerly accepted unusually deep inputs. A supported migration/replacement remains the preferred complete issue outcome; the accepted Batch10 configuration-only Tailwind attempt failed real CSS compilation, while the broader official migration required107 templates and explicit style ownership. This lane does not reuse that template candidate.

## Actual platform results

macOS arm64 ran Node22.19.0/npm11.6.0. Linux x64 ran Node22.23.3/npm10.9.9 in Docker Desktop arm64 emulation, image `node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`. Emulated execution is not native Linux equivalence. Environments excluded inherited credentials/dotenv/provider endpoints; build/preview used only inert local URLs and an inert anonymous placeholder, not unit-test authentication.

| Control | macOS | Emulated Linux |
| --- | --- | --- |
| Final committed repair tests | 40 behavior +21 installer, all pass | Same61, all pass |
| Full original frontend cohort | 147 suites;2,077 pass;1 existing pending;0 fail | Same |
| Dependency boundaries + fresh production runtime | 106+9 pass;0 skips | Same after real Git prerequisite installation |
| Production build, lint/types and tooling CSS | Pass | Pass |
| Native CPU/model, Sharp decode and real ZIP | Pass | Pass |
| Unchanged actual embedding builder | 264×384 finite vectors, exact article identity/order | Same |
| Actual preview browser/fallback/WASM | Two queries in each real mode; no page errors/unexpected transport | Same |
| Production audit | 0 entries, exit0 | 0 entries, exit0 |
| Full audit | 26 entries:7 high/19 moderate; exit1 | 27 entries:8 high/19 moderate; exit1 |

The existing pending test is `BudgetTab.debtAbsence`: its mounted PostgreSQL HTTP capture prerequisite (`FINANCIAL_ABSENCE_HTTP_CAPTURE_DIR`) is absent. It was not weakened, faked or newly skipped. Counts distinguish cases, suites, repeats and review controls; repeated runs are not added into unique product acceptance totals.

The native checks executed Transformers4.3.1/ONNX Runtime1.30.0 CPU inference using model `Xenova/all-MiniLM-L6-v2` revision `751bff37182d3f1213fa05d7196b954e230abad9`, Sharp0.35.5 SVG/PNG/WebP through both declared callers, and AdmZip0.6.1 extraction. Article142 committed-vector cosine was0.99929648 on macOS and0.99597021 on emulated Linux against the existing0.99 floor. The unchanged builder also executed an actual CPU Identity control, repeatable384-dimensional inference, and wrote405,504 finite bytes with normalized vectors and exact264-article identity. Those outputs are evidence fixtures; production embeddings were not regenerated.

The real unchanged `tests/batch7DependencyBrowser.cjs` executed fallback and actual WASM searches for presidential terms and health care. Top semantic articles were142 and43; fallback ranking actually differed. Preview CSS was fetched from the actual server with200/type/hash checks. Full generated CSS equals the accepted baseline byte-for-byte, SHA256 `c9565032641e960d1d0cc18de94b0694d24ac92ba83a108945fd355b6a92a336`. The original323-case Chromium suite was collected only; it was not executed for this lane. These samples do not supply integrated navigation/visual acceptance.

**Graph limitation:** final macOS and Linux `npm ls --all --include=dev --include=optional --json` returned0 but reported two optional locked entries as extraneous: `@emnapi/runtime`1.11.3 and `@img/sharp-wasm32`0.35.5. A further clean reinstall reproduced them; baseline graph output has no such diagnostics. No invalid version/range was reported in the final candidate graph. This is not an unqualified clean graph result. Earlier transient invalid pretty-format output and both optional diagnostics are retained; no force override or guessed graph cleanup was applied.

Fresh registry reads still report braces3.0.3 and sprintf-js1.1.3 as latest releases. [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [sprintf advisory](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) have no patched release. npm audit is version-based and still reports their propagation entries after local repair. A passing inherited security policy is not a risk exception or complete issue acceptance.

## Independent axes and evidence

The [Standards report](batch11-issue-494-evidence/STANDARDS_REVIEW.md) records zero documented-standard violations and zero actionable heuristic smells at the implementation commit. It independently passed61 committed tests plus258 distinct additional controls (including three real minifier regenerations). Its publication review then found incomplete error/environment schema checks in the draft verifier. Original reproductions, original verifier bytes and later refusal controls are preserved rather than reassigned to a new producer.

The [Spec report](batch11-issue-494-evidence/SPEC_REVIEW.md) records zero scoped implementation defects,133 independent passing controls and one acknowledged complete-issue acceptance gap. The [adversarial report](batch11-issue-494-evidence/ADVERSARIAL_REVIEW.md) records551 unique passing controls after fixing four original defects and the distributed-entry gap. These local axes do not substitute for coordinator acceptance or platform/audit evidence.

The [packet protocol](batch11-issue-494-evidence/README.md) describes the portable archive, exact original producers and raw streams, integrity verifier, malformed-record controls, source/hash binding and replay prerequisites. Verification always returns `current_checkout_acceptance:false` and `issue_494:OPEN_UNRESOLVED`. It proves retained bytes and declared capture consistency, not receipt authenticity, current checkout behavior or future acceptance. Final artifact rechecks and final remote identity are external addenda to avoid self-referential commit/hash rewriting.

Important retained failures: initial npm/PATH/config setup failures; an overlength baseline red fixture and an incorrect valid-format expectation (both withdrawn); the genuine installer traversal red; six genuine early adversarial regressions; the minified sprintf residual; a schema1 installer/schema2 manifest mismatch after the primary recovery; missing accepted Linux seed/helper fixture imports; missing actual Git in the container; the old optional-package/pretty-format diagnostics; reviewer-only syntax/fixture mistakes; and the draft verifier’s missing/misleading environment controls. Corrected final runs retain the same product assertions and actual dependencies. No failing receipt is relabeled green. The final same-fixture original baseline was5 pass/35 fail; the repaired behavior fixture was40 pass, plus21 installer cases.

## Coordinator handoff

The all-state issue census used all seven API pages:617 issue/PR records,308 issues,15 open. Existing #494 owns this dependency work; no duplicate ticket was created. Actual issue body/comments remain open and unresolved. Repository Actions readback is disabled; no workflow was enabled or executed, no merge/production operation occurred, and no paid bot review was requested. The parent coordinator owns hosted CI, integrated acceptance, final review, shared skill changes and issue dispositions.

Assigned preview process groups/listeners were checked absent after both platform previews. Final exact owned-container removal/readback is recorded in the external binder. No broad process/Docker cleanup is permitted. [Local proposed lessons](batch11-issue-494-evidence/LESSONS.md) are suggestions only; shared skill files were not edited.

Next acceptance work is an owner-reviewed supported Tailwind/PostCSS and Next glob replacement, supported NYC/argparse/sprintf remediation, resolution of candidate optional graph diagnostics, and fresh native-platform/full browser/integrated/hosted evidence. Any shared style/navigation changes require accepted owner HEAD/tree and coordinator-approved integration. No exception or approval is inferred from this draft.

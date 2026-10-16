> Historical review record from the original investigation. Its absolute commands, reviewed draft hashes and cleanup statements describe that run only. The original generator bytes and artifacts are mapped in `../HISTORICAL_ARTIFACTS.json`.
>
> Current supported replay: `python3 -I <packet>/portable-replay.py spec --baseline <installed baseline frontend> --candidate <installed candidate frontend> --output <fresh external directory>`. Prepare both roots using `../README.md`; current replay writes external receipts and cleans owned temporary fixtures/cache even on errors. Do not run the historical absolute commands below.

# Independent executable specification review

Reviewer scope: dependencies lane, 2026-10-16. Read COORDINATION.md and adversarial-verify, claims-need-receipts, dependency-auditor skills. No app/candidate edits; all reviewer writes are in this directory. No install, browser, service, hosted Actions, account mutation, or paid review. Review was executed under Node v22.19.0, darwin arm64.

## Disposition

The **narrow docs-only blocked-remediation conclusion is supported**: the tested argparse override is not a shippable manifest/lock-only change with the existing repair contract. This review does not establish that every compatible remediation is impossible. No final narrative draft document existed when inspected; only the untracked evidence directory was present in the checkout. Recheck the finished document for the limits and findings below before claiming final-head review.

1. **P1 if shipped: mandatory install/repair contract rejects removal.** Candidate lock has argparse 2.0.1 and no sprintf-js; baseline lock has nested argparse 1.0.10 and sprintf-js 1.0.3. Running the unchanged `planRepairs` against a private fixture with the candidate lock and known valid baseline repaired braces produced `tooling repair: missing locked sprintf-js` in both normal and production check modes. `blocker.cjs` executed exit 0, where success means both expected failures were observed. Source: frontend/scripts/apply-tooling-repairs.cjs:82 fixes the package inventory at two, :89 restricts names, :104 requires each locked package; frontend/package.json:26 invokes repairs at postinstall and :9 checks repairs at prebuild. The actual candidate's check first rejects unpatched braces because failed install left its tree unrepaired; the private fixture removes that earlier failure to independently reach and confirm the missing-lock blocker. No shared files were repaired or bypassed.
2. **P2 compatibility limit: `js-yaml --version` silently loses its output.** The real NYC transitive js-yaml 3.15.2 CLI under argparse 1.0.10 exits 0 and prints `3.15.2\n`. Under candidate argparse 2.0.1 it exits 0 with empty stdout AND stderr. This was executed twice, independently of the author's probe, and is retained in results.json and version-confirmation.json. A future proposal that updates only repair contracts must not claim complete CLI compatibility. It must explicitly resolve or accept this observed interface change. Valid CLI conversion paths also emit argparse deprecation warnings under the candidate; help capitalization and unknown-argument diagnostic formatting/output stream differ.
3. **Retained observed functionality:** both real `@istanbuljs/load-nyc-config` installations resolved valid YAML and YAML inheritance. Both rejected empty, null, malformed YAML, nonstring extends, missing extends, circular extends, and explicitly absent config. The real js-yaml CLI retained data stdout and exit codes on stdin YAML, stdin JSON, empty stdin, explicit file, multiple documents, and deprecated `--to-json`; both rejected unknown options and missing files with exit 2, and malformed compact/trace inputs with exit 1. These are bounded samples, not universal compatibility proof.

## Executed commands and receipts

Working tree inspected: `/Users/roger/.codex/worktrees/compatible-dependencies/audit_app`; `git rev-parse HEAD` returned `3f3b1f1981b93c3317e204defbd235121c1df084`. Final reviewer `git diff --stat` was empty; `git status --short` showed only author's `?? docs/admin/implementation/batch14-dependencies-evidence/`.

Run from any cwd:

```sh
node /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/ENGINEERING_BATCH_14/dependencies/spec-review/review.cjs
node /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/ENGINEERING_BATCH_14/dependencies/spec-review/blocker.cjs
```

Both commands exited 0. First command independently executes nine NYC config cases and twelve CLI cases for each root, plus direct read-only repair checks; full outputs, CLI stderr and source hashes are in results.json. Second command asserts both missing-lock failures; complete output is in blocker-results.json. These are reviewer harness success codes, not candidate installation success codes.

Version confirmation used `spawnSync(process.execPath, [actualResolvedYamlCli, '--version'], {encoding:'utf8'})` for each root; the exact selected CLI resolves through the actual `@istanbuljs/load-nyc-config` module, not a globally installed js-yaml. Complete output is version-confirmation.json. The executable harness records selected package versions through that same resolution chain.

| Source | baseline SHA256 | candidate SHA256 |
| --- | --- | --- |
| package.json | a5c78d7d9e3a18ef1cb0be64eb1302d32e141ed8db0b603fa8050dda45bc7d92 | 5a6a00d523e19a1d95af7b55c0967349008825505e541e2ae75b9140b48c4ad5 |
| package-lock.json | 46569a23bd8d750b57e2d0dc44b0ddf6c8498a27c22ea82d0a8e5c80b88858dc | fda6befb45060e569b869902e165d8cd47f2dd0d0e19048ad968f7f8715e2d37 |
| scripts/apply-tooling-repairs.cjs | acd61ee77794572624afa1cfdb030ca80bf482148a3b4a213681e1bc453956fa | acd61ee77794572624afa1cfdb030ca80bf482148a3b4a213681e1bc453956fa |

Baseline root: `/Users/roger/.codex/worktrees/compatible-dependencies/audit_app/frontend`.
Candidate root: sibling `../argparse2-candidate/frontend`, frozen hashes above. No assertion about later candidate changes is implied.

## Necessary future proposal and limits

A future sprintf-removal patch needs an explicitly authorized repair-contract migration: preserve fail-closed detection of missing required patches/packages, retain reviewed braces checks, intentionally retire sprintf inventory/patch entries only after proving it absent from the supported lock graph, update tests that directly import sprintf, and test clean script-enabled installs and omission modes. Current behavior tests import sprintf at frontend/scripts/tooling-repair-behavior.test.cjs:50, :91, :108, :119. Changing those contracts is outside this lane's present ownership. The CLI version-output regression is a separate acceptance issue for that follow-up, even if YAML consumers themselves retain the sampled results.

Not run: full reinstall (explicit reviewer constraint), frontend lint/type/build/Jest, native imports or embedding/model behavior, all supported Node versions, production omission install, browser checks, hosted CI, current live advisory fetch. Current advisory severity/reachability claims were not independently refreshed by this reviewer; this review establishes local compatibility/blocker facts only. The author's clean-install failure receipt is corroborating evidence, not relabeled as reviewer execution. No claim that all security findings are fixed, or that the current production graph equals either local root.

Disposable synthetic config directories `baseline/`, `candidate/` and the small `blocker-fixture/` were removed after final replay. Retained scripts recreate only their own disposable fixtures when replayed. No processes, locks, ports, services, or shared fixtures were left running or changed.

## Final narrative and assertion review

Subsequently read the finished `docs/admin/implementation/BATCH_14_DEPENDENCIES_HANDOFF.md`, evidence `README.md`, `cli-version.test.cjs`, and candidate patch headers. The handoff now explicitly rejects the CLI version regression, distinguishes the candidate probe's earlier unpatched-braces failure from clean-install missing-lock failure, treats exit 0 of the diagnostic probe as observations rather than acceptance, and limits its conclusion to the tested candidate/current ownership. No additional actionable overclaim found in the final reviewed text. This is approval of the documentation/investigation disposition, not approval to ship the override or bypass repairs.

Executed the new assertion fixture from the isolated checkout with these exact commands:

```sh
BATCH14_FRONTEND_ROOT='/Users/roger/.codex/worktrees/compatible-dependencies/audit_app/frontend' node --test docs/admin/implementation/batch14-dependencies-evidence/cli-version.test.cjs
BATCH14_FRONTEND_ROOT='/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/ENGINEERING_BATCH_14/dependencies/spec-review/../argparse2-candidate/frontend' node --test docs/admin/implementation/batch14-dependencies-evidence/cli-version.test.cjs
```

Baseline: exit 0, 1 pass, 0 fail, 0 skips. Candidate: exit 1, 0 pass, 1 fail, 0 skips; `--version must print its package version`, actual empty string versus expected `3.15.2\n`. Raw TAP retained as final-baseline.txt and final-candidate.txt. The candidate fixture's loop stops at its first failed assertion, so it does not independently execute `-v` on candidate. Reviewer separately executed both `--version` and `-v` on both resolved real CLIs with `spawnSync` and retained both-version-flags.json: baseline output `3.15.2\n`, candidate empty output, status 0 for all four calls. The handoff's claim that independent probes cover both flags is therefore supported.

Reviewed final file SHA256 (also retained as final-files.json):

- BATCH_14_DEPENDENCIES_HANDOFF.md: `c5c8596c880e360be14a6c43b311d4eb21aebeb16558c5c9a4c4504fd185ee8d`
- batch14-dependencies-evidence/README.md: `932944edcda76338dd54dee166447a10a1b9e93174a738731fb9f548043a1173`
- batch14-dependencies-evidence/cli-version.test.cjs: `d27c5b82f941b7f3cceb9bb8d3e73e179590fac312a5edf413d1d70430586ef5`

Later review-disposition/PR metadata additions are not implied by these exact hashes. README installation replay commands were read for consistency but not reinstalled by this reviewer, as explicitly constrained. Source graph/runtime coverage limits above still apply.

# Batch 9 residual dependency handoff — 2026-10-09

The scoped implementation and local verification are complete. Standard tooling
commands now reject unreviewed Tailwind content patterns and effective Next lint
root globs before invoking their vulnerable callers. The measured Jest graph
rejects malformed package identities, normalized version aliases and unsafe
numeric prereleases. **Complete acceptance of [#494](https://github.com/Rodgers31/audit_app/issues/494)
is not met:** both unpatched advisory roots remain, full audits still fail, and
no residual-risk exception is assumed. Keep the issue open and the PR draft.

## Coordinator review amendments

The author history below is preserved. Review reproduced a false rejection for
a child that never reached the graph assertion, premature JSON from spreading
an unawaited Promise, and a host-specific npm validator import. The Promise
case exited nonzero on the tested Node runtime; the review's exit-zero mechanism
was not reproduced, but the premature success-shaped output was real.

The accepted controls now require the intended assertion/guard diagnostic and
exact graph-test execution, await asynchronous validation, and resolve npm and
the validator from the owned installation. Null/array/syntax-invalid Tailwind
and unreadable ESLint inputs receive explicit contract diagnostics. Their tests
use installed modules so unrelated missing-dependency setup cannot satisfy the
negative control. The complete baseline fixture now includes its manifest and
provides the actual npm CLI to its child.

The original summary/archive stays unchanged. A new read-only portable archive
verifier validates historical bytes and explicitly labels their source identity;
`build-evidence.cjs --verify-existing` invokes it. New recorders capture source
before execution and refuse a success verdict after source/generator/HEAD
changes. Current controls and historical diagnostics are distinguished in the
evidence README. These repairs do not remove either residual advisory root or
meet complete #494 acceptance.

## Source, ownership and resume point

Base: verified main `672c5c011ce57dc41551f5fbc642bc4e69134c43`. Product head:
`94f350ffc93bec4433617b04bf7c94bad4828345`, branch
`codex/batch9-residual-dependencies`, targeting `main`. This delivery has no
dependency on held #584 and contains no sibling delivery. The clean initial
managed worktree was `/Users/roger/.codex/worktrees/a486/audit_app`; remote main
matched the pinned base before implementation. The dirty primary checkout and
its environments/installations were not used or modified.

Changed product files are `frontend/package.json`, `frontend/package-lock.json`,
`frontend/README.md`, and the four dependency scripts
`jest-dependency-boundary.test.cjs`, `tooling-input-boundary.test.cjs`,
`verify-tooling-inputs.cjs`, `verify-dependency-tooling.cjs`. The only other
owned changes are this handoff and `batch9-dependencies-evidence/`. No bootstrap,
ETL, seeding, models, migrations, financial definitions/data, PDF workflow pins,
search implementation, embeddings, styling configuration or publication policy
changed.

[summary.json](batch9-dependencies-evidence/summary.json) binds the exact product
head, all seven product hashes, all command identities and the archive hash.
Subsequent delivery commits contain documentation/evidence only. A committed
file cannot embed its own future Git hash; the exact final delivery head and PR
URL are recorded in the final author report and external `delivery.json` under
`/Users/roger/.codex/visualizations/2026/10/09/01a1220d-747e-7c50-bf38-369c8db7b3a7/batch9-dependencies/`.
Resume by verifying that remote branch head, the product hashes in the summary,
and the PR's draft/base state. Coordinator acceptance, review of any new remote
findings, merge and operational checks remain separate gates.

## Investigation and selected control

The issue and its latest comments were read before implementation and again
before publication. A paginated open-and-closed issue inventory is retained as
`issue-dedup.*` in the raw archive. Existing #494 tracks all remaining dependency
work; no new follow-up issue was needed, and no parent issue was closed.

Fresh registry and primary advisory observations still show braces 3.0.3 and
sprintf-js 1.1.3 as their latest releases, with no patched version in
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and
[GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c).
`registry-*` and `advisory-*` receipts retain the actual observations. Supported
Tailwind v3 remains 3.4.19; current Next lint 16.4.0 still declares fast-glob;
current NYC loader 1.1.0 still declares js-yaml 3. The previous owned Tailwind v4
experiment failed the retained PostCSS plugin contract; its historical evidence
is in [the Batch 8 handoff](BATCH_8_DEPENDENCIES_HANDOFF.md). No supported removal
of an unused root was demonstrated. This author did not repeat that migration,
apply forced fixes, override native/YAML major versions or downgrade framework
behavior to change the audit verdict.

`verify-tooling-inputs.cjs` retains exactly the existing four Tailwind source
patterns. Each has one five-extension brace group, instead of accepting arbitrary
depth/ranges/source scope. For Next lint it resolves ESLint's effective settings
for the actual default directories/extensions and a root probe, including local
extends, overrides, alternate config and descendant config. The final positive
run checks 315 configurations. Custom Next `rootDir` globs are rejected. Standard
`predev`, `prebuild` and `prelint` invoke this check; the CSS compatibility verifier
awaits it before emitting success. Existing application discovery and CSS
configuration remain unchanged.

These controls cover the retained configured entry paths, not a sandbox around
executable configuration, direct custom CLI/configuration, different Next lint
directory settings, or changes made after a development watcher has started.
Future changes to those contracts need their own caller review. The upstream
braces library remains vulnerable. Actual caller controls resolved Tailwind's
and Next lint's declared fast-glob modules and reproduced `RangeError` with an
8,003-character, 4,000-level pattern. This demonstrates the primitive/caller
failure; it does not demonstrate a public request exploit.

The report boundary uses Sharp's declared semver parser, preserves exact
prerelease/build spelling, and rejects numeric prereleases outside the safe
integer range. npm's `validate-npm-package-name` 6.0.2 supplies the identity
grammar instead of repeated ad hoc regex repairs. The measured graph retains
its lowercase naming contract and allows legitimate historical/builtin names.
The added validator is a pinned, dependency-free development package, with Node
`^18.17.0 || >=20.5.0`. That includes the existing advertised app contract
`^20.9.0 || ^22.0.0 || >=24.0.0`; current validator 8 requires newer Node minima
and was not selected. The engine-subset fixture now also checks this dependency.

All 901 existing non-root lock records, including all 173 production records
(the established non-`dev` definition), are unchanged. Only the root development
declaration and one new development record differ. There is no native, framework,
Jest or browser runtime resolution change. Actual installed inventory retains
Transformers 4.3.1, Sharp 0.35.5 for both callers, ONNX Node 1.30.0, installer
adm-zip 0.6.1 and ONNX Web 1.31.0-dev.20260914-8d85527a0. The library YAML load
path was executed; it does not invoke argparse's CLI formatting path. The actual
installed sprintf primitive still throws on 101 precision digits. No sprintf
remediation or universal format-caller safety claim is made.

## Executed verification

Raw command arrays, cwd, timestamps, source commit/tree/file hashes, observed
exits, runtime and output hashes are in
[raw-receipts.tar.gz](batch9-dependencies-evidence/raw-receipts.tar.gz). The
summary verifies each receipt's generating tool and raw-output hashes before
archiving, then reads its own provenance back from disk. Scripts needed to
reproduce controls are committed alongside the archive. Do not add overlapping
review/control counts to the application-test counts.

| Check | Actual result |
| --- | --- |
| Fresh engine-strict installs | macOS arm64 Node 22.19.0/npm 11.6.0 and pinned emulated Linux amd64 Node 22.23.3/npm 10.9.9 pass, including the final lock |
| Pinned Linux identity | `node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`; container runtime reports x86_64 |
| Full final frontend tests, each platform | 147 suites pass, 2,077 tests pass, one existing optional financial-forecast test skips; zero failures |
| Final dependency-boundary command, each platform | 30 Node controls plus nine runtime controls pass; zero failures/skips; actual query/discovery/CLI and real pruned image decode execute |
| Discovery | Baseline/final actual macOS discovery sets contain the same 147 suite paths; Node fixtures remain outside Jest |
| Full final production build, each platform | Pass, including lint/type build checks; API targets are inert loopback and expected connection-refused diagnostics are retained |
| Lint/types/tooling | Final macOS lint, standalone TypeScript and scoped-script lint pass; Linux build lint/types, repaired lint and actual CSS tooling pass |
| Local production preview | Actual npm/Next start serves `/learn` and built CSS at 200; owned process group stops and listener absence is verified |
| Actual installed trees | Final `npm ls --all --json` passes on both platforms; no peer problems reported |
| Production audit | Baseline/final macOS and final Linux report zero, exit 0 |
| Full audit | Baseline/final macOS 26 affected package entries, exit 1; final Linux 27, exit 1; same two advisory roots |

The final macOS root grouping is seven braces-propagation entries and 19
sprintf-propagation entries. Linux has eight braces entries and the same 19
sprintf entries: its extra entry is `@tailwindcss/typography` peer propagation.
The root count, affected package-entry count and affected installed-node count
are recorded separately in the summary. These are not independent demonstrated
exploits, and the full audit is not a passing acceptance gate.

Native image decoding runs through the existing pruned-runtime controls on both
platforms. Full native CPU inference, ZIP and browser WASM/fallback ranking were
not repeated: their dependency records and entry-source paths are unchanged.
Their prior exact-source receipts remain in Batch 7/8; they are historical
verification, not newly executed Batch 9 results. No minimum Node 20.9 or Node 24
execution is claimed. The advertised runtime contract is unchanged and the new
package's engine compatibility is measured by the subset test. No SQLAlchemy,
database or persistence change is in this lane.

## Red/green, review and dated supersession

The baseline observation channel was established by a real fresh install,
nonempty installed graph, nonempty discovery and full/production audit outputs.
The real Jest CLI intentional-failure control and actual malformed-report
children prove that an execution failure reaches the verdict.

`red-version-boundary` accepts `v30.5.2` on the pinned baseline and fails the new
expectation; `red-unsafe-prerelease` separately accepts
`30.5.2-9007199254740992` against the exact pinned guard bytes. Its matching
`green-unsafe-prerelease` makes the guard reject that report. The paired
`red-tooling-complete` uses the baseline verifier and the final 8,003-character
fixture: all three unsafe-config expectations fail because the verifier emits
CSS success. The candidate checks reject them. Independent review then
reproduced effective-config and npm-name holes on intermediate commits; the
default regression suite ships those cases, each observed red and green.

All independent reviews and raw controls remain intact:

- [Spec accepted review](batch9-dependencies-evidence/spec-accepted-review.md): invalid registry names rejected; no remaining scoped findings.
- [Standards accepted review](batch9-dependencies-evidence/standards-accepted-review.md): required JSDoc added; no remaining violations/actionable smells.
- [Behavior accepted review](batch9-dependencies-evidence/behavior-accepted-review.md): 80/80 independent controls match expectations; actual installed graph suite six passes, zero failures/skips; zero unresolved findings.

Valid intermediate findings were fixed rather than dismissed: root-only ESLint
checking missed effective inheritance/overrides/alternate/descendant settings;
non-object JSON could receive success; whitespace and then reserved/period
package names evaded the initial grammar. The recorded direct-CLI/watcher limit
remains deliberate and was not expanded into arbitrary executable-code isolation.

**2026-10-09 superseding record:** the Batch 8 semantic-version repair and early
Batch 9 regex/root-config checks did not establish the final strict report/input
boundary. The new rejected-input measurements supersede that interpretation,
not their historical graph/audit counts. Raw historical receipts and review text
are unchanged, and the older hashes identify the code actually tested then.

Unsuccessful controls are retained honestly. `red-tooling-replay` is a fixture
setup failure (omitted `.eslintrc.json`), corrected in `red-tooling-complete`.
`mac-lint` is a startup configuration failure (missing explicit public API URL),
corrected with scoped inert environment. `native-inventory` attempted Sharp's
unexported `package.json` subpath and failed; `native-inventory-complete` uses
actual npm tree measurement. The earliest deep-input fixture exceeded the
upstream length limit; the corrected 4,000-level caller reproduction is the
stack-exhaustion evidence. None of those setup/control failures proves acceptance.

## Remaining gates and reusable lessons

#494 still needs a compatible Tailwind/PostCSS migration or publisher fix,
supported Next lint glob replacement and NYC/js-yaml/argparse/sprintf remediation.
Production audit zero does not accept residual development/build exposure. No
new risk exception, source-scope expansion or policy weakening is proposed.

The five repository workflow definitions remain `disabled_manually` in the
read-only workflow-state receipt. Dynamic Copilot workflows being active is not
evidence that repository CI ran. No hosted execution, production inspection,
Actions setting change, deployment, paid review request or merge is claimed.
Coordinator owns those gates and final acceptance. If remote review threads or
body-only findings appear, fetch them with pagination, reproduce valid findings,
push the finished repair before replying with its pushed identity, resolve only
handled items and re-fetch. The publication-time remote review state is recorded
in the external delivery receipt and final author report.

The owned `batch9-dependencies-linux` container was removed and an exact-name
listing is empty. The preview listener is absent after process-group cleanup.
Owned caches, immutable evidence and this managed worktree remain for review;
no shared runtime was modified or pruned.

Reusable lessons, backed by the red/control receipts: inspect effective tool
configuration rather than one root file; use the ecosystem's identity grammar
rather than repeatedly patching a regex; distinguish safe numeric prereleases
from parser acceptance; and bind a successful compatibility verdict to the
actual caller inputs before replacing those inputs with a synthetic fixture.
These lessons are recorded here for coordinator consolidation, without changing
globally installed skills.

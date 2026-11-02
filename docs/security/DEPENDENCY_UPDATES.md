# Dependency update qualification

Queue schedules, grouping, PR limits, security-update activation and migration
are defined in the [dependency review queue policy](../operations/dependency-update-policy.md).
That policy supersedes this document's original 31 October 2026 five-queue
configuration. The reviewed configuration takes effect when it reaches the
default branch; inspect that branch and the recorded settings readbacks when
checking the live state. This document retains the dependency qualification,
source-bound repair, wheel, worker and no-new-cost requirements.

The native GitHub Dependabot configuration is `.github/dependabot.yml`.
The owner reviews and merges PRs manually. There is no auto-merge workflow,
custom updater, paid model/review integration, token, registry credential,
`pull_request_target` workflow, deploy trigger or elevated permission added.

## Queue policy and compatibility

Use the canonical policy for the two weekly routine queues and their separate
security groups. Routine groups include eligible minor/patch updates; major
migrations require deliberate review, and security fixes may require a major
version. Security updates use GitHub's separate PR budget and are not postponed
until the routine weekly slot. Repository alert and security-update settings
are independent of the YAML groups; their activation sequence and dated
observations belong to the canonical policy.

Grouped updates still require every applicable qualification below. A 0.x minor
change can break compatibility even when SemVer calls it minor. A shared PR does
not make independently resolved Python environments interchangeable, qualify a
new native/model/browser dependency, or bypass source-bound tooling repairs.
Existing proposals can occupy the lowered routine limits; follow the policy's
retained-inventory and selective-replacement procedure before retiring them.

## Authoritative files and coverage

Backend/ETL/fixture resolution uses root `.python-version` 3.12.16, matching the
tested serving Python line. Dependabot selects its available supported patch in
that line; the file does not pin production's floating image.

Backend scanning includes `requirements.txt`, `requirements-dev.txt`, and the
referenced `security-constraints.txt`. ETL uses `requirements.txt`. The worker
fixture's former `requirements.lock` is renamed to supported `requirements.txt`;
Docker still supplies it to the installer's fixed `/input/requirements.lock`.
The three actual preflight driver manifests are included, including hashed wheels.
Historical archived evidence is not an active install manifest and is not updated.

Python uses `versioning-strategy: increase` so a permitted newer version can raise
an application's floor rather than simply leaving a broad range untouched.
Existing upper compatibility bounds, hash coverage and linked requirements must
be reviewed in each resulting diff. Conflicting bounds may produce a resolver
failure instead of a PR. Do not widen them or bypass guards merely to make the
bot succeed. Worker updates require the separate qualification in its README.

The upstream Dependabot parser at commit
`85379652e4ef784fdd38bf4598b0b347832f805b` was actually executed against every pip
location. It discovers all three backend files, the 18 ETL declarations, 93
worker pins and all three preflight drivers. Its file fetcher follows local `-r`
and `-c` references and supports the root `.python-version`. The old standalone
`.lock` suffix is not a discovered requirements root; the rename removes that
blind spot. Config was checked against the Dependabot v2 schema and every path.
Actual npm manifest/lock updates and pip installs/pip check exercise the package
change mechanics. No hosted Dependabot run or generated bot PR is claimed before
the owner merges this configuration.

**npm override limit:** an executable review of the actual upstream npm manifest
updater reproduced a separate blind spot. Its subdependency helper updates a
plain `follow-redirects` override (positive control), but leaves version-selector
keys `glob@>=9 <14.0.2` and `minimatch@>=9 <11.0.1`, and nested `next.sharp`,
unchanged when supplied synthetic newer patches. That helper ran with transport/
type-annotation stubs; it is not a hosted job failure or a complete updater run.
Do not assume Dependabot can advance those exact pins. A maintainer must check
new advisories/releases for these paths, update the matching scoped/nested pins
with the lockfile, and rerun their caller/native acceptance. A bot resolution
failure is actionable, not evidence that no update is needed. Keep the scoped
legacy compatibility boundary; a blanket override would break real callers.
Source-bound repairs now cover braces, js-yaml, deepmerge, eslintrc and the
import/React/accessibility plugins. Parent changes need manual review of the
exact overrides, all repaired caller files and complete nested file inventories.
The lint migration's six parent-scoped minimatch pins and cache/remover pin must
advance together with their verified caller APIs. The install guard also pins
three actual CommonJS entry paths/hashes and checks package-root plus true source
requester resolutions. Preserve its canonical-root handling and three exact CLI
links; do not add generic exclusions or skip nested directories. The separate
YAML4 exception remains restricted to its exact reviewed path/version in both
inventory and installer. Inspect Dependabot job logs when a weekly check produces
no PR; silence alone is not a clean audit.

**Coverage limit:** npm security updates can repair supported transitive lockfile findings.
Unpinned Python transitives that appear only after resolution are not a complete,
immutable dependency graph in these range manifests. Constraints cover declared
floors, not every possible future resolution. Dependabot does not replace fresh
full-environment pip-audit/OSV checks. Every update PR still needs a clean complete
runtime/dev/ETL resolution and audit, including build/test packages. Installer
pins in Dockerfiles, OS packages, Node/CPython patches, OCR/Java/FFmpeg, browser
binaries and model assets require their separate runtime/platform maintenance.
There is no claim of weekly OS/native or whole-system vulnerability scanning.

## No-new-cost boundary and activation

Read-only checks on 31 October 2026 found this is a public repository, with only
the main protection ruleset and no Copilot review rule. The owner's personal
Copilot automatic review, review-new-pushes and draft-review controls are OFF;
CodeRabbit is absent from the installed GitHub Apps list. No reviewers or review
request automation are configured by Dependabot. Recheck these settings if an
integration is later installed or automatic review policy changes.

Render auto-deploy and PR previews are OFF. Vercel uses a paid elastic build
machine, so a successful old ignored-build status alone is insufficient cost
protection: `frontend/vercel.json` explicitly disables deployment for
`dependabot/**` and `codex/dependency-security-*`. Both npm and pip branch forms
were checked with minimatch and the official Vercel `git` schema fragment. Other
branches retain the existing project policy. Keep these exclusions and preview
holds in place. The initial official Vercel full schema has an unrelated invalid
experimental-services definition; instance validation and the used git fragment
are checked separately, not described as a clean upstream metaschema result.

GitHub's standard Dependabot jobs do not use included Actions minutes; larger
runners can incur charges. This public repository uses standard GitHub-hosted
Dependabot runners and adds no runner configuration. Downstream Actions, paid
reviews and previews are separate costs; existing CI/deploy workflows stay
`disabled_manually`. Scheduled ingestion and its approved source SHA are untouched.

Follow the canonical policy's activation and settings-verification sequence.
The configuration must reach main before its groups govern generated updates;
security-fix PR generation is a separate setting, enabled only after the reviewed
grouping and cost/preview protections are on the default branch. Alert enablement
and an initial empty inventory do not prove a completed vulnerability scan.
No paid check, extra hosted run or automatic merge follows from this policy.
The version updater can run while ordinary repository workflows are disabled.
Existing required checks still protect main; disabled checks do not grant a merge
bypass. Arrange approved validation through the existing review process.

## Review procedure and rollback

For each npm PR, run `npm ci --include=dev --include=optional`, `npm ls --all`, full
and production `npm audit --json`, dependency/tooling/runtime boundaries,
TypeScript, lint, full Jest and production build. Preserve source-bound tooling
repairs; a repair hash refusal is a real compatibility blocker. Native/model or
browser dependency changes also need real model inference/image decoding and
owned browser checks. Do not replace these with source-string assertions.

For each Python PR, install into fresh environments using the real manifests and
constraints, run pip check and exact resolved pip-audit/OSV queries, then affected
auth/parser/native/source tests in normal and true optimized modes where required.
For hashed preflight driver updates, inspect the complete hash diff before
merging. Dependabot can expand a hash set to additional wheels or source
distributions: reject that generated diff, or manually prune it to only the
explicitly reviewed CPython/platform wheel identities. Do not accept new hashes
merely because `pip --require-hashes` accepts them as alternatives. When the
package version changes, verify the new official wheel bytes and their hashes
for every previously qualified Python/platform combination; keep source
distributions and unqualified platforms excluded. Re-run the exact driver's
manifest identity and isolation controls after pruning. This applies to the
hashed `batch66/preflight-driver-requirements.txt` and
`batch80/github-driver-requirements.txt`; the separately un-hashed batch71 pin
does not confer the same wheel constraint. Rebuilding the worker image
requires its complete exact installer and unchanged confinement/capacity workload
qualification; a package-clean audit alone is insufficient. Keep production data,
source writers and worker/publishing/upload/financial opt-ins off during fixtures.

Use the existing human review and branch protections. The updater proposes
changes; it cannot approve, merge, deploy, publish, migrate, or enable a source.
For a rejected update, retain the failure and address its actual compatibility
problem; do not add blanket major/security ignores. The
[lint matcher migration](DEPENDENCY_MATCHER_MIGRATION_2026_10_31.md) removes legacy
minimatch/glob/rimraf while preserving all 54 configured rule settings and the
existing lint stack. The current raw full audit retains five low deepmerge
entries at its unchanged, locally repaired registry version; production is zero.
Issue 494 remains open. Optional future pattern configurations, including the
currently disabled import/no-internal-modules rule, need their own semantic
review. ESLint 8 remains deprecated and its eventual broader migration is
separate work. Every future update still needs fresh resolution, audit, complete
rule/config parity, caller/cache tests and source-bound repair verification.

To pause routine PR creation, set the affected `open-pull-requests-limit` to zero
in a reviewed configuration change. This does not disable advisory security
updates; their setting is separate. Reverting the consolidation restores its
preceding queue configuration rather than stopping all weekly checks. Existing
PRs remain for deliberate manual handling. To roll back a merged dependency update,
revert its manifests/lockfiles together and reinstall/rebuild the previous reviewed
graph; document reintroduced advisories. No application data migration is involved.

Primary references: [version updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-version-updates),
[options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference),
[security updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates),
[runner costs](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-on-actions),
[Vercel branch exclusions](https://vercel.com/docs/project-configuration/git-configuration).

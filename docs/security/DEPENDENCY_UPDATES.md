# Weekly dependency updates

The native GitHub Dependabot configuration is `.github/dependabot.yml`.
The owner reviews and merges PRs manually. There is no auto-merge workflow,
custom updater, paid model/review integration, token, registry credential,
`pull_request_target` workflow, deploy trigger or elevated permission added.

## Schedule and grouping

| Ecosystem/location | Monday, America/Chicago | Concurrent version PR cap |
|---|---|---|
| npm `/frontend` | 08:00 | 4 |
| pip `/backend` | 08:15 | 3 |
| pip `/etl` | 08:30 | 2 |
| pip `/tools/worker_host_fixture` | 08:45 | 2 |
| pip drivers `/docs/admin/batch66`, `batch71`, `batch80` | 09:00 | 1 shared update configuration |

These are target check times, not guaranteed PR delivery times. IANA timezone
handling follows Chicago daylight saving time. The first Monday after preparation
is **2 November 2026**. Backend/ETL/fixture resolution uses root `.python-version`
3.12.16, matching the tested serving Python line. Dependabot selects its available
supported patch in that line; the file does not pin production's floating image.

Next/eslint-config-next, React/types and Jest/types each have their own minor/patch
group. Native inference/image packages and ETL PDF/data packages group patches
only. Other ordinary libraries group minor/patch updates. The fixture groups
patches only; its minor and major changes remain individual. Major updates are
never included in these routine groups or blanket-ignored. A 0.x minor change
can break compatibility even when SemVer calls it minor: review it accordingly.
PR caps can leave a later group queued until earlier PRs are handled.

Groups apply to version updates. Advisory-triggered security updates remain
ungrouped and visible, with GitHub's separate fixed cap of ten security PRs.
A schedule does not postpone a security update until Monday. Security update
settings, dependency graph and alerts must be enabled independently; the observed
repository security-update setting is currently disabled and is unchanged here.

## Authoritative files and coverage

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

Activation is the owner's merge of the reviewed configuration to main, after the
remediation PR. This will allow weekly version PR creation; no hosted job is
started in this session. If desired, the owner can then enable dependency graph,
alerts and Dependabot security updates in Settings → Advanced Security, preserving
all cost/preview protections. Enabling security updates before these exclusions
reach main could create unprotected PRs, so it is deliberately not done here.
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
Hashed preflight driver updates must retain every qualified Python/platform wheel
hash and pass that preflight's isolation controls. Rebuilding the worker image
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
updates; their setting is separate. Revert the bot commit to remove weekly checks.
Existing PRs remain for manual handling. To roll back a merged dependency update,
revert its manifests/lockfiles together and reinstall/rebuild the previous reviewed
graph; document reintroduced advisories. No application data migration is involved.

Primary references: [version updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-version-updates),
[options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference),
[security updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates),
[runner costs](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-on-actions),
[Vercel branch exclusions](https://vercel.com/docs/project-configuration/git-configuration).

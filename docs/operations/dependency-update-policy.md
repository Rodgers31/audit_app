# Dependency review queues

Routine updates use two weekly queues in [Dependabot configuration](../../.github/dependabot.yml):

| Queue | Manifests | Schedule | Open routine PR limit |
| --- | --- | --- | --- |
| Frontend | `/frontend` | Monday, 08:00 America/Chicago | 1 |
| Python | `/backend`, `/etl`, `/tools/worker_host_fixture`, `/docs/admin/batch66`, `/docs/admin/batch71`, `/docs/admin/batch80` | Monday, 08:15 America/Chicago | 1 |

Each queue groups eligible minor and patch updates using a single wildcard group. That matching group is what consolidates the Python directories; listing several directories and setting a limit alone would not establish a global Python queue. The version-only allow filter keeps routine major upgrades from falling outside the group into individual PRs. Review and merge remain manual. No dependency versions, GitHub Actions workflows, paid reviews, services or application activation controls change with this configuration.

Security updates have separate `frontend-security` and `python-security` groups. Their eligibility is not limited to minor/patch versions. The routine `allow.update-types` filter applies only to version updates. Dependabot's separate, fixed security PR limit can exceed the two routine slots; do not suppress urgent fixes to meet a cosmetic PR count.

The Python entry monitors several independently resolved environments. Grouping and the open-PR budget do not prove that all incompatible manifests fit in one universal upgrade PR. Inspect the first ordinary run for directory coverage and waiting candidates. A stalled application upgrade must not leave maintenance environments unattended; review the update logs and adjust the queue structure deliberately if that happens. Do not set `group-by: dependency-name` for the weekly wildcard group: that requests a separate cross-directory group for each dependency.

Review major migrations separately during a monthly dependency inventory review, or sooner when required by a security fix. This policy adds no scheduled job or automation for that review. There is no global ignore rule or auto-merge.

Repository alerts and automatic security-fix PRs are separate GitHub settings; YAML groups do not enable them. The 2 November 2026 readback found both disabled. Alerts were then enabled using the existing repository administration access and verified by the alerts-state endpoint. Automatic security-fix PR generation stays disabled until these reviewed groups reach the default branch. At that point enable it and verify its actual enabled state and current alert inventory. An unreadable or still-populating inventory is unknown, not evidence of zero vulnerabilities. This uses native Dependabot; no paid scanning product or expanded authentication scope is required.

## Review and migration

1. Review the configuration PR using the ordinary complete-review process. Native Dependabot behavior is observed only after the configuration reaches the default branch; YAML parsing alone does not prove hosted grouping or dependency resolution.
2. Inventory the existing bot PRs, their changes and any security notices before changing their disposition. The initial inventory is twelve proposals, #871 through #882. None is accepted merely because the configuration changes.
3. After default-branch activation, inspect Dependabot's ordinary update logs. Existing proposals can consume the lowered limit and prevent a replacement from opening. If that happens, first retain their exact heads, patches and pending-version inventory, classify security and major changes, and prepare a reviewable manual replacement or explicit deferred inventory. Then retire only routine proposals deliberately superseded by the approved consolidation, with links to that replacement/inventory. Do not wait circularly for a generated replacement, assume closing will recreate the same version, or suppress urgent security fixes. Dependency merging and selective retirement remain separate reviewed actions; this configuration change does neither.
4. For each generated batch, inspect resolved versions/lockfiles, compatibility and current advisories; execute the affected frontend or Python checks locally before manual review/merge. A successful dependency PR is not production activation authority.
5. Confirm all seven manifest directories remain covered and urgent security updates are not waiting behind a routine queue. Preserve the existing major-upgrade inventory until those migrations are deliberately reviewed.

The initial inventory includes the separate Gunicorn and pandas major migrations in #878 and #879. Preserve lockfile-only changes too, such as the Supabase JavaScript update in #880. The hash expansion in #872 needs review against the existing approved-wheel policy; fewer PRs do not justify accepting it without that review.

Configuration rollback is the previous `.github/dependabot.yml` from the configuration PR's base commit. It changes future update behavior; it does not roll back merged dependency upgrades or establish the state of existing PRs. Do not restore the old queue limits merely to trigger extra hosted runs.

References, checked 2 November 2026:

- [Dependabot options: groups, directories, routine limits and version-only allow rules](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [Configure security updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates)

Publishing, uploads, workers and financial generation remain off throughout this change.

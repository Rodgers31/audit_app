# Batch 9 dependency evidence

Product: `94f350ffc93bec4433617b04bf7c94bad4828345` on the pinned main baseline
`672c5c011ce57dc41551f5fbc642bc4e69134c43`. See
[the handoff](../BATCH_9_DEPENDENCIES_HANDOFF.md) for scope, limits, unsuccessful
runs, residual advisories and review dispositions.

[summary.json](summary.json) binds seven product hashes, 96 recorded commands,
all 173 unchanged production records, complete advisory-root/entry/node counts,
and every immutable raw file's hash.
[raw-receipts.tar.gz](raw-receipts.tar.gz) contains 308 raw/tool files, including
all red/green output, failed setup/control runs, paginated issue inventory,
registry/advisory snapshots and independent child results. Loose raw files
remain locally; the archive is the committed portable copy. Older records retain
their original absolute generator/cwd paths. When reproducing elsewhere, map a
generator under this evidence directory to the included file with the same name
and verify its content hash; do not reinterpret its historical target identity.

Extract into an empty owned directory, then compare every extracted file with
`rawArchive.entries` in the summary. The archive includes all original generating
scripts; `run.cjs` records new immutable commands and verifies its own readback.
Use a new receipt name on every run. `build-evidence.cjs` is an append-only
snapshot builder; the committed summary/archive already exist, so rerunning it
in place intentionally fails. Reproduce a new evidence snapshot in a new owned
directory, preserving this one.

Examples after `npm ci --engine-strict` in an owned frontend:

```sh
npm run test:dependency-boundaries
npm run verify:dependency-tooling
node ../docs/admin/implementation/batch9-dependencies-evidence/replay-unsafe-version.cjs baseline
node ../docs/admin/implementation/batch9-dependencies-evidence/replay-unsafe-version.cjs candidate
```

The baseline unsafe-version command intentionally fails the new expectation
because the old guard returns success; the candidate command passes because
the actual guard rejects it. Rejected report controls substitute a measured
report at that boundary; installed-graph and CLI controls separately execute
real npm/Jest. They do not claim an ownership race or worker exclusion.

The summary audit validator refuses absent/malformed/incomplete measurements,
checks npm report version and entry/severity totals, and verifies observed audit
exits. `ADVISORIES_PRESENT` is distinct from `NO_ADVISORIES_REPORTED`.
Full final audits are still 26 macOS/27 Linux entries at two roots, exit 1.
Production reports are zero, exit 0. Neither is a complete #494 acceptance verdict.

The accepted independent reports are `spec-accepted-review.md`,
`standards-accepted-review.md` and `behavior-accepted-review.md`. Earlier reports
remain historical and are superseded only as described by the dated handoff.

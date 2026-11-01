# Dependency PR review disposition — 1 November 2026

This is a limited maintenance review of PR866 and its stacked weekly-bot PR867.
It is not completion or signoff of the interrupted broader application security
audit. It enables no workflow, worker, source writer, upload or publication.

## PR866 findings

**Vercel branch patterns: refuted; no configuration change.** The finding says
`git.deploymentEnabled` uses literal branch names. Vercel's current
[official Git configuration documentation](https://vercel.com/docs/project-configuration/git-configuration#matching-multiple-branches)
explicitly supports minimatch syntax. It also defines the default for an
unmatched branch as true and lets any matching true rule permit deployment.

An executed check reads the current `frontend/vercel.json` and uses the installed
minimatch11.0.3 with Node24.22.1. All eight representative branches give their
expected result: npm/pip/worker Dependabot branches and both dependency Codex
branches match the existing false rules; `main`, an ordinary feature branch and
the source-acceptance branch retain the default true policy. Changing the rules
to two exact names would lose coverage of future bot branches. This is evidence
for the documented matching semantics, not a hosted deployment or proof that
every provider-side integration setting has been exercised. No deployment was
triggered to test it.

**Installer spelling: refuted, already resolved.** PEP503 replaces separator runs
with a hyphen; it does not remove them. `P_I_P` and `p.i.p` name `p-i-p`, not `pip`.
Case variants of `pip` are handled by the existing lowercase sort. Duplicate
detection still uses canonicalized names. The existing installer unit controls
exercise pip-first ordering through a recording subprocess port; they install
no package and start no worker.

**Worker fixture CI coverage: valid, fixed.** The required `test-backend` job
previously did not collect `tools/worker_host_fixture/tests`. It now runs that
suite as a bounded, two-minute unittest step after dependency installation.
The existing workflow remains disabled; no hosted run was requested. The exact
configured shell command passes all34 local tests in normal and optimized
Python. An owned one-test failing fixture returns exit1 through the same shell
command, proving a failed unit test blocks the step. The pre-change workflow
fails the step-presence check. These are unit controls, not a worker-image,
kernel confinement, capacity, provider or live workload qualification.

**Historical replay controls: valid documentation boundary, preserved evidence.**
The follow-up's `legacy-api-major-control.cjs` and `guard-exemption-control.cjs`
are historical controls. The former expects a legacy caller to fail on a modern
matcher; that expectation is obsolete after the caller migration. The latter
reconstructs an earlier exclusion guard and requires its exact old source shape.
They must not be used as acceptance gates against the migrated candidate.

The eight executable/configuration inputs recorded in
`dependencies/2026-10-31/followup/spec/source-binding.json` were independently
compared with committed snapshot
`1ebfaed53deabe9f0ce0f2dc5e02a81a20f83b9f`: all eight hashes match. The archived
reports, scripts and receipts remain unchanged so their provenance is retained.
The archival replay page's generic "candidate" path refers to those bound
historical bytes, not today's default checkout. Current acceptance uses the
permanent matcher/caller/cache/install boundary tests in
`frontend/scripts/lint-matcher-migration.test.cjs`,
`tooling-repair-install.test.cjs`, `modern-glob-boundary.test.cjs` and the
maintained matcher migration report. Historical command receipts are not a new
audit or a passing current-candidate run.

## Submitted public-response patch

Claude's submitted commit3d8e57b changes public-response projections and adds
fourteen ordinary unit tests: public server paths/private job details are
removed, exception details are replaced with fixed public messages, and
operator logs/admin-only job status retain their existing diagnostic purpose.
The diff changes neither dependency manifests nor publication/source controls.

The actual fourteen tests were rerun in a network-disabled, read-only source
container. With the immediately preceding `main.py` overlaid, eleven fail and
three pass; the submitted code passes all fourteen in both normal and optimized
Python. No real database, provider or credential was used. This corroborates
that specific patch and its regression behavior; it does not establish that the
whole application or every dependency is vulnerability-free. The separately
documented raw npm audit and runtime/worker qualification limits still apply.

## Evidence and holds

The coordinator retains exact commands, code hashes, test outputs, the eight
Vercel matching results and historical source comparison in the private
`pr869-release-open-pr-reviews/dependencies` evidence directory. An initial CI
probe expected31 tests from one file; discovery correctly ran34 including the
endpoint-framing file, so that probe refused. The corrected exact34-case probe
and negative control pass; the initial refusal is retained as harness history.

PR866 and PR867 remain for human review. No merge, deployment, paid review,
hosted rerun, resource, grant, credential or operational activation is authorized
or performed by these review fixes. Publishing, uploads, workers, financial
generation and native financial source admission remain off.

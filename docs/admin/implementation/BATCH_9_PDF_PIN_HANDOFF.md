# Batch 9 PDF pin handoff — #586

## Goal and ownership

[Issue #586](https://github.com/Rodgers31/audit_app/issues/586) asks for an offline
rebind of the retained-PDF acceptance workflow to the producer already accepted
through #569 / #578. The owned managed worktree is
`/Users/roger/.codex/worktrees/a9aa/audit_app`, branch
`codex/batch9-pdf-workflow-pin`, based on verified main
`672c5c011ce57dc41551f5fbc642bc4e69134c43`. Initial HEAD matched this identity,
the checkout was clean, and read-only `git ls-remote` returned the same main.
This lane has no dependency on held #584.

Changed-file ownership is limited to:

- `.github/workflows/r2-acceptance.yml`: one producer SHA256 assignment.
- `backend/tests/test_r2_acceptance_workflow_pin.py`: offline guard regression.
- This handoff and `docs/admin/implementation/batch9-pdf-pin-evidence/`.

Producer and Batch 8 receipt-runner bytes, other workflows, runtime manifests,
financial/ETL/claim code, credentials and the primary checkout remain outside
this delivery. No interface, migration or persistence code changed.

## Exact rebind and preserved evidence

`git show 672c5c0:backend/scripts/r2_producer_acceptance.py | shasum -a 256`
returned `9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f`.
The original workflow expected
`15b2a796171a9bd8b994d1de16bc8a4e49b863a57dc85dd77baa78395aad1028`.
Only that expected hash changes. The script hash is also checked in the
executed positive control before the shell runs.

The original [Batch 8 handoff](BATCH_8_PRODUCER_LINT_HANDOFF.md) and
`batch8-producer-evidence/workflow-pin-control.json` remain intact. Their stale
pin refusal was deliberate at that time. The dated Batch 9 receipts supplement
that history; they do not overwrite or recertify historical producer results.
Each receipt records generator/test/workflow/producer/old-runner hashes, command,
runtime, target HEAD/tree, dirty status, actual stdout/stderr and exit code.
The recorder reopens every written receipt, and the regression checks every
owned JSON receipt's live generator provenance, including unsuccessful runs.
WIP target HEAD/tree names the baseline; the content hashes name executed bytes.

## Executed local results

| Check | Actual outcome | Receipt |
| --- | --- | --- |
| Old-pin refusal and confirmation controls | 7 passed, 17 deselected | `baseline-negative-controls.json` |
| Current reviewed producer with old pin | 1 failed, 23 deselected; shell exit 1 before observer | `baseline-current-bytes-red.json` |
| Rebound guard selection | 24 passed; no skips/xfails | `rebound-guards-green.json` |
| Scoped critical lint, flake8 7.3.0 | exit 0; stdout count `0` | `scoped-critical-lint.json` |
| Existing R2 inline workflow syntax selection | 6 passed, 193 deselected; no skips | `workflow-shell-syntax.json` |
| Owned Python compilation | 2 files compiled, exit 0 | `compile-owned-python.json` |
| Shared flake8 availability setup | exit 1, module absent; not acceptance failure | `missing-shared-flake8-setup.json` |

The regression executes the workflow's actual YAML `run` block with Bash
`-e -o pipefail` and actual `sha256sum`. Its `python` observer imports the
unchanged producer module and runs actual `main`, argparse, guard ordering and
Git commands in a separate OS process. A fresh owned local clone is checked out
at frozen app HEAD `420cdc1887502940db32403fe26c6158789f9bc3` / tree
`093b3c321197943c0a647f1e763212982ee7cef4`. Clone objects are read-only; the
fixture owns its index, refs and worktree.

The live `run` function alone is replaced by a call-log observer returning
`OFFLINE_GUARD_ACCEPTED`. Positive pilot and PDF markers prove the observation
channel is alive. Linux/Python 3.12 are explicitly simulated to exercise the
guards on macOS; this is not runtime parity. Child environment is constructed
without ambient provider credentials/configuration, dotenv is disabled, and
socket entry points refuse IO. No application startup or live producer runs.

Negative controls cover changed/empty/absent script, actual wrong Git checkout,
dirty frozen checkout, moving `main` and wrong literal expected HEAD, unsupported
stage and `--attempt 2`, absent live/publisher switches, wrong account/bucket/
jurisdiction/source, zero memory and nonnumeric timeout. Confirmation executes
its actual shell with empty, wrong, trailing-space and correct values. Structural
checks retain dispatch-only triggers, fixed application checkout, credential
isolation, permissions, concurrency and step/job time limits.

`--attempt 2` is an unsupported producer argument; its refusal does not certify
a GitHub rerun policy. The existing workflow has no `github.run_attempt` check.
No such policy is added by this hash-only maintenance. Existing single-source
publisher-request and retry controls inside the producer remain unchanged and
are not retested as live behavior here.

The only production entry path for this pin is the manual workflow's acceptance
step. Repository searches found one workflow hash assignment; direct producer
calls use their own guards and do not consume this pin. No sibling trigger is
changed. The test is under the normal backend testpaths; the documented scoped
command uses `--confcutdir=tests` to avoid unrelated application startup.

Reproduce from the backend directory with Python containing pytest, PyYAML and
pytest-asyncio:

```sh
python -m pytest --confcutdir=tests -p pytest_asyncio.plugin \
  tests/test_r2_acceptance_workflow_pin.py -q -s
```

To record it from the repository root, use a fresh output directory/label:

```sh
python docs/admin/implementation/batch9-pdf-pin-evidence/record_check.py \
  --label replay --output-dir /OWNED/receipts -- \
  /ABSOLUTE/python -m pytest --confcutdir=tests -p pytest_asyncio.plugin \
  tests/test_r2_acceptance_workflow_pin.py -q -s
```

Runtime is read-only primary venv Python 3.13.9, pytest 9.0.2 and PyYAML 6.0.3
on macOS 27.0.1 arm64, Git 2.54.0 (Apple Git-157), Bash 3.2.57 and Darwin
sha256sum 1.0 (`runtime-tools.json`). No packages were installed into that runtime. The initial
flake8 command reported module absent; flake8 7.3.0 was installed only in the
owned external `PDF_PIN` evidence directory for final checks. This setup failure
is not counted as a test pass. SQLAlchemy minimum testing, migration and
frontend builds are inapplicable to this workflow pin/test-only change.

## Independent review and publication

Independent Spec and Standards reviews each report zero actionable findings
and independently execute the same 24-control suite with no skips/xfails. Spec
also independently reproduces old-shell exit 1/no observer and new-shell exit
0/pilot+PDF markers. Standards checks exact workflow delta, original producer
blob identity and every current owned receipt's provenance.

The independent behavior reviewer authored a separate sitecustomize tracing
interposer and harness, invoking the unchanged script CLI through the actual
Python interpreter. Its final trace stops on `main`'s line before calling `run`;
application imports, network and non-read-only Git subprocesses are denied.
Final controls: **30/30 pass, no skips/xfails**, including real wrong/dirty
HEAD and a newly created local moving branch with the same tree but a different
commit, actual macOS runtime refusal, malformed output/path, shell-injection
confirmation text, and supported versus unsupported CLI arguments. This is
independent of the author's test implementation.

The original behavior control is preserved with 24/30 passes and six harness
failures. An executed audit-shape diagnostic established that a `PosixPath`
cwd broke JSON event serialization; the preliminary bytes-valued-executable
hypothesis is retained and refuted in the raw diagnostic. Costly per-frame path
resolution was also repaired. Original and corrected generators/interposers
remain separately hashed. The v2 body-entry stop also passed 30/30; v3 stops
before the call itself and denies unexpected `run` entry. The final readback
verifies generator/interposer hashes and removal of all three owned temporary
clones and child processes.
Spec's missing-gh PATH setup and Standards' overly strict receipt-inventory
assumption failures are likewise retained and corrected, not called acceptance
passes. No review finding required implementation changes or a new issue.

Raw scripts, commands, output, source/generator hashes and reports live under
the external `pdf-pin/{spec-review,standards-review,behavior-review}/` directory
below. `review-evidence-bindings-v2.json` binds their top-level artifact hashes
in this committed packet. The first author review inventory also included all
temporary checkout files; that oversized but valid inventory is retained
externally as `review-bindings-with-fixture-checkouts.json`, rather than added
to the PR. The v2 inventory intentionally limits itself to review artifacts.
Selections overlap and counts must not be added.

Keep the PR draft for coordinator acceptance; no bot
review is requested by this lane and no merge is performed. Exact final delivery
HEAD and PR URL will be read back after the final commit/push into external
`delivery.json` under
`/Users/roger/.codex/visualizations/2026/10/09/01a1220d-747c-7542-8adf-1edef834d5f6/pdf-pin/`.
This avoids a self-referential commit hash inside its own committed contents.

All 287 open and closed non-PR GitHub issues were inspected through paginated
`issues?state=all&per_page=100`. Existing #586 tracks this exact pin; #569/#504/
#137 historical acceptance and #545 parent remain separate. No newly confirmed
defect requires a follow-up. No issue is closed by this author.

## Remaining operational authorization and prerequisites

Offline issue acceptance covers the rebind and guards only. A new full 935-page
replay, intended-host memory/disk and deployed acceptance are **unexecuted**.
They require separate human/coordinator approval for the exact run/attempt,
including any rerun, and source/
storage operations, acceptance of this draft, and coordinator-managed Actions
state. Read-only GitHub inspection on 2026-10-09 reported `r2-acceptance.yml`
`disabled_manually`; historical claims in TESTING_GATES do not prove hosted CI.

Before a later run, verify the accepted harness bytes again, frozen clean app
HEAD/tree, fixed PDF SHA256
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`
and 53,561,211-byte retained object, private source account/bucket/default
jurisdiction, source-only credentials and control token isolation. Use the
actual backend requirement file on Linux/Python 3.12, at least 15 GB physical
memory, the fixed 8 GiB process budget and 720-second limit, and explicitly
measure intended-host disk space/headroom before running. Preserve the current
15-minute job and 12-minute combined pilot/PDF step bounds.

An authorized later run must retain safe summaries and generator hashes,
observe the full semantic oracle and qualification/public-consumer checks, and
measure actual peak RSS, elapsed time and disk use on the intended host. Deployed
adapter/settings/read-only consumer checks require their own coordinator
authorization and actual deployed receipts. None is inferred from these
offline guards. #490 storage/reconciliation, financial acceptance and deployed
operational tracking remain independent.

## Resume and reusable lessons

Resume from this managed worktree and handoff; inspect the draft and final
delivery receipt, then perform coordinator review/acceptance. Retain the worktree
and evidence. All fixture processes exit normally and tmp checkouts are owned
pytest resources; no server/container/service or shared DB was started.

The lesson supported by the red/green receipts is to execute a frozen shell
guard before rebinding its hash: a hash equality assertion alone cannot prove
that refusal stops execution or that admitted bytes reach the next guard.
Use an explicit observer at the live boundary and label simulated runtime
separately from intended-host acceptance. Do not convert unsupported CLI-attempt
refusal into a claim about GitHub rerun policy. The coordinator can consolidate
these lessons; no global skill or common contract is edited.

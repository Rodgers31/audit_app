# Batch 8 producer lint handoff — #569

Local acceptance for [#569](https://github.com/Rodgers31/audit_app/issues/569)
is complete using the frozen contract's bounded inert regression path. The
production change is one line: clear the captured dictionary contents after
comparison, preserving the closure binding and releasing its heavyweight values
before SQLite persistence. This fixes the critical lint gate without changing
parser, financial, receipt, qualification or publication code.

## Source and delivery identity

- Repository: Rodgers31/audit_app. Parent #545 remains open.
- Fixed base: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`.
- Base tree: `f22a430a4402d79867da63ad97db8c8d474d3a71`.
- Owned checkout: `/Users/roger/.codex/worktrees/537c/audit_app`.
- Branch: `codex/batch8-producer-lint`.
- Base producer SHA256:
  `15b2a796171a9bd8b994d1de16bc8a4e49b863a57dc85dd77baa78395aad1028`.
- Final producer SHA256:
  `9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f`.
- Capture test SHA256:
  `e21974a1e75f82a1ec45956b07bd85497d49aef52fb882d03b56afe7d5ef03d0`.
- Implementation/final Git identities and draft PR URL are recorded in the
  delivery addendum below after publication. Nothing is merged by this lane.

WIP receipts name the unchanged base HEAD/tree in `target_commit/target_tree`;
their producer/test content hashes identify the exact modified bytes executed.
They do not claim the working tree was clean or already committed. Delivery
identities bind the committed source to those same executed bytes. The exact final delivery HEAD
is also retained in the external `delivery.json` after the last documentation
commit, avoiding a self-referential commit identifier.

## Executed evidence

Compact, append-only receipts and the allowlisted runner are in
`docs/admin/implementation/batch8-producer-evidence/`. Every receipt binds the
runner's SHA256, command, cwd, source/test hashes, Python/platform, output and
observed exit status; provenance is reopened after writing. The evidence guard
examines every owned JSON receipt and refuses missing/mismatched generator
provenance unless explicitly superseded. Larger independent scripts, exact
baseline export, diff snapshots and raw results remain under:

`/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-7430345d2ae6/producer-lint/`.

| Check | Observed result | Receipt |
| --- | --- | --- |
| Exact broad backend critical lint on base | exit 1; one F821 at line 440, no other findings | `baseline-critical-lint-v2.json` |
| Producer regression on unchanged base | exit 1; lint test failed for that F821; 10 runtime controls passed | `baseline-regression-v3.json` |
| Broad critical lint after repair | exit 0; stdout `0` | `final-critical-lint.json` |
| Producer regression after repair | exit 0; 11 passed, two existing SQLAlchemy warnings | `final-regression.json` |
| Wider producer/receipt/cache/PDF-evidence selection | exit 0; 285 passed, 3 skipped, two existing warnings | `receipt-regressions-v2.json` |
| Owned receipt provenance guard | exit 0; 1 passed | `evidence-provenance-check.json` |
| Final selection including the evidence guard | exit 0; 286 passed, 3 retained-PDF skips, two existing warnings | `delivery-suite.json` |
| Final broad critical lint | exit 0; stdout `0` | `delivery-critical-lint.json` |
| Disabled workflow's hash pin comparison | old hash differs from current; expected refusal, no workflow invocation | `workflow-pin-control.json` |

Earlier failed runs are preserved. The first standalone collection attempt
failed before runtime assertions because the application rejects the in-memory
SQLite pool with its configured pool options. The runner now uses an owned file
destination; `SUPERSEDED_RUNNER.md` explicitly records the old runner hash and
supersession. The first wider selection omitted backend conftest and reported
265 passes plus 12 missing-fixture errors. Loading the required shared test
fixtures produced the passing wider result above; no implementation repair was
needed. These errors are not counted as passes.

The three skips are exactly one `PDF_EVIDENCE_REAL_BROP` case and two
`PDF_EVIDENCE_REAL_CBIRR` cases. Their absent retained document resources are not
substituted or certified by the synthetic controls.

## Runtime boundary and fixture identity

`test_r2_producer_capture.py` invokes real `pdf_producer`. Its inert synthetic
body is SHA256
`b4468b18ca570c7ed0239d985c77697a511b3661e7b0171fc0a7a6b00a071d93`.
It replaces the expensive PDF parser/page extraction boundary with explicit
synthetic output and replaces the unavailable retained semantic comparison with
a named observer. It executes actual fetcher orchestration, cache freshness,
conversion, signed R2 adapter at a local MockTransport, sealed local-byte
receipt creation/binding, budget parsing/writing, SQLite and public qualification.
The synthetic counts are selected to exercise the real orchestration guards;
they are not counts extracted from a PDF in this session.

Alive markers prove tables, parsed records, revenue coverage and converted output
reach the real capture path. Weak references prove captured parse records,
copied table rows and coverage are gone before SQL persistence while converted
records remain available. Real SQLite creates 468 synthetic budget rows and one
receipt extraction. Its 1,404 qualification fields match the producer's
independent row assembly; retained bytes have no invented publisher HTTP status
or acquisition time. Public qualification/serialization does not call the
measured store. Separate literal-projection controls execute real
`compare_pdf_output`, verify no runtime receipt mutation, and refuse altered
publisher status. Size/count/cache/receipt/SQL failures never report success.

The whole repository was searched for this lifetime boundary. There is one
`pdf_producer` definition and one production caller, `run`'s PDF-stage branch.
The dispatch-only workflow invokes that stage. Pilot and marker-read branches
have separate implementations and no captured dictionary. Direct calls and
the PDF-stage call share the repaired boundary; no scheduled/domain parser or
financial writer was edited.

## Independent reviews

Standards and Spec reviewers ran in parallel against fixed base, full initial
diff, current #569 issue/comments and frozen Batch 8 spec. Standards reported
0 hard documented-standard violations and 0 heuristic findings; tool-enforced
lint rules were kept separate. Spec reported 0 findings and independently
executed the 11 producer controls and broad critical lint successfully.

A separate adversarial executor authored its own synthetic parser/store harness,
ran both the exact base export and repaired producer, and observed the four
capture/lifetime channels through actual conversion, receipts and SQLite.
Its 56 cases comprise 38 primary cases (a positive control and 17 hostile
direct-call boundaries per arm, plus literal projection/immutability per arm)
and 18 supplemental capture type-gate probes. Missing/wrong bytes,
None/empty/cached parse, missing/duplicate observation channel, short counts,
serialized or modified receipts, missing evidence/conversion, comparison refusal
and SQL refusal did not produce success. No introduced runtime defect was found.
Supplemental None, wrong-schema dictionaries, booleans, NaN, both infinities,
tuple and plain empty-list captures refused on both source versions.
These executed controls are independent of the author's test implementation.
Exact reports, commands, probe scripts and read-back hashed results are retained
under `standards-review/`, `spec-review/` and `adversarial-review/` in the raw
directory. Final delivery rechecks are appended below.

No additional confirmed defect required a new issue. The workflow's deliberate
pin refusal is an existing security boundary and a future coordination
prerequisite, not a reason to weaken the gate. #569 remains open until the
coordinator accepts and merges its draft PR; broader and operational parents
are not closed here.

## Reproduction and limits

Runtime: read-only `/Users/roger/Documents/projects/audit_app/venv/bin/python`,
Python 3.13.9 on macOS 27.0.1 arm64. Exact versions are in
`runtime-versions.json`: flake8 7.3.0, pyflakes 3.4.0, pycodestyle 2.14.0,
mccabe 0.7.0, pytest 9.0.2, SQLAlchemy 2.0.46, pdfplumber 0.11.9,
pdfminer.six 20251230, httpx 0.28.1, botocore 1.42.54 and pydantic 2.12.5.
This is not Linux/Python 3.12 parser or memory parity. Repository requirement
files and tool versions are unchanged; the issue's actual pinned lint tool is
installed only in an owned external directory.

To reproduce, install `flake8==7.3.0` in a new owned `--target` directory using a
compatible read-only Python. From repo root, invoke the committed runner with
that directory, a new receipt label and an owned output directory:

```sh
python docs/admin/implementation/batch8-producer-evidence/run_check.py \
  --label repeat-lint --output-dir /OWNED/receipts --lint-packages /OWNED/lint \
  -- python -m flake8 . --count --select=E9,F63,F7,F82 \
  --show-source --statistics --exclude=venv,__pycache__,.git
python docs/admin/implementation/batch8-producer-evidence/run_check.py \
  --label repeat-producer --output-dir /OWNED/receipts --lint-packages /OWNED/lint \
  -- python -m pytest --confcutdir=tests -p pytest_asyncio.plugin \
  tests/test_r2_producer_capture.py tests/test_r2_producer_evidence.py -q -s
```

The runner's receipts retain the exact fully resolved commands actually used.
The wider suite requires backend conftest, so omit `--confcutdir=tests` for it.
No full repository/financial, frontend, deployment or production acceptance
suite is claimed from this narrowly scoped tooling repair.

The **full 935-page retained-PDF replay is unexecuted**. No exact retained PDF
was found in checked-in fixtures or the checked session evidence paths. No
source acquisition was attempted. Historical 2026-10-08 hosted receipts remain
intact and are explicitly superseded for claims about this new generator in
`HISTORICAL_PRODUCER_RECEIPTS.md`. Their financial numbers are not corrected or
recertified here. The exact full-PDF oracle remains unchanged and unexecuted.

The disabled `r2-acceptance.yml` still requires the old script SHA256. Offline
comparison proves it would refuse the new bytes. A coordinator-reviewed pin
update is required before any future separately authorized workflow invocation.
GitHub read-only verification returned `actions.enabled=false` and main still
at the fixed base. No hosted checks were requested or fabricated.

## Ownership, cleanup and next action

Only the producer, targeted tests and this lane's handoff/evidence are changed.
No primary-checkout file, shared runtime/cache, financial source file, model,
registry, CLI, provider, workflow or other lane tree was mutated. Subagents wrote
only their owned raw evidence. Child test commands complete normally; there is
no owned server, listener, worker process group, database service or container.
Fixture storage/SQLite uses owned temporary paths; raw scripts and evidence are
retained for review. Disposable lint installation cleanup and final Git
cleanliness are confirmed in the delivery addendum.

Next action: coordinator review the attached scoped draft, manually request
Copilot if desired, integrate it under existing policy, then close #569 after
accepted merge. Any workflow-pin rebind/full retained replay belongs to a
separately reviewed follow-up. #545 and the operational gates remain open.

## Published delivery addendum

Draft PR: [#578](https://github.com/Rodgers31/audit_app/pull/578), opened and
attached to this author chat. The reviewed implementation commit is
`2a26a74b5937ba1016b23b0dfc000db645988972`, tree
`5658d69acbc787b5b93733b17c0005ab9f204cee`. Its checkout was clean immediately
after commit and before the normal branch push. The production source is
identical to the executed/reviewed final SHA256 above. This final addendum is
documentation only; exact resulting tip/tree and remote-head equality are
written after commit to the owned raw `delivery.json`.

The final local selection includes the evidence guard: **286 passed, 3 skipped**,
exit 0; final broad flake8 critical gate returned `0`, exit 0. Standards and
Spec final rechecks found no blocking findings, and independent adversarial
execution retained 56 cases. The final reports are copied with original
content hashes into `batch8-producer-evidence/INDEPENDENT_REVIEWS.md`.

The owned external flake8 installation and this checkout's pytest cache were
removed after verification. Independent reviewer temporary source/storage/SQL
fixtures were removed; their exact scripts and receipts remain. No owned
server, worker, listener or container was started. The shared Python runtime
and other checkouts remain untouched. The managed worktree remains available
for coordinator review.

PR creation was verified `OPEN`, `isDraft=true`, no requested reviewer. No paid
review was requested. An automatic Vercel integration context appeared on GitHub;
it is not backend/ETL/security Actions evidence and is not counted in acceptance.
Actions was read back disabled. No merge, workflow invocation, manual deployment,
provider/source acquisition, production SQL/storage write or issue closure
occurred. Scoped local #569 acceptance is complete; the retained-PDF replay,
future workflow pin rebind and broader operational gates remain separate.

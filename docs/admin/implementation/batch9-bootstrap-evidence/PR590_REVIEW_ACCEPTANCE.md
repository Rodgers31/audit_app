# PR590 review corrections and local acceptance — 2026-10-09

This index supersedes current-acceptance claims in the historical author handoff,
README and independent reports. Original receipt/output bytes and prior failures
remain unchanged. The author head is `813acb0b75c6eccadf514dbbaffbc6439fd7fb63`;
review checkout merged actual main `b0ec603ccbf29d5ae7f6540faa3d484964334fb1`
without source conflicts. The merge checkpoint is
`cfc77b7615c3c0bb8af110edf22beca8cc15abe8`. New receipts explicitly bind the
working-tree files, rather than claiming that the pre-repair checkpoint alone
identifies the tested source.

## Review findings

| Finding | Classification and verified correction |
| --- | --- |
| `4235345006`: caller transaction committed on refusal | **Valid, understated.** Coarse and county probes could also roll back/close a supplied caller session; early helper commits could commit it. All three bootstrap session entrypoints now borrow a child `create_savepoint` session when a caller Session or Connection has a transaction. Refusal and successful bootstrap preserve the caller's outer transaction. |
| `4235345038`: process URL redirects | **Valid, understated.** Shared exact driver/host/port/user/password/database validation refuses URL overrides and nonempty ambient `PG*` settings before engine construction. The subprocess hook pins DBAPI loopback host/hostaddr, port, database and credentials. |
| `4235345062`: cleanup target redirection | **Valid.** Same DB guard plus exact labelled Docker identity and JSON published port verification precede connecting. Actual database/user census verifies no other owned databases, schemas or sessions before removing only that container ID. |
| `4235345100`: migration replay redirects | **Valid.** Guarded admin and migration engines; Alembic's actual engine construction is temporarily pinned and restored. Replayed database revisions must equal the checkout's actual Alembic heads, with claims RLS enabled and zero claim rows. |
| `4235345133`: other-domain evidence redirects | **Valid.** Guarded admin CREATE/DROP DATABASE target and pinned engines. The existing #589 defect remains separate. |
| `4235345168`: Spec driver redirects | **Valid.** Guarded parent and child connection settings before constructing engines. Native-first real startup is re-executed against the owned fixture. |
| `4235345201`: missing `baseline.txt` | **Invalid.** It is tracked at the reviewed author head, is 8,075 bytes, and SHA256 `2943bbd84a0fd2887e6651b1866346ea632f9c5f227bb8880fda7ec83148f948` matches `baseline.json`. The untouched author verifier actually completed: 31 JSON plus three Spec raw records. No baseline output was fabricated or exempted. |
| Body-only: verifier ignores source hashes | **Valid.** Original verifier accepted an actual independent source mutation. New current receipts compare every recorded source hash with current file bytes. Older records are frozen under `historical-provenance.json` and cannot certify current behavior. Generator archives preserve exact original bytes; raw output remains required for historical records. |
| Body-only: `source_mode=not_run` invalid | **Valid for the admin metadata allowlist.** `safe_job_metadata` omits `not_run` and accepts `unknown`; this is an allowlist filter rather than an exception in generic national-budget persistence. Refusals now persist `unknown`, FAILED and `ownership_refused=True`. The county-audit validator is domain-specific and is not the national-budget validator. |

The same fixture guard applies to **six executable entrypoints**, including the
adversarial child driver in addition to the five mentioned in inline findings.
The refusal matrix contains 12 URL variants and five ambient redirects for each
entrypoint (102 cases), plus two actual owned target positive controls. Verifier
controls prove independent source drift and missing historical outputs fail.
Original pre-repair controls failed the refusal contract; some already-invalid
URLs raised the wrong old assertion, so these failures do not imply that all
102 inputs previously reached a database. No refusal control constructed a real
external database connection.

## Caller commit boundary

The four SQLite Session/Connection × force controls observe pending caller data
from the caller and from an independent connection, then verify caller rollback
removes it. Actual PostgreSQL controls also execute the budget handler: the
original author source ends/commits the caller transaction and releases its claim;
the repaired source leaves the outer transaction active, with zero independently
visible effects and one unreleased independently committed claim. Caller rollback
removes reference/budget effects while that claim remains. A child savepoint
commit is not evidence that the caller's outer transaction committed. Accordingly,
borrowed successful jobs record `outer_commit_pending=True` and
`ownership_retained=True`, and bootstrap does not acknowledge them. Ordinary
owned transactions commit before acknowledging and retain the existing next-run
behavior. There is no automatic recovery/release of a retained caller-owned claim.

## Executed acceptance

Bootstrap source SHA256 is
`a513689c2c5458783470128ae5019a77db3fad55f2f66ada058f9398387311cf`.
Current Python 3.13.9 / SQLAlchemy 2.0.46 and minimum Python 3.12.15 / actual
SQLAlchemy 2.0.23 execute identical source-bound selections:

| Receipts (`.json` and `.txt`) | Observation on each runtime |
| --- | --- |
| `review-scope-{current,min}-acceptance` | 253 passed; includes 143 previous scoped cases, four new caller controls, 102 refusal controls, two positive targets and two receipt-verifier controls. Counts overlap with selections below. |
| `review-default-process-{current,min}-acceptance` | 20 passed, zero skips/xfails; explicit author fixture URL is removed in the test process. A fresh owned default fixture is created from the already prepared immutable image and removed. |
| `review-borrowed-green-{current,min}-acceptance` | Actual PostgreSQL normal and force cases preserve caller transaction and retain the claim; zero effects after caller rollback. |
| `review-migration-{current,min}-acceptance` | Actual empty owned database upgrade reaches exact Alembic head set; claims RLS true, zero claims; owned database dropped. |
| `review-spec-{current,min}-acceptance` | **Spec:** native-first actual startup is ready with 47 counties, one bootstrap observation, only the native handler entered; preexisting budget sentinel retained. |
| `review-standards-{current,min}-acceptance` | **Standards:** independent ORM control observes caller rollback with `conditional_savepoint`, preservation with `create_savepoint`. Four concrete caller controls are also in the 253 selection. |
| `review-adversarial-wrapper-{current,min}-acceptance`, `adversarial/review-adversarial-{current,min}-acceptance` | Same 22 inert destructive/result/claim-continuity controls pass per runtime. These are replayed author controls, not a new independent reviewer endorsement. |
| `review-borrowed-red-current-acceptance` | Expected exit 1: both actual PostgreSQL caller-boundary cases fail on the exact original author bootstrap loaded from pinned Git bytes. |
| `review-other-readiness-acceptance` | Existing #589 defect reproduced: actual ready=True, county_count=0, bootstrap_jobs=0. Passing means reproduction succeeded. |
| `review-critical-lint-acceptance` | Required critical flake8 selection clean, using the read-only minimum runtime. |
| `review-cleanup-acceptance` | Exact manual review fixture census clean; only labelled owned container/anonymous volume removed, port free. |

The automatic default fixture requires the repository's approved immutable image
prep and a local Docker Unix socket. It never pulls an image implicitly, selects
only the verified local Docker endpoint, checks native image architecture and
RepoDigest, and binds only loopback port 55492. Its separate labelled bridge
network contains only its own container. The manual review fixture uses port
55590 and distinct `batch9-review-590-` resources. Parent/child environments are
inert, dotenv loading is disabled, and only inert registry handlers run. No
workflow, production settings, provider/financial source writes or shared runtime
installation changed. Hosted and production acceptance are coordinated separately.

## Preserved unsuccessful evidence and custody

All intermediate review receipts remain append-only. `review-default-fixture-red`
executed 20 **skips** before the default lifecycle fix; its zero exit code does
not mean process acceptance. The first auto-fixture attempt had 20 setup errors
because this Docker implementation published no port on its internal network.
A second had 20 passing cases plus a teardown error from delayed port release;
resources had already been removed. Neither counts as acceptance. The final
owned bridge lifecycle verifies exact published ports and waits boundedly for
post-removal loopback release. A prior owned-engine setup error caused by an
empty libpq `service` name is also preserved; service is now omitted after
ambient service settings are refused. Historical records are distinguished from
fresh final source-bound records by the verifier, rather than rewriting their
hashes or outcome counts.

The review fetched all **294 open and closed GitHub issues**. The unchanged
non-budget false-readiness reproduction is already tracked in **#589**; no new
out-of-lane issue was uncovered by this repair. #582 acceptance/closure, PR
thread replies, final hosted checks and merge remain coordinator actions.

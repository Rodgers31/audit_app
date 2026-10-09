# Independent Batch 8 producer reviews

The following final reports are copied verbatim from independent reviewers. Source identities refer to their prepublication review snapshots; later delivery-only documentation does not change the tested producer bytes.

## Standards

Original: `/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-7430345d2ae6/producer-lint/standards-review/FINAL_STANDARDS_REVIEW.md`. Report SHA256: `6643f88e735d5bc2ce7d2c76c79051dc71cf9ac781fb36f29e1b1f4b5edceaf0`.

# Final independent Standards recheck — Batch 8 #569

**Findings: 0 hard documented-standard violations; 0 heuristic smells.**

Reviewed the full current `git diff 97fe77462b4e63ffad7dc393b8bf97d3e51571f7` and byte-identical immutable `delivery-review.patch` (SHA256 `c9f4dce0c5c475a677fe97a6a8189adb3793344cfb3517dd30046f6a764437f9`). Base/tree remain `97fe77462b4e63ffad7dc393b8bf97d3e51571f7` / `f22a430a4402d79867da63ad97db8c8d474d3a71`; no post-base commit existed at review.

The producer, capture regression and runner hashes are unchanged from initial review. The new evidence test checks generator existence, current hash or explicitly documented historical supersession, and verdict/exit consistency. These evidence-maintenance assertions supplement the executed runtime controls; they do not replace behavior verification. No actionable baseline smell or documented-rule breach was found in the new hunk.

`BATCH_8_PRODUCER_LINT_HANDOFF.md` and `HISTORICAL_PRODUCER_RECEIPTS.md` distinguish synthetic capture/receipt/SQLite controls from full-PDF and hosted acceptance, preserve original financial receipts, and state that those old receipts cannot certify the changed generator. This follows `CONTEXT.md`'s byte-identity distinction and the Batch 6/7 acceptance briefs' local/operational boundaries. The unchanged disabled workflow still pins the old script; future coordinator-reviewed rebinding is explicitly pending. No protection or Actions setting is weakened by this diff.

The earlier wider-suite setup errors are historical, not unresolved current failures: `receipt-regressions-v2.json` records exit 0, 285 passes and three exact retained-document skips (BROP1/CBIRR2). The new guard receipt records one pass. The separate adversarial report records 56 independently authored cases with no introduced defect. I inspected those outputs and source bindings; this Standards recheck does not claim to have executed their suites.

The initial report is preserved. The before-publication PR/exact-head/cleanup addendum remains pending, so delivery completeness is not certified here. Full 935-page retained-PDF replay, Linux/Python 3.12 resource parity and hosted checks remain unexecuted, as the handoff states. Tool-enforced standards remain excluded from this axis.

Total Standards findings: 0 hard, 0 heuristic; no Standards blocker in the reviewed delivery diff.

## Spec

Original: `/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-7430345d2ae6/producer-lint/spec-review/FINAL_REPORT.md`. Report SHA256: `bf4487a1ce5044c1eb7a0970542cede465196fe8cb59d5c0c7715bcc9c7de4ef`.

# Final independent Spec recheck — #569

**Findings: 0.** The implementation meets scoped local acceptance; no missing code requirement, scope creep, or incorrect runtime behavior was found.

Reviewed the full current WIP diff from `97fe77462b4e63ffad7dc393b8bf97d3e51571f7` (tree `f22a430a4402d79867da63ad97db8c8d474d3a71`), frozen spec/current issue, new evidence guard, historical-receipt declaration, complete handoff, and independent adversarial report/hashed summary. Delivery patch SHA256: `c9f4dce0c5c475a677fe97a6a8189adb3793344cfb3517dd30046f6a764437f9`. No implementation commit existed during review. Producer/capture-test/runner hashes remain those in the initial report.

“Choose the smallest behavior-preserving closure/lifetime repair” remains satisfied by the sole production change, `captured.clear()` at the same post-comparison/pre-SQL boundary. “Prove the actual producer capture path” is supported by my earlier independent execution: **11 passed**, all capture/release/SQLite markers observed; real conversion, sealed local-byte receipts, real SQLite/public qualification, and failure boundaries were exercised. The handoff accurately identifies synthetic parser/count/comparison boundaries and does not recertify the retained financial oracle. The independent adversarial report records **56 executed cases** on original and repaired source with no introduced defect; its scope and resource cleanup are explicit.

I independently executed the added all-owned-JSON provenance guard: **1 passed**, exit 0 (`final-independent-spec-provenance.json`), and repeated broad backend critical lint against the final test changes: stdout **0**, exit 0 (`final-independent-spec-critical-lint.json`). The guard requires live generator files/hashes or named supersession and consistent exit/verdict. Earlier failures remain distinguishable from current evidence. My disposable synthetic fixture directory was removed; no service/container was started.

The handoff now honestly binds WIP source hashes separately from base HEAD/tree, preserves the observed **285 passed / 3 unavailable-exact-PDF skips**, supersedes old hosted-generator claims, and labels full 935-page replay unexecuted as the frozen contract permits. The disabled workflow’s old hash deliberately refuses current bytes; a separately reviewed coordinator rebind is required before future authorized invocation, with no scope expansion here.

Pending delivery, not a code finding: add committed implementation/final source identities, draft PR URL/attachment, and final cleanliness/cleanup receipts before delivery. Those requirements are acknowledged in the handoff and cannot be completed before publication.

## Adversarial execution

Original: `/Users/roger/.codex/visualizations/2026/10/09/01a11fbc-1c41-7822-ad9a-7430345d2ae6/producer-lint/adversarial-review/REVIEW.md`. Report SHA256: `1636b19d6eef5ff7086d5af5467e5b037d76ca44ff6c472ce4a8c8bb91528178`.

Independent adversarial execution for Batch 8 / #569 completed without a confirmed introduced defect.

Target: `codex/batch8-producer-lint`, uncommitted implementation over fixed commit `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, tree `f22a430a4402d79867da63ad97db8c8d474d3a71`. Producer original SHA256 `15b2a796171a9bd8b994d1de16bc8a4e49b863a57dc85dd77baa78395aad1028`; patched SHA256 `9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f`. Production diff remains the single `del captured` → `captured.clear()` replacement. Read-only repository review; all reviewer writes are in this directory.

Observed commands (Python path is `/Users/roger/Documents/projects/audit_app/venv/bin/python`):

- `python run_independent.py probes`: exit 0, `PASS: independent cases=38`; exact command/environment/stdout/stderr retained in `probes-run.json`.
- `python run_independent.py critical-lint`: broad backend command `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=venv,__pycache__,.git`, exit 0, stdout `0`; retained in `critical-lint-run.json`.
- `python run_extra.py`: supplemental real capture type-gate returns, 18 cases; child exit 0, stdout `PASS malformed real capture result cases=18`; retained in `extra-boundary-run.json`.
- The same supplemental wrapper separately linted the exact `git show` baseline producer exported into this owned directory. Child exit 1 with `:440:9: F821 undefined name 'captured'`, count 1; retained in `baseline-file-lint-run.json`. This file-specific reproduction does not replace the author's broad pinned-baseline receipt.
- `python finalize_review.py`: provenance read-back validated each retained JSON generator hash and producer identities, observed zero remaining fixture directories/SQLite files. `review-summary.json` contains the receipt manifest.

Runtime was macOS arm64 / Python 3.13.9; flake8 7.3.0, pyflakes 3.4.0, SQLAlchemy 2.0.46, pdfplumber 0.11.9. The wrappers construct an empty allowlisted environment, set owned file SQLite, disable dotenv and autoseeding/warmup, and the execution scripts replace socket connect/connect_ex/create_connection with denials. No installs, server, container, credential use, hosted provider call, or shared tree/cache/environment mutation occurred.

The independent parser fixture is separately authored and has distinctive `independent-adversary-channel-569` markers, allocated 700 and absorbed 125, rather than author test values. Its bytes are explicitly not a PDF: SHA256 `e40afcb2e8ed2342ebc0595ba41cb99286316be5b852e97d5e5852562ba6d4be`, size 67. Local byte storage carries a simulated `r2_private` label to exercise the producer's exact gate; no R2 or publisher authority claim follows from that simulation. The cache wrapper, converter, receipt capabilities, writer, SQLite, qualification, and public county endpoint execute actual repository functions.

Both baseline and patched positive controls observed exactly `PARSER`, `CAPTURE`, `RELEASE`, `SQL` markers. Capture assertions inspected tables, parsed records, revenue coverage, and converted records, including their distinctive marker and literal money values. Weak references to captured parse data, a captured table row collection and revenue coverage were dead at the pre-SQL boundary; the complete converted-record packet was unchanged by comparison. Actual SQLite/public qualification execution returned 468 rows, one receipt extraction, 1,404 qualification fields and zero public object gets. These are synthetic orchestration counts, not a retained-PDF acceptance refresh. Successful execution of the baseline confirms that its lint diagnostic is not a demonstrated runtime NameError.

Each arm also exercised absent object, wrong byte size, same-size wrong digest, None and empty parser results, plain cached-list result, missing page observation channel, duplicate page sequence, short table/record counts, serialized receipt capability, mutated HTTP status, mutated byte check, missing evidence, None conversion, comparison refusal and SQLite refusal. All rejected without a success return. No rejected probe reached SQLite. Direct capture type-gate probes rejected None, empty/wrong-schema dictionaries, True, NaN, both infinities, tuple and plain empty list with `fresh_parse_required` on both arms. An independent literal canonical projection accepted the expected bytes without mutating runtime input, and rejected a changed status on both arms.

Findings: none confirmed for the changed lifetime boundary. No additional issue is proposed. Known inherited limits remain: the full exact 53,561,211-byte retained PDF and its 935-page parser/oracle/runtime-budget replay were unavailable and unexecuted; no Linux 3.12 or hosted R2 acceptance was performed. The synthetic orchestration comparison deliberately uses an observed channel assertion rather than the retained semantic oracle. The real comparison function was executed separately against a literal bounded projection. Historical hosted producer results and the disabled workflow pin cannot certify the new generator; the author's separate supersession document states that limit. Independent execution supports the scoped lint/lifetime repair, not those operational claims.

Receipts are append-only; a repeat should use a fresh owned directory and retain the prior files. The exact scripts and baseline source are retained here to make every probe inspectable. No repository sentinel was touched by this reviewer.

Standards: 0 hard and 0 heuristic findings. Spec: 0 findings. Adversarial execution: no confirmed introduced defect across 56 cases.

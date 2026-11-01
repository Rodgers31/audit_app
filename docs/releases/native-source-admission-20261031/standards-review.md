# Independent Standards review — native source admission

**Scoped pass: 30 independent cases passed normally and the same 30 passed under true Python `-O`; zero failures, errors or skips. No actionable finding remains in this scope.** This review does not authorize source adoption or operational activation.

Frozen candidate: `../candidate`, 6,587 files, mapping SHA256 `14a510a8ab5c4078e075d0077125aa1004bce402d1f66d3f816a7ff1a15aa813`. The complete file map and manifest were verified before and after execution without changes (`SOURCE-BEFORE.json`, `SOURCE-AFTER.json`). Manifest-file SHA256: `5c21428891c41e6016173f26a7e2ac9c668526e579543898efea0b928ee4f86b`.

## Executed boundaries

- Seven real workflow root/job/seed-step environment bindings, including missing, false, exact true, uppercase, whitespace, numeric-string and empty values. Actual process admission accepts only the exact string `true`, independently of financial generation.
- Six ordinary admin qualification policy cases refuse source admission that is enabled or malformed; three fresh process startup cases demonstrate the unchanged settings model and independent defaults.
- Actual KRA producer/writer, sealed acquisition, committed PostgreSQL qualification and current financial reader: generation enabled alone did not qualify rows; source-only fresh acquisition did. Switching the flag alone did not retroactively qualify an old row. Previously qualified current-source eligibility persisted after source admission was disabled.
- Seven actual qualification mutations remained held: operator quarantine, foreign publisher, foreign URL, archived source, missing extraction receipt, changed amount, and foreign country. Four current-job mutations (running, partial/error, fixture origin and wrong domain) caused reader refusal.
- Two actual dispatch cases kept financial generation disabled for either source-flag value. Every PostgreSQL case asserted no post, target, publication, media, cursor or event creation. The final separate read-only query confirmed all seven table counts were zero.

`CASE-LEDGER.json` pins each execution to its real JUnit file. Normal: 30 passed (6.269s container wall time); optimized: 30 passed (8.723s). Commands, outputs and exit receipts are retained as `independent-{normal,optimized}-*`, `.txt` and `.xml`; tests are `test_admission_independent.py`.

## Runtime and scope limits

Execution used cached `pr863-python-patch-parity:local` image `sha256:1b4cc12668ffaa5bd5e5aa78bd96c053f8d0778651c040ad4a5d69ef305d983b`: Linux arm64, Python 3.12.16, SQLAlchemy 2.0.55, PostgreSQL 17.11, Alembic head `a756b20a0001`. Test containers were capped at 1 CPU / 768MiB / 256 PIDs and joined only the owned network-none PostgreSQL namespace; no host port was published. Fixture identity, role, database, port, data directory and schema were checked before any mutation.

The local publisher-shaped HTML, acquisition and job fixtures exercise software contracts; they do not establish current official source facts or adoption permission. Root's genuine national/KRA replays and Spec's restricted-role/cache tests are separate evidence, not included in these 30 cases. The YAML binding was expanded offline, not dispatched on GitHub. This review did not test production, install worker grants, publish, upload, or activate operational controls.

Source admission is prospective and default-off. It can admit verified freshly bound numeric source cells while financial generation remains off. It does not revoke an already accepted current source when later disabled. An explicit owner source-adoption decision remains separate from merging this code.

## Source pins

| Path | SHA256 |
| --- | --- |
| `.github/workflows/seed.yml` | `130aa9dd789c2049e3a4c554970a67fec3c1f618ed740781ceaceec1a4e31286` |
| `backend/admin_etl_qualification.py` | `4617d0b1534a8f866877bb3bac9b6ff992daf95d6d4f2f3f4544493d7e3215b0` |
| `backend/seeding/native_financial_admission.py` | `40f1533c7bd4066704970fc0fd2d1d53c20346ca7249146b588590c4657914c6` |
| `backend/seeding/native_financial_gate.py` | `2bc6f78cdd8933ea864d161714a64965a435d53d9f423223e8066b5f4ee42bbf` |
| `backend/seeding/domains/national_budget/fetcher.py` | `fbfa4781a3aafd337a39709ad7c994b02c7636a198948bd9e53f63a137d0bdb0` |
| `backend/seeding/domains/pending_bills/fetcher.py` | `9a3b7d372491a4df6200717d37f6ccad619db31b75dfcb6766daed916c211432` |

## Replay and cleanup

Use a fresh evidence sibling beside the retained candidate, copy `prepare_owned.py`, `run_independent.py` and `test_admission_independent.py` there, then execute:

```sh
python3 prepare_owned.py
python3 run_independent.py
python3 run_independent.py --optimized
```

These commands require the two pinned cached images and create only the narrowly named offline fixture. Do not reuse the sealed output directory or run concurrently with another replay of these fixture names. The prepare script generates new local credentials; it never needs production credentials. After replay, remove only its exact owned fixture and both generated env files. `seal_review.py` records the original complete verification/cleanup sequence; it is an archival receipt generator, not an idempotent replay command.

Original owned fixture `native-admission-standards-pg-20261031` and both credential files were removed; absence and retained-artifact secret scan are recorded in `CLEANUP.json`. Shared/root containers were untouched. Verify this packet offline with `python3 verify_packet.py`.

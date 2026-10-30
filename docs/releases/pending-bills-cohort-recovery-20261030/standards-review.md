# Final independent Standards review — recovery candidate 3

**Scoped pass: 50 unique cases — 34 executed on frozen 3, plus 16 unchanged source-lane controls carried from frozen 1. Zero remaining failures/errors/skips in final scope.** No actionable finding remains.

Final input: `recovery-candidate-3`, 5,799 files. Mapping SHA256 `6a1bcb7aac9b1fd4b2c44843aa8d40852a9d9bea43b25a4446c7585e86faf8fc`; manifest-file SHA256 `d8da5abf936876b364ee86e4bc5dcd6c58464d1654eeb959be54ce0dd10834e0`. Every entry matched before/after. The 2→3 product delta is only the non-virtual issuer predicate and its two admission calls; SQL/locking/source paths are unchanged (`frozen2-to3-product.patch`). Source carry hashes are pinned in `candidate3-manifest-after.json`.

| Executable scope | Cases | Receipt |
|---|---:|---|
| Genuine retained acquisition/capability → pending REPORT selection; BUDGET twins, exact retained ID, competing REPORTs, foreign rows, metadata/capability attacks; two national retained-scope counter-controls | 16 | `candidate-source-final.xml`, unchanged-path carry |
| Genuine first-cohort subset/reacquisition/replay/new facts, concurrent completion, deadline after V2 flush, typed readback fault, marker schema, private-finalizer misuse | 13 | `candidate3-final.xml` |
| Actual-hook late source/value/qualification-receipt changes and restoration replay; mutation, reconstruction, mixed-record and both virtual-method witness attacks | 8 | `candidate3-final.xml` |
| Real national-budget/revenue baseline/change/replay; snapshot table/ID/type/count bounds, missing rows and positive hashes/context changes | 13 | `candidate3-final.xml` |

## Resolved findings and classifications

- **Source lane:** accepted `0a2534d` produced five desired failures/nine passes on the core 14 controls (`accepted-source-red.xml`). Native pending bills must select unique KEN/exact-URL **REPORT** rows in both retained acquisition and writer. BUDGET 2544 is a separate lane from retained REPORT 2549; two REPORTs still refuse. Wrong/missing retained targets never substitute. Fresh only-BUDGET creates a REPORT without modifying budget metadata. National retained behavior remains unchanged. Earlier artificial all-document-type positive fixtures are superseded by this explicit lane contract.
- **Issuer integrity:** frozen 2 accepted unissued reconstructed witnesses whose instance/subclass `intact()` returned true (`candidate2-cohort.xml`: two failures/19 passes). Frozen 3 refuses both unchanged attacks using exact class plus issuer-owned weak registry through a non-virtual predicate. This was a reconstructed-capability refusal defect, **not a demonstrated source-qualification/publication bypass**; genuine qualification still occurred.
- **Completion:** final actual-hook controls refuse late source withdrawal, value/receipt drift, deadline and readback faults without committing V2. Unchanged reacquisition stays silent; genuinely new/changed facts still create held review drafts. The corrupted-cursor probe required privileged row insertion plus direct private-finalizer misuse, not normal hook flow; it was optional hardening and now refuses missing issued witnesses.

The legacy county-budget scalar helper concern is pre-existing and outside its normal bulk nightly path; no broader repair was requested.

## Execution, replay and cleanup

Source controls used actual owned PostgreSQL receipt acquisition/capture. Completion/context controls used the real Alembic chain to `a756b20a0001`, real native producers/readers/qualification/consumers and explicitly source-shaped local PDF/HTML fixtures. No synthetic authority view or verifier replacement was used. Publication/target tables remained empty.

All project execution used cached capped offline Docker: Python 1 CPU/2 GiB/256 PIDs; owned PostgreSQL 1 CPU/512 MiB/128 PIDs, 256 MiB tmpfs, no network/host port. Python joined only that owned loopback namespace. Exact DB/address/port/data-directory/schema ownership/head guards preceded mutation. Parent PostgreSQL was never used. `PROVENANCE.json` pins source/tests/JUnit; `replay.py --label <fresh-label>` recreates this isolated fixture and runs all 50 cases.

All original reds and setup failures remain retained. Setup-only failures received no test credit: CIDR address formatting before DDL, an overly narrow stale-job exception expectation and SQLAlchemy colon parsing in fault-trigger text. No skip or product edit hid them.

`CLEANUP.json` confirms the owned container and tmpfs fixture removed; no credentials/named volumes/owned containers remain. Parent PG/node were untouched. No provider/worker/upload/hosted/production action or external grant occurred. This is scoped executable evidence, not production acceptance or a latency/capacity claim; separate owner receipts are not counted here.

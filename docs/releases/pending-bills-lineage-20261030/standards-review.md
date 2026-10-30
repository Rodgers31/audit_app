# Independent Standards review — final native-only lineage repair

**Scoped pass: 54/54 executable controls passed, zero errors/skips. No actionable finding remains in this helper review.**

This report **supersedes the earlier generalized-helper 34-case pass** and the interim native-branch result. The generalized helper changed legacy title/edition behavior; that earlier pass did not establish legacy compatibility and must not be used as release acceptance. The final API deliberately scopes exact-URL selection to a valid native capability and restores no-authority legacy behavior. Historical inputs, tests and results remain intact.

## Frozen input and execution

Final input: `source/`, accepted HEAD `b7eadcb3dde3b7e5236222b8b981b9b0f3786510` plus the final writer repair. The 1,443-file manifest SHA256 is `ef542014c0b158630711df8f9e819dcba2794bc098a8a547e30844ec7e0121b8`; writer SHA256 is `c98b29aeb5242477f94b3f26a2d1ea439f4404a71420e55ce421e8cdd3a097ca`. All frozen bytes remain unchanged, and the final writer still matches the author checkout. Only writer.py differs from the retained narrow-native red snapshot. `provenance.json` and the replay receipts pin exact inputs, test hashes, argv and outputs.

All project execution ran in cached image `sha256:571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`, with read-only source and `--network none --cpus 1 --memory 2g --pids-limit 256`. Real SQLAlchemy models use isolated persisted SQLite databases with foreign keys enabled; the only dialect adaptation compiles JSONB to SQLite JSON.

Positive native controls obtain **actual NativeReportAuthority objects through capture_pdf_report**, consuming source-shaped owned PDF bytes, actual sealed acquisition receipts, retained local bytes and publisher-post HTML fixtures. They do not instantiate the authority with a private token or mock its validator. The deliberately reconstructed instance is a negative attack. These are local fixture capabilities, not proof of a real publisher acquisition or current PostgreSQL source qualification.

## Results

| Scope | Executed | Result |
|---|---:|---|
| Native: exact-URL reuse across five document types, title refresh, fresh creation/idempotency, foreign matches before the bound, same title/different URL | 8 | Pass |
| Native: duplicate URL across BUDGET/REPORT, seven non-object metadata shapes, three conflicting existing publishers | 11 | Pass; no mutation |
| Native: five bad declared publishers, seven synthetic capability shapes, wrong request URL/exported or mutated receipt | 15 | Pass; refuse before SQL |
| Native: changed value/URL/snapshot, reconstructed instance, and changed value with recomputed snapshot | 5 | Pass; refuse before SQL |
| Native: stale persisted title/metadata/publisher, null metadata, genuine wrong-domain capability | 5 | Pass |
| Legacy: five contracts each executed against candidate and accepted helper | 10 | Pass |
| **Total** | **54** | **54 passed; zero failures/errors/skips** |

No-op/refusal native controls inspect executed SQL for mutation statements and compare persisted rows; stale-map cases also require no dirty/new ORM state. Legacy comparisons commit and check identity/proof preservation, title-based URL replacement, same-URL/different-title edition creation, Treasury no-declaration, explicit publisher correction, defaults and established foreign-title behavior. Legacy selection does not receive or grant native authority.

Receipts: `final.txt`, `final.xml`, `final-receipt.json`. The **same 54 tests** against the narrow pre-integrity repair reproduce **five failures/49 passes**, with zero setup errors/skips (`narrow-red-replay.*`). The added legacy matrix against the withdrawn generalized helper reproduces **three failures/seven passes** (`generalized-legacy-red.*`), while all ten pass on the final narrow API. These results explicitly demonstrate the earlier review coverage gap and its resolution.

## Resolved admission finding

The interim helper checked class/domain/URL and receipt seal, but omitted authority snapshot and sealed observation equality. A genuine captured capability with mutated period/URL or corrupted snapshot, and a reconstructed instance, could create and commit a source through the helper. The downstream persist_native_report guard independently checked those invariants; this was a **helper admission/side-effect gap, not a demonstrated full-writer, source-admission or publication bypass**.

Final helper admission now verifies the constructor snapshot and exact sealed observation manifest before querying. All four unchanged original attack cases pass. An additional attack mutates the period **and recomputes the snapshot** while keeping the old sealed observation; it fails on the interim helper and refuses before SQL on final, independently exercising manifest binding. The core persistence/receipt guards remain unchanged.

## Replay and limits

```sh
python3 /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/release-rollout-20261030/nightly-lineage-standards-review/native-final/run-review.py --label replay-final
```

Use `--source ../native-v3/source` with a fresh label to repeat all five red attacks. The runner refuses receipt overwrite. Exact generalized-legacy comparison argv is retained in `generalized-legacy-red-receipt.json`. All product code executes inside capped offline Docker; the host script only uses the standard library for orchestration and hashes.

This is helper selection/admission/side-effect and legacy compatibility evidence. It does **not** independently execute the genuine retained-PDF database proof's source-ID branch, current PostgreSQL qualification, the actual nightly job, concurrent writers or production validation. The integration owner separately owns the real retained source→writer/lineage test. No publication, worker or source-admission activation is authorized by this pass.

No product file was edited. No shared PostgreSQL database was used/reset, no credential files or services were created, and no provider request, build, download or install occurred. Every own test container/SQLite fixture completed with `--rm`; no owned fixture remains.

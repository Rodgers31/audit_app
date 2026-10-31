# PR860 debt fallback Standards review

**Scoped pass.** Final normal and true optimized Python each passed **93 cases: 78 independent +15 author, zero failures/errors/skips**. This is 92 cases in the primary/known GDP-debt matrix plus one separately executed within-tolerance acquisition discriminator. The project's copies of the new independent regressions were pinned but not counted again.

Base `16538db009704ece4e0aaa51ac162752d591180c`; final focused projection `candidate-3`,1,466 backend files, mapping SHA256 `ef044ae9770e01228b78f27e676861973baff0d44411380d740c12d3fa84a769`. Final product pins:

- `debt_timeline/writer.py`: `f88e9deac7a97e540ca01a47ffad18c7d6411f6fa3f1a687efdc9edf12085619`.
- `debt_timeline/fetcher.py`: `e73cb83da80cea80f9373414e2cfb20cf5561eb5258a855f5986543aa4761670`.

The projection freezes the accepted backend plus the debt repairs and retained regressions; unrelated ongoing fiscal changes are excluded. All snapshot bytes and 17 reviewed current-checkout source/test/dependency pins match before/after. See `SOURCE-FINAL-BEFORE.json`, `SOURCE-FINAL-AFTER.json`, `FINAL-RECEIPT.json` and `FINAL-CASE-LEDGER.json`.

## Confirmed defects and exact RED→GREEN evidence

The unchanged original13 tests reproduced **7 failures/6 passes in both modes** on the accepted PR head (`baseline-normal/optimized.txt/xml`, `BASELINE-RECEIPT.json`). All13 now pass:

- Fallback lookup reused same-title KEN REPORTs with unrelated URL or publisher. It now requires the exact default URL/publisher as well as country/title/document lane, preserving unrelated rows.
- CBK failure overwrote previously observed stock/source/receipts with fixture values; missing GDP similarly erased prior valid observations. Existing observed values and evidence now survive when no matching current observation replaces them.
- Fresh GDP15T over retained stock1.3T previously saved/published API values for fixture stock1T and ratio6.7. It now retains1.3T and derives8.7; qualification and API checks pass. `baseline-seam.json` preserves the actual bad saved/API trace; the final unchanged tests verify corrected saved/API output. The old error downgraded qualification rather than falsely verifying the ratio; no publication bypass was demonstrated.
- Successful GDP with no current CBK was marked fixture-only. It now reports partial with separate unavailable debt/live-or-partial GDP components.

The new acquisition boundary initially accepted external520B from one issued sealed acquisition with domestic840B/total1400B from another, replacing the retained row with an inconsistent vector. `boundary2-normal.txt/xml` preserves **6 pass/1 RED** on the first repaired snapshot. Final code requires one acquisition/sealed manifest for all three stock cells and the parser's0.5% component reconciliation; all seven boundary cases pass.

`test_same_acquisition_discriminator.py` additionally combines different acquisitions while remaining within0.5% tolerance. It fails on frozen candidate2 (`acq-discriminator-red-normal.*`) and passes on final normal/O (`acq-discriminator-final-*`). This proves the acquisition check is exercised independently of the sum check. Its exact fixture SHA256 is in `FINAL-RECEIPT.json`.

## Coverage, policy and limits

Actual local producer/client capture, CBK parser, receipt sealing, record parser, writer, query qualification and unwrapped API consumer execute. Only PDF page-text extraction is controlled; source bytes/figures are explicit synthetic fixtures, not claims about official financial facts. No runtime receipt capability is fabricated by a test.

Bounded hostile cases include metadata-only refresh claims, serialized receipts, changed acquisition fields, normalized-value mismatch, receipt already bound to another document, mixed acquisitions, and a complete valid new acquisition. Invalid inputs preserve old stock; valid fresh stock replaces it, retains unobserved GDP and clears the derived ratio. Neither-source changes preserve prior values/evidence/ratio; fresh GDP recomputes against retained raw-KES stock.

The WB-only extra year does not create an unsupported debt-stock year. Legacy fixture bootstrap remains unverified stock authority; these are deliberate baseline/no-new-year boundaries, not defects requiring invented evidence. Current acquisition and byte-retention qualification remain separate; the review does not strengthen or claim a new retention gate.

One imported prior control still expected fixture-only for no-CBK/live-GDP. That stale expectation produced exactly1 failure/91 passes per mode (`legacy-expectation-*`). Only its expected mode changed to partial, as required by the reviewed repair; no assertion was removed. Original bytes and exact hashes/edit are retained in `prior-controls/ADAPTATION.json` and `test_gdp_matrix.original.py.bytes`.

SQLite with test JSONB adaptation was used; no PG/concurrency or HTTP/cache/lifespan/browser acceptance is claimed. All project execution used cached image571e327e…, networknone,1CPU/1GiB/256PIDs. Local generation, native financial, media and supervisor flags plus AUTO_SEEDER were false. No product edits or production/provider/paid/hosted actions, uploads, publication or workers occurred.

## Replay and cleanup

See `REPLAY.md`. Exact commands, exit0 receipts and JUnits are pinned. All owned `pr860-debt-*` containers are absent; no PG or credentials were created. Shared `admin-redesign-pg`, `admin-redesign-node` and root `pr860-review-tools` are preserved. See `CLEANUP.json`. No actionable issue remains in the exercised debt scope; this is not acceptance of unrelated fiscal work or production deployment.

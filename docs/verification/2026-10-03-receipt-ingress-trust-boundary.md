# Receipt ingestion trust boundary — #137

## Scope and reproduced baseline

This local fix starts at combined integration commit
`1e2c2be9dcbadcc7aa97b16b8baceae22cc01dc6` (the same tree as `6e3936d`).
That pre-fix #137 integration includes the new qualification reader. These
findings do not assert that deployed main, which lacks that reader, already
publishes the same incorrect qualification.

The unchanged independent `REMAINING_COMBINED_PRODUCER_READER_PROBE_V3.py`
reproduced an ordinary configured economic JSON payload manufacturing a
successful acquisition, parser manifest and Extraction without retained source
bytes. The actual generic economic and exact verification handlers returned
`verified`. Its refusal control was red at the frozen baseline; the shipped
`test_configured_json_never_self_certifies_nonexistent_bytes` was independently
red against that same baseline too.

Two related controls were proved red while deliberately removing only their
new boundary: cached/changed PDF parse outputs could certify cells against
unchanged PDF bytes (three failures); copying and resealing an existing source
manifest could change acquired 7 into public verified 99 (two failures). The
root independently reproduced the two resealing failures and validated the
explicit early refusal on the fix. These are #137 integration findings.

## Runtime contract

`CapturedReceipt` is a runtime acquisition capability produced by actual byte
capture/readback. Its authority is absent from JSON and pickle. Deepcopy keeps
the original immutable acquisition/manifest fingerprints and source binding;
it cannot bless a changed envelope. Ordinary dictionaries, exported exact
Extraction references, forged check flags and changed envelopes preserve the
financial observation but cannot create or reuse stronger receipt authority.

Typed API/web/PDF source parsers annotate an unsealed acquisition, parse their
actual input and seal the complete source observation manifest. Copying refuses
a sealed receipt or any preexisting manifest; sealing refuses resealing.
CBK HTML explicitly binds the exact decoded text to the captured input bytes.
The source manifests still bind raw value/unit, identity, locator and supported
scale/rounding operations independently of the normalized row.

At persistence, a sealed acquisition cannot change its source document ID,
country, publisher or URL. Retained bytes are read back again before storing
the immutable Extraction metadata. Missing/corrupt store objects remain
qualified, with explicit failure metadata. Source bodies are never stored in
JSON or read by public handlers.

The measured 25-observation positive uses one store put, one capture read and
one persistence read, with one Extraction. Metadata qualification adds zero
store reads. Memoization shares the immutable manifest per acquisition rather
than multiplying source-body reads by row or measure.

## Ingress coverage and cache behavior

The shared `persist_evidence` boundary covers economic indicators, national
GDP/poverty, revenue, debt timeline (including its independent GDP source
document) and national loan evidence. `bind_pdf_evidence` covers county/national
budget and pending-bills writers. No public reader, DTO, model or migration was
changed. Revenue writer placement is left to the separate integration change.

Fresh PDF parse results have a nonserialized source digest and immutable record
snapshot. County budget, national budget page text and county payables carry
that result to the PDF builder. JSON cache hits and changed fresh results retain
their existing values and skip the expensive reparse, but cannot seal new source
claims. No historical reparse or backfill is implied.

API HTTP cache reuse, cold client reopen, and forged cache sidecar/body controls
prove that a cached observation has no fresh response status or acquisition
time. PDF sidecar JSON likewise cannot restore network acquisition authority.
Genuine source acquisitions continue to verify; owned cached/local byte fixtures
remain qualified when transport is unknown. Zero and missing interest values
retain their established meaning. Wrong source periods refuse promotion.

IDS supplies annual USD inputs without a complete independently bound FX operand
or a genuine persisted measurement date for the KES loan. The unsupported
normalized KES envelope is omitted. Quantities, row source document and NULL
interest are unchanged; the declared annual USD source period and precise
limitations are retained as `source_note` in exact provenance. Actual loan and
exact verification handlers return the same historical qualified association,
without an invented as-at date or contradictory financial assertion.

## Executed verification

- Unchanged independent V3 on the final fix: **32 passed**, seven existing
  serialization warnings. Its PDF cases use the retained actual BROP/CBIRR
  source artifacts; no new publisher acquisition is claimed.
- Final typed producer/cache/download/IDS suite: **170 passed, 5 skipped**,
  three existing deprecation warnings. Skips require an owned disposable
  PostgreSQL via `AUDIT_TEST_POSTGRES_URL`. All three retained actual PDF
  controls ran with `PDF_EVIDENCE_REAL_BROP` and `PDF_EVIDENCE_REAL_CBIRR`.
- Earlier affected producer/public-handler/financial-guard sweep: **803 passed,
  56 existing gated skips**, six warnings. This preceded the last resealing
  guard and IDS disclosure change; the final 170-case suite covers those edits.
- New shipped trust controls include actual handler positives, JSON/pickle and
  exact-ref replay, mutation and resealing, deleted/corrupt/missing stores,
  wrong periods, API cache cold/reuse/poisoned sidecars, PDF parse-cache poisoning,
  measured multirow storage calls, real retained API/web writer roundtrips,
  and 22 unchanged IDS loan amounts through both public and exact handlers.
- Critical flake8 (`E9,F63,F7,F82`) on seeding and the changed helper/tests:
  **0 findings**. `git diff --check` is clean.

Logs from this local run are `/tmp/receipt-ingress-baseline-red.log`,
`/tmp/receipt-ingress-shipped-baseline-red.log`,
`/tmp/receipt-ingress-cache-red.log`,
`/tmp/receipt-ingress-reseal-shipped-red.log`,
`/tmp/receipt-ingress-independent-final-after-review.log`,
`/tmp/receipt-ingress-final-targeted.log` and
`/tmp/receipt-ingress-final-producers.log`.

Durable production retention/adoption and hosted/full integration gates remain
with the coordinator. This run did not access production, credentials, GitHub,
Actions or deployments. Known embedded KRA publisher-chain and independent IDS
FX/period limits remain honest qualifications; no new duplicate issue is filed.

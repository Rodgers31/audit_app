# Optional Supabase runtime preparation (#137)

Prepared against main `2ed370312e7aa4f9c4ad6d91e8d5e9dbd6e7be93` after PR #495. The owner selected preparation for the existing project `xznjxwrkbkahwtnbstbj`. No provider requests, bucket creation, access changes or deployment were performed. #137 remains open pending actual durable acceptance.

## Runtime contract

`ReceiptStore.put/read` remains provider-neutral. The default is the existing local adapter (`storage_scope=local`). Explicit Supabase selection binds regular HTTP, streamed PDF and PDF evidence paths to the remote adapter (`storage_scope=supabase_private`). Missing/invalid durable configuration fails client construction without local fallback. Retention outages preserve qualified observations with explicit missing-byte evidence.

The adapter uses the existing httpx dependency: HTTPS hosted project endpoints only, immutable `receipts-v1/chunks/{prefix}/{part_sha256}` and `receipts-v1/manifests/{prefix}/{whole_sha256}` keys, `x-upsert=false`, authenticated GET, no redirects or environment proxies, confirmed bucket identity and `public=false`, bounded nonempty bytes, declared-length checks and SHA256 readback. Duplicate insertion requires exact readback; corruption refuses without overwrite. Provider error bodies are discarded and transport exception contents suppressed before receipt metadata/logging. There is no bucket provisioning, public URL, signed URL, listing, update, delete or lifecycle API.

Every logical source, including a small JSON/HTML response, has a separate versioned manifest. Source bytes are never parsed or guessed to be manifests. A manifest declares version/type, the requested whole SHA256 and total size, part count, and ordered part indices/digests/sizes. The reader validates its complete shape, exact sizes/count/sum, strict integer types and lowercase hashes before downloading any part, then checks every part and the reconstructed whole source. Duplicate JSON fields refuse; legitimate repeated source chunks can reuse a content-addressed key, while malicious substitution/reordering cannot pass the requested whole SHA. The manifest is at most 64 KiB, there are at most 64 parts, and the logical source is at most 64 MiB (also subject to the chosen logical cap and 64 × chosen part cap). Each part is at most 32 MiB by default. Writes verify parts before inserting the manifest last; interrupted attempts can leave orphan chunks, but cannot claim a complete retained source. Changing the part cap after retaining a source can make its immutable existing segmentation incompatible: do not overwrite/resegment an existing manifest; plan cap changes and recovery explicitly.

Modern server keys go in `apikey`. Such keys grant **full-project service_role access and bypass RLS**. A dedicated key is separately revocable, but is not bucket-scoped. This adapter accepts modern `sb_secret_` keys only. Resolve `RECEIPT_SUPABASE_SECRET_KEY` through the existing `config.secrets.get_secret` server backend, with its existing backend behavior. Never supply the key to Vercel/frontend/browser code. Its live availability is untested.

| Variable | Supabase configuration |
| --- | --- |
| `SEED_RECEIPT_STORAGE_BACKEND` | `supabase` (default `local`) |
| `SEED_RECEIPT_SUPABASE_URL` | `https://xznjxwrkbkahwtnbstbj.supabase.co` |
| `SEED_RECEIPT_SUPABASE_BUCKET` | Owner-approved private bucket identifier, pending |
| `SEED_RECEIPT_MAX_BYTES` | Explicit logical source cap ≤67108864 bytes |
| `SEED_RECEIPT_PART_MAX_BYTES` | Optional positive integer physical chunk cap ≤33554432 bytes; blank/unset defaults to 32 MiB |
| `SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS` | Positive finite seconds ≤120; default 30 |
| `RECEIPT_SUPABASE_SECRET_KEY` | Dedicated server secret in the configured secret backend |

The deadline spans metadata/upload/readback, with remaining-budget httpx timeouts and chunk checks. An in-flight stalled chunk may additionally wait for the read-gap timeout established at request start, bounded by that request's remaining budget. The domain's existing wall-clock cap remains the outer bound. No automatic storage retry is introduced.

Optional `put_and_read` returns verified reconstructed bytes and avoids redundant capture downloads; direct `put` also verifies. Capture checks digest and byte equality. For N parts, capture performs N chunk GETs plus one manifest GET; first immutable Extraction persistence independently performs one manifest GET plus N chunk GETs. That is two whole-source byte volumes plus two small manifest byte volumes. Subsequent facts sharing the same source/acquisition/seal/extractor reuse that session's Extraction without any additional storage GET. Fresh reads always reach storage. Public handlers/serializers consume metadata only.

## Capacity and owner gates

Root's read-only account inspection on 2026-10-07 reported Auditors **Free**, cycle Sep 23–Oct 23: egress 10.259/5 GB (205%), database 0.091/0.5 GB (18%), storage 0/1 GB, no buckets. The dashboard warned of restrictions Oct 8 if excess egress remained unresolved. Existing issue #481 tracks that egress problem; no duplicate was created. Empty storage usage does not establish operational availability under this restriction.

Confirm current restriction/capacity before enabling uploads. The [pricing page](https://supabase.com/pricing) lists a Free per-object upload cap of 50 MB. Root's retained annual county PDF inventory measured **53561211 bytes**, above both 50,000,000 and 52,428,800 bytes. Chunking preserves those exact logical bytes and whole SHA256 while defaulting to physical objects at most 32 MiB; bucket capacity checks apply to actual chunks/manifests, not the logical PDF size. A larger file alone does not force a Pro plan, but the **1 GB Free storage allowance and existing egress restriction still apply**. Above-logical-cap sources retain explicit missing-byte qualification; never truncate or fabricate success. Supabase [recommends resumable uploads above 6 MB](https://supabase.com/docs/guides/storage/uploads/standard-uploads). Bounded standard-upload chunks still need representative live acceptance under the chosen whole-operation timeout before rollout.

Owner decisions remain: bucket name/region, storage and egress budget/alerts, approved production writers, key rotation, referenced-edition retention, orphan grace period, independent recovery copy, recovery objectives, inventory reconciliation and missing-object restoration. No GC is implemented. Restrict other privileged writers/manual overwrite/deletion: no-overwrite requests are not provider-level WORM. Private-bucket checks can race administrative access changes, requiring operational controls and monitoring. PostgreSQL metadata backups do not back up object bytes.

The actual nightly producer is `.github/workflows/seed.yml`, `python -m seeding.cli seed --all`. Its seed-job environment binds the optional repository variables (including part cap) and server secret, defaulting to local mode. Empty optional caps parse as unset; Supabase requires an explicit logical cap and defaults the part cap to 32 MiB. Part cap inputs reject booleans, floating-point values and noninteger environment strings. The receipt secret is scoped to the seed job. Configuring Render alone does not configure this producer. No workflow trigger, repository variable/secret, Actions run or deployment was changed.

## Guarded live acceptance after approval

Merge can retain the default `SEED_RECEIPT_STORAGE_BACKEND=local` with no provider variables configured. Activation is a separate operation after capacity/access/recovery approval: configure the approved project/bucket and server secret, logical `SEED_RECEIPT_MAX_BYTES=67108864`, and pin `SEED_RECEIPT_PART_MAX_BYTES=33554432` (32 MiB) before the first retained receipt. Select `SEED_RECEIPT_STORAGE_BACKEND=supabase` only for the approved prospective acceptance runtime. Stop activation on any current account restriction, unapproved quota/egress, public/unknown bucket, invalid cap/configuration, storage timeout, nonmatching/missing manifest/part, unexpectedly successful public/anon access, or failed restart/recovery gate. Explicit Supabase configuration failure never falls back quietly to local.

Rollback to `SEED_RECEIPT_STORAGE_BACKEND=local` pauses prospective durable retention and emits `storage_scope=local` for new acquisitions. Local storage is not a deployed durability claim. Existing remote manifests/chunks remain intact; rollback does not delete, rewrite or reseal historical receipts. Keep the part cap pinned for the lifetime of existing manifests and record any later approved format/cap transition.

Run from the repository root in an approved backend environment, with the above variables and server secret manager configured. The CLI does not load dotenv. Keep secrets out of command arguments, shell history and captured output. These commands are instructions; **they have not been executed against Supabase**.

```sh
python scripts/verification/verify_durable_receipt.py \
  --expected-project-ref xznjxwrkbkahwtnbstbj \
  --expected-bucket "$SEED_RECEIPT_SUPABASE_BUCKET" \
  put --file backend/tests/fixtures/worldbank_gdp_2022.json \
  --allow-supabase-write
```

Preserve only the digest/byte_size/project/bucket/status report. Stop that process, restart the approved runtime/container, and run in a fresh process using the returned digest and integer size:

```sh
python scripts/verification/verify_durable_receipt.py \
  --expected-project-ref xznjxwrkbkahwtnbstbj \
  --expected-bucket "$SEED_RECEIPT_SUPABASE_BUCKET" \
  read --digest RETURNED_SHA256 --expected-size RETURNED_BYTE_SIZE
```

Repeat put with unchanged bytes: same digest, no overwrite. Exercise a representative large PDF and a changed edition: distinct digest for changed bytes. Confirm public/anon denial and bucket privacy. Retain prospective parser/SQL/public-handler evidence for exact precision, NULL/zero, qualifications, shared Extraction request counts, and zero public-handler source-body reads. Do not backfill or reseal historical observations.

Recovery drill: choose an owner-approved disposable acceptance object, retain an independent copy and metadata, and follow the approved plan. This CLI cannot delete/corrupt storage. Confirm missing/corrupt readback refusal, restore only matching digest/size bytes, and read from a fresh runtime. Record current quota/egress, restart and recovery evidence before declaring durable acceptance.

## Local evidence and references

`backend/tests/test_supabase_receipt_store.py` executes a file-backed local REST simulation with synthetic credentials and exclusive inserts. Fresh boundary/adapter reads retained files; hostile configuration, metadata, redirects, corruption, missing/partial/oversized bodies and exceptions are exercised. This establishes no provider durability, access, quota, billing, restart or recovery success. Reproduce:

The prior single-object implementation's focused run on 2026-10-07 was **204 passed, 8 skipped, 3 existing warnings in 2.21s**. The chunked revision adds strict manifest/part/physical-cap controls and adapts traffic assertions. Five existing skips require disposable PostgreSQL; three require retained real BROP/CBIRR PDF paths. Actual SQLite ORM execution retains twenty GDP facts sharing one Extraction: the one-part source causes two manifest GETs and two chunk GETs (capture and first persistence), with no additional reads for the other facts. The actual CLI subprocess refuses an unconfigured/local backend.

The chunked revision's final focused ten-file author suite completed **267 passed, 8 skipped, 3 existing warnings in 2.41s**. The actual retained annual county PDF (53561211 bytes, SHA256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`) passed exact local put/readback and a fresh OS-process read against a file-backed REST simulation. Physical chunks were 33554432 and 20006779 bytes, plus a 384-byte manifest. Put made three insert-only POSTs and read two chunks plus one manifest; the fresh read made no POSTs and read those same two chunks and manifest. Each phase transferred 53561211 source bytes plus 384 manifest bytes. The harness created only its own temporary object files and removed them afterward. Synthetic credentials and MockTransport were used throughout; this is **not provider durability, plan availability, egress or deployed acceptance evidence**.

A second run measured whole-process macOS peak RSS of **403701760 bytes during put** and **296435712 bytes during fresh read**. Those measurements include Python, fixture/request copies and verification overhead; they are not production capacity measurements. This bytes-returning Protocol and the acquisition/parser paths retain multiple bodies in memory. Measure peak memory on the actual seeder/parser host and reject activation if its approved headroom is insufficient; chunked uploads solve the physical object limit without establishing memory availability.

Independent execution found delayed-EOF acceptance and an unexpected same-type storage exception leaking its message. Both were corrected with runtime regressions. Removing each fix **in memory only** made its actual new regression fail (late EOF: did not raise; same-type redaction: assertion failure). Live provider acceptance is still pending; the parent review owns final independent verification and source hashes.

Independent chunk execution also found that a tiny configured part cap allocated excessive source slices before refusing the 64-part ceiling. The adapter now computes the count and refuses before allocating any parts. The small SliceProbe regression passes with the fix and fails against an in-memory version of the old allocation-first guard, without allocating a massive test payload. This correction belongs to #137's adapter acceptance; no duplicate issue is needed.

A deeply nested manifest within the byte ceiling previously raised raw RecursionError; manifest and bucket JSON decoder errors now normalize to fixed storage refusal messages. The actual nested-manifest regression passes and fails with that catch removed in memory. A separate reviewer reported six final chunk control groups passing against adapter SHA256 `1825e3c1b3d4441abdf32f0e0dc5a7020a751fc48441475a7e50d163f635bfed`, including the original deep-JSON probe and CLI refusal JSON, pre-allocation guard, the real retained PDF in separate CLI processes, actual ORM/public-handler integration and no public-handler source-body GETs. All of this execution used local simulated boundaries; live durable gates remain pending.

```sh
python -m pytest \
  backend/tests/test_chunked_receipt_store.py \
  backend/tests/test_receipt_seed_workflow_binding.py \
  backend/tests/test_supabase_receipt_store.py \
  backend/tests/test_durable_receipt_acceptance_cli.py \
  backend/tests/test_response_receipts.py \
  backend/tests/test_seeding_http_client.py \
  backend/tests/test_review_495_receipt_boundaries.py \
  backend/tests/test_receipt_ingress_trust.py \
  backend/tests/test_prospective_pdf_evidence.py \
  backend/tests/test_pdf_resume.py -q -rs
```

Official sources inspected 2026-10-07: [uploads/duplicate inserts](https://supabase.com/docs/guides/storage/uploads/standard-uploads), [private authenticated downloads](https://supabase.com/docs/guides/storage/serving/downloads), [key semantics/headers](https://supabase.com/docs/guides/api/api-keys), [storage access](https://supabase.com/docs/guides/storage/security/access-control). Live acceptance remains pending.

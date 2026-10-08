# Optional Supabase runtime preparation (#137)

Prepared against main `2ed370312e7aa4f9c4ad6d91e8d5e9dbd6e7be93` after PR #495. The owner selected preparation for the existing project `xznjxwrkbkahwtnbstbj`. No provider requests, bucket creation, access changes or deployment were performed. #137 remains open pending actual durable acceptance.

## Runtime contract

`ReceiptStore.put/read` remains provider-neutral. The default is the existing local adapter (`storage_scope=local`). Explicit Supabase selection binds regular HTTP, streamed PDF and PDF evidence paths to the remote adapter (`storage_scope=supabase_private`). Missing/invalid durable configuration fails client construction without local fallback. Retention outages preserve qualified observations with explicit missing-byte evidence.

The adapter uses the existing httpx dependency: HTTPS hosted project endpoints only, insert-only content-addressed `sha256/{prefix}/{digest}` keys, `x-upsert=false`, authenticated GET, no redirects or environment proxies, confirmed bucket identity and `public=false`, bounded nonempty bytes, declared-length checks and SHA256 readback. Duplicate insertion requires exact readback; corruption refuses without overwrite. Provider error bodies are discarded and transport exception contents suppressed before receipt metadata/logging. There is no bucket provisioning, public URL, signed URL, listing, update, delete or lifecycle API.

Modern server keys go in `apikey`. Such keys grant **full-project service_role access and bypass RLS**. A dedicated key is separately revocable, but is not bucket-scoped. This adapter accepts modern `sb_secret_` keys only. Resolve `RECEIPT_SUPABASE_SECRET_KEY` through the existing `config.secrets.get_secret` server backend, with its existing backend behavior. Never supply the key to Vercel/frontend/browser code. Its live availability is untested.

| Variable | Supabase configuration |
| --- | --- |
| `SEED_RECEIPT_STORAGE_BACKEND` | `supabase` (default `local`) |
| `SEED_RECEIPT_SUPABASE_URL` | `https://xznjxwrkbkahwtnbstbj.supabase.co` |
| `SEED_RECEIPT_SUPABASE_BUCKET` | Owner-approved private bucket identifier, pending |
| `SEED_RECEIPT_MAX_BYTES` | Explicit positive cap ≤67108864 bytes AND actual account/bucket caps |
| `SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS` | Positive finite seconds ≤120; default 30 |
| `RECEIPT_SUPABASE_SECRET_KEY` | Dedicated server secret in the configured secret backend |

The deadline spans metadata/upload/readback, with remaining-budget httpx timeouts and chunk checks. An in-flight stalled chunk may additionally wait for the read-gap timeout established at request start, bounded by that request's remaining budget. The domain's existing wall-clock cap remains the outer bound. No automatic storage retry is introduced.

Optional `put_and_read` returns verified bytes and avoids redundant capture downloads; direct `put` also verifies. Capture checks digest and byte equality. A capture performs one full object GET; first immutable Extraction persistence performs one independent full GET. Subsequent facts sharing the same source/acquisition/seal/extractor reuse that session's Extraction. Fresh adapter reads always hit storage. Public handlers/serializers continue to consume metadata only.

## Capacity and owner gates

Root's read-only account inspection on 2026-10-07 reported Auditors **Free**, cycle Sep 23–Oct 23: egress 10.259/5 GB (205%), database 0.091/0.5 GB (18%), storage 0/1 GB, no buckets. The dashboard warned of restrictions Oct 8 if excess egress remained unresolved. Existing issue #481 tracks that egress problem; no duplicate was created. Empty storage usage does not establish operational availability under this restriction.

Confirm current restriction/capacity before enabling uploads. The [pricing page](https://supabase.com/pricing) lists a Free upload cap of 50 MB; the adapter's 64 MiB ceiling **does not claim Free compatibility**. Measure the largest real PDF and configure the minimum approved account, bucket and adapter limit. Above-limit documents retain explicit missing-byte qualification; never truncate or fabricate success. Supabase [recommends resumable uploads above 6 MB](https://supabase.com/docs/guides/storage/uploads/standard-uploads). This bounded standard-upload adapter needs representative large-PDF live acceptance under the chosen timeout before rollout.

Owner decisions remain: bucket name/region, storage and egress budget/alerts, approved production writers, key rotation, referenced-edition retention, orphan grace period, independent recovery copy, recovery objectives, inventory reconciliation and missing-object restoration. No GC is implemented. Restrict other privileged writers/manual overwrite/deletion: no-overwrite requests are not provider-level WORM. Private-bucket checks can race administrative access changes, requiring operational controls and monitoring. PostgreSQL metadata backups do not back up object bytes.

The actual nightly producer is `.github/workflows/seed.yml`, `python -m seeding.cli seed --all`. Its seed-job environment now binds these optional repository variables and the server secret, defaulting to local mode. An empty optional byte cap parses as unset locally; selecting Supabase without a cap refuses construction. The receipt secret is scoped to the seed job. Configuring Render alone does not configure this producer. No workflow trigger, repository variable/secret, Actions run or deployment was changed.

## Guarded live acceptance after approval

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

Final focused author run on 2026-10-07: **204 passed, 8 skipped, 3 existing warnings in 2.21s**, selecting new adapter/CLI/workflow binding files plus existing response receipts, seeding HTTP, PR #495 receipt boundaries, receipt ingress, prospective PDF evidence and PDF resume tests. Five skips require disposable PostgreSQL; three require retained real BROP/CBIRR PDF paths. Actual SQLite ORM execution retained twenty GDP facts sharing one Extraction with exactly two full source GETs total (capture and first persistence), with no additional reads for the other facts. The actual CLI subprocess refused an unconfigured/local backend.

Independent execution found delayed-EOF acceptance and an unexpected same-type storage exception leaking its message. Both were corrected with runtime regressions. Removing each fix **in memory only** made its actual new regression fail (late EOF: did not raise; same-type redaction: assertion failure). Live provider acceptance is still pending; the parent review owns final independent verification and source hashes.

```sh
python -m pytest backend/tests/test_supabase_receipt_store.py -q
```

Official sources inspected 2026-10-07: [uploads/duplicate inserts](https://supabase.com/docs/guides/storage/uploads/standard-uploads), [private authenticated downloads](https://supabase.com/docs/guides/storage/serving/downloads), [key semantics/headers](https://supabase.com/docs/guides/api/api-keys), [storage access](https://supabase.com/docs/guides/storage/security/access-control). Live acceptance remains pending.

# Optional private R2 source receipts (#137)

Prepared against `77a68925756ade06e06f31ee4347e992e772ace0`. This change adds a server adapter and guarded acceptance command. The default remains `local`. No R2 subscription, bucket, token, repository setting, Actions run or deployment was changed by this preparation. At preparation, the coordinator reported R2 activation awaiting the owner's acceptance of recurring usage terms. Supabase Pro had been confirmed separately; its adapter remains supported. Provider activation and live acceptance are separate gates.

## Exact target and access

Proposed account: `6929fa03fad58c2f93c70196ec498c69`. Proposed dedicated bucket: `audit-source-evidence-v1`, **Standard** class, `default` jurisdiction. A location hint is placement guidance, not a residency guarantee. Select EU jurisdiction only if residency requires it, record that decision, and change both the endpoint and expected jurisdiction. R2's free allowance applies to Standard storage; no Frankfurt-specific free-tier advantage is assumed. Internet egress from R2 is free; upstream host transfer charges and latency still need measurement.

Keep the managed `r2.dev` URL disabled and every custom domain disabled. Do not add browser access, public Workers routes, social-media bindings or lifecycle deletion rules for this bucket. The social S3 port is a separate contract and is unchanged.

Create two separately revocable credentials only after the owner confirms their exact exposure in the browser:

| Credential | Permission and exposure |
| --- | --- |
| Object credential | Dedicated **Object Read & Write**, restricted to this one bucket. Its S3 credentials can overwrite and delete objects; the adapter never invokes those operations. This is application insertion discipline, not provider WORM. |
| Control credential | Separate **Workers R2 Storage Read** scoped to this account. This reads bucket configuration **and objects across the account**; Cloudflare does not make this control permission bucket limited. It is used only for three read-only privacy checks in this adapter. |

The adapter signs S3 requests with explicit credentials through the already declared boto3/botocore dependency. It never uses a default credential chain, arbitrary endpoint, public SDK or browser token. The separate control token goes only to the fixed `api.cloudflare.com` account/bucket route; the S3 secret never goes there. Redirects and environment proxies are disabled. Credentials are resolved with the existing server `config.secrets.get_secret` backend; preserve its documented behavior and provision host secrets explicitly. Keep secrets out of command arguments, logs, artifacts and frontend variables. Rotate Render and GitHub credentials independently where practical. Cross-host availability is untested.

## Privacy and byte contract

Before each logical put or read, one shared deadline covers these three bounded control GETs: bucket metadata (exact name, Standard class and configured jurisdiction), managed domain (explicit `enabled=false`) and custom domains (a list with explicit `enabled=false` on every entry). Successful control responses must explicitly carry `success=true`, an empty `errors` array and a result object. Missing, malformed, contradictory-error, duplicate-field, inaccessible or public metadata refuses **before any object IO**. Neither successful HEAD nor authenticated object GET proves privacy. This check establishes the direct public-domain configuration at that moment; it cannot prove absence of an independent Worker route or stop privileged administrative changes after the check. The coordinator must inspect bindings and control who can change exposure.

The source digest remains SHA256 of the exact bytes consumed by the parser (`response.content` for HTTP; acquired PDF bytes for PDF). No numeric values, evidence statuses, parser schema or historical receipts change. Storage failure keeps the existing explicit missing-byte qualification.

Objects use `receipts-v1/chunks/{digest[:2]}/{part_sha256}` and `receipts-v1/manifests/{digest[:2]}/{whole_sha256}`. The shared version-one codec preserves the Supabase wire bytes. Every source, including JSON, has a separate manifest; bytes are never guessed to be a manifest. Bounds remain 64 MiB logical bytes, 32 MiB per part, 64 parts, and 64 KiB manifest. The pinned chosen part cap must remain compatible with existing manifests.

Each signed PUT includes `If-None-Match: *`. Cloudflare documents conditional PutObject support. Success or precondition failure (412) still requires exact readback. Wrong existing bytes refuse; no overwrite or delete is attempted. Parts are checked first, then the manifest is inserted last and checked. Interrupted writes may leave orphan chunks; they cannot certify complete evidence. Fresh reads validate the entire manifest before part downloads, verify each part's size and digest, and verify the reconstructed whole digest. Duplicate JSON fields and reordered/substituted parts refuse.

One total deadline spans manifest preparation, privacy checks, signing, uploads and bounded identity-encoded readbacks. No automatic retry is added. Deadline checks occur before requests, on headers, on streamed chunks, at EOF and before success. An in-flight stall can wait for its read-gap timeout established at request start, up to that request's remaining budget; the seeder's existing domain wall-clock cap remains the outer bound. This is not a hard cancellation guarantee. Runtime holds source, part slices and reconstructed bytes in memory: representative PDF throughput and host headroom must pass before activation.

## Configuration and guarded acceptance

The actual nightly producer is `.github/workflows/seed.yml`, the seed job's `python -m seeding.cli seed --all`. The new mappings are scoped to that job; adding mappings does not create secrets, enable R2 or run Actions. Render configuration alone does not configure the nightly producer.

| Setting | Proposed value |
| --- | --- |
| `SEED_RECEIPT_STORAGE_BACKEND` | `r2` only in the approved acceptance runtime; otherwise `local` |
| `SEED_RECEIPT_R2_ACCOUNT_ID` | `6929fa03fad58c2f93c70196ec498c69` |
| `SEED_RECEIPT_R2_BUCKET` | `audit-source-evidence-v1` |
| `SEED_RECEIPT_R2_JURISDICTION` | `default` |
| `SEED_RECEIPT_MAX_BYTES` | `67108864` explicit logical cap |
| `SEED_RECEIPT_PART_MAX_BYTES` | `33554432`, pinned before first retention |
| `SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS` | `30` default; choose measured finite budget ≤120 |
| `RECEIPT_R2_ACCESS_KEY_ID` / `RECEIPT_R2_SECRET_ACCESS_KEY` | Dedicated bucket object credential via the server secret backend |
| `RECEIPT_R2_CONTROL_TOKEN` | Separate account-wide read control token via the server secret backend |

The CLI requires matching backend/account/bucket/jurisdiction before secret lookup, and separate write consent. It loads no dotenv. After approved provider setup, run these instructions in a private backend environment; they are **not a record of live execution**:

```sh
python scripts/verification/verify_durable_receipt.py \
  --expected-backend r2 \
  --expected-account-id 6929fa03fad58c2f93c70196ec498c69 \
  --expected-bucket audit-source-evidence-v1 \
  --expected-jurisdiction default \
  put --file backend/tests/fixtures/worldbank_gdp_2022.json --allow-r2-write
```

Stop the process, restart the approved host/container, then read in a fresh process using its reported digest and integer byte size:

```sh
python scripts/verification/verify_durable_receipt.py \
  --expected-backend r2 \
  --expected-account-id 6929fa03fad58c2f93c70196ec498c69 \
  --expected-bucket audit-source-evidence-v1 \
  --expected-jurisdiction default \
  read --digest RETURNED_SHA256 --expected-size RETURNED_BYTE_SIZE
```

Retain a safe report containing target, code commit, digest, bytes, elapsed time, and outcome, never credentials or source bodies. Repeat identical put (same digest), a changed edition (distinct digest), and the retained representative 53,561,211-byte PDF. Check unauthenticated denial separately without publishing a URL. Exercise the actual source parser, disposable SQL persistence and metadata reader, including a storage refusal that preserves qualification. No public request should fetch source bytes. Restart, host migration and independent recovery are separate from immediate byte matching; the CLI reports this scope.

## Budget, recovery and decision

[Official Standard pricing](https://developers.cloudflare.com/r2/pricing/) inspected October 7, 2026 lists 10 GB-month storage, 1 million Class A and 10 million Class B operations free monthly; above that, $0.015/GB-month, $4.50/million Class A, and $0.36/million Class B. Direct internet egress is free. Other Cloudflare products and upstream hosts can charge separately. Free allowances do not impose a spending ceiling; establish alerts and an owner-approved ongoing budget.

For N parts, put/readback uses N+1 PUTs and N+1 GETs, plus three control reads. Fresh recovery uses N+1 object GETs plus three control reads; initial Extraction persistence performs its own independent read. Repeated editions and failed attempts can accumulate orphan chunks. Content reuse reduces stored bytes but does not remove request charges. Keep referenced editions; no automatic GC is provided.

Record bucket jurisdiction, logical/part caps, manifest version, digest inventory and acquisition metadata in a private recovery inventory. Maintain a separately administered copy of manifests and every referenced chunk. A database backup alone is insufficient. Test recovery in a separate private target using restored exact objects and fresh-process hash/size verification. Define retention, backup cadence and recovery objectives; do not count R2 as independent backup of itself. Missing/corrupt objects stay qualified until exact recovery succeeds. Do not reserialize source bytes or overwrite an existing manifest to make a changed cap work.

Selecting `local` pauses prospective R2 retention and reports local scope; it does not delete remote objects or upgrade old receipts. Restore R2 only after its target/privacy/capacity checks pass. There is no implicit fallback from selected R2 to local or Supabase.

R2 adds useful low-cost capacity and avoids R2 internet egress charges for repeated large source readbacks. Supabase is already implemented and the owner has confirmed Pro; its live acceptance can proceed independently. R2 only improves this goal after billing activation, both credential exposures, private metadata and representative throughput/recovery are accepted. No broad replacement is required.

Official references: [S3 conditional support and unsupported public-access APIs](https://developers.cloudflare.com/r2/api/s3/api/), [token permissions](https://developers.cloudflare.com/r2/api/tokens/), [public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/), [bucket metadata](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/methods/get/), [managed-domain state](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/domains/subresources/managed/methods/list/), [custom-domain state](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/domains/subresources/custom/methods/list/).

## Local verification scope

Author execution passed **238 tests, zero skips** across `test_r2_receipt_store.py`, `test_supabase_receipt_store.py`, `test_chunked_receipt_store.py`, `test_durable_receipt_acceptance_cli.py` and `test_receipt_seed_workflow_binding.py`. The R2 tests exercise actual botocore signing and httpx requests at a simulated boundary, private metadata refusal before object IO, conditional conflicts, interrupted retry, exact fresh reconstruction, source capture, stream/deadline limits and credential-safe errors. A fixture generated from the exact pre-extraction `77a6892` Supabase source proves identical version-one wire bytes for five representative sources, alongside the existing hostile-manifest tests.

In-memory removal of each guard made its selected test fail: privacy preflight, signed conditional header, and EOF deadline. No source file was changed for these negative controls. The final author run used an allowlisted environment and disposable SQLite configuration, without inherited provider credentials. Existing dependency/runtime deprecation warnings remain. This proves local technical behavior; it does not establish real token permissions, actual private provider configuration, billing limits, host throughput, cross-host secret availability or disaster recovery. Independent review and provider acceptance remain separate.

Independent review reproduced a contradictory synthetic envelope (`success=true` with nonempty `errors`) certifying private readiness in the first candidate. The gate now requires an explicit empty errors array; 21 author controls cover absent, null, nonlist and nonempty errors at all three privacy steps. This is a malformed-boundary finding, not a claim that Cloudflare returns this response. The old exact source is preserved externally for independent red/green verification.

The final R2 adapter SHA256 `bac90f05c91218c5eaffccc4cb853d8f8ef880bff9a15cd58f5912887f107237` passed seven independent control groups with stable runtime/configuration/CLI/workflow hashes. The reviewer verified final-request SigV4 HMAC/body/conditional headers, insertion conflicts and manifest publication, 58 manifest mutations and baseline wire compatibility, privacy refusals, deadline/error controls, actual client/domain/disposable SQLite/public-reader flow, and the representative PDF through separate guarded CLI put/read processes. The simulated parser flow produced 26 facts across three acquisitions; its public reader performed zero source-object GETs. The archived old errors-envelope gate accepted the exact contradictory control and performed four object requests; the final gate refused with zero object requests. No blocking adapter defect remained. These executions contacted simulated boundaries, not Cloudflare. Live capacity, permissions, throughput, host headroom and recovery remain pending.

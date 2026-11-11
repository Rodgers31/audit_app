# Nightly refresh v2 semantic evidence

Use the semantic importer with an existing owned PostgreSQL schema and an independently collected loopback transcript. It reclassifies stored jobs, reads the actual catalog revision, and derives the expected refresh context from the recomputed current-run report. The classifier checks the admitted and planned SHA against the source SHA and computes the plan digest from the supplied original. The v2 witness begins at or after the CLI completion recorded in that context.

```sh
python3 -B tools/nightly_acceptance_20261105/operational.py --semantic-local input.json \
  --backend-config /private/fixture/backend.json --signing-key-file /private/fixture/key \
  --require-refresh-v2
python3 -B tools/nightly_acceptance_20261105/ledger.py check-semantic-local input.json \
  --backend-config /private/fixture/backend.json --signing-key-file /private/fixture/key \
  --require-refresh-v2
```

Python uses the existing backend `cryptography` runtime. The verifier reads files and the owned read-only schema. The verification path sends zero HTTP requests.

## Packet and collection

Set `schema` to `nightly-semantic-local-input-v2` and use the same top-level fields as v1. Set `refresh` to a reference to the bundle below and `census` to a reference to the independent witness. Every artifact reference has the canonical relative `path`, byte `size`, and lowercase hex `sha256`. All references, including nested bundle references, resolve relative to the input directory.

The `nightly-refresh-v2-bundle-v1` object has five keys.

| Key | Original bytes |
| --- | --- |
| `schema` | Literal `nightly-refresh-v2-bundle-v1`. |
| `sealed` | The full ordered `REFRESH_HTTP_EVIDENCE_V2 ` lines from both original phase stdout streams. Retain the exact JSON text and terminating LF per line. |
| `state` | The exact producer `--state` file containing `state` and `signature`. |
| `backend_output` | The original complete backend phase `GITHUB_OUTPUT` bytes. |
| `pages_output` | The original complete pages phase `GITHUB_OUTPUT` bytes. |

The `nightly-refresh-local-witness-v2` object has these keys. Acquire the witness independently of the signed response objects.

| Keys | Observation |
| --- | --- |
| `schema`, `context` | Literal `nightly-refresh-local-witness-v2` and the exact five wire fields `source_sha`, `plan_sha256`, `run_id`, `run_attempt`, `schema_head`. Run and attempt are decimal strings. |
| `started_at`, `finished_at` | Collector wall-clock epoch seconds immediately before the backend phase and after the pages phase. Import within seven days of completion. |
| `backend_origin` | The exact HTTPS origin used for both backend calls, without a trailing slash. |
| `frontend` | Exact HTTPS `url`, independently observed serving `commit`, and `manifest_sha256` of the raw serving frontend manifest. Those manifest bytes must match the verifier checkout's manifest. |
| `backend_before`, `backend_after` | Each has the Linux `boot_id`, integer `pid_namespace_inode`, `supervisor`, sorted `workers`, and a stable `listeners` array. Process identities use `PID:start_ticks`. Collect each serving TCP listener's positive integer `port`, `inode`, and sorted `holders` from procfs. Account for all listener inodes on the serving ports, including sockets created with SO_REUSEPORT. |
| `generation`, `marker_identity` | Read the final marker file's 32-hex generation and its `[inode, mtime_ns, size]` from the serving namespace. |
| `backend_exit`, `pages_exit` | Exact integer child exit codes from the collector. Both must be zero. |

For an owned fixture, allocate a private directory and set the producer umask to `077`. Capture both phase outputs separately. Keep the key, the v2 witness, and every v2 bundle file private to the importing user. The importer holds bounded, owned, single-link no-follow descriptors and rechecks the same path bindings and bytes through consumption. Pass the existing signing secret as exact UTF-8 file bytes without an added newline. Keep the key and decrypted HTTP originals out of Git, exported receipts, terminal output, and shared storage. Destroy the disposable key and private raw request file after the scoped run.

The verifier authenticates each AES-256-GCM envelope using the domain-separated key derived from that secret, and authenticates the exact decoded HTTP request and response bodies separately. It binds the response to the original request digest and reconciles the exact reconstructed private JSONL bytes with the backend-prefix and full-transcript phase digests. A full success is one invalidation, bounded worker-status polls until the first complete adoption census, and one exact frontend acknowledgment. A fresh status poll can revisit a worker before coverage completes. Repeated request nonces, duplicated ciphertext records, missing phases, receipts after full worker coverage, and mismatched original markers refuse. Re-importing the same intact archival packet is a read-only verification of that same observation.

The workflow stores public ciphertext lines. Those lines alone cannot provide the independent witness, raw phase output files, or signed backend state required by this importer. Acquisition and custody of these originals need their own evidence. The signed request and response bind the bodies. Exact endpoint identity, HTTP status, original process observations, and terminal exits also rely on the collector. The shared signing key is available to the client and both servers.

## Verdict scope

A successful v2 import emits `nightly-semantic-local-observation-v2` with `OFFLINE_V2_HTTP_HMAC_AND_ACK_SEMANTICS_VERIFIED`. A recognized required-source hold can leave source completion red while the stored current-run observation and cache acknowledgment both qualify locally. Source retention remains in the per-job report and is independent of the refresh transcript digest. The local cache acknowledgment covers a single backend namespace and the frontend route's exact acknowledgment. The loopback test also observes the actual Next cache tags queued by the route.

The top-level verdict remains `LOCAL_SEMANTIC_OBSERVATIONS_ONLY_OPERATIONAL_GATES_PENDING`. Hosted attempt provenance, deployed topology and rendered values, fiscal and OAG source adoption, native/runtime admission and release remain held. The prepared and structural ledgers retain their pending verdicts. Historical v1 input and captures have their own local-only verdict and cannot satisfy `--require-refresh-v2`.

## Local qualification

The ciphertext and refusal suite is `tools/nightly_acceptance_20261105/test_acceptance_refresh_v2.py`. The end-to-end fixture is `tools/nightly_acceptance_20261105/test_acceptance_refresh_v2_loopback.py`. Run the latter alongside `backend/tests/test_refresh_current_run_postgres.py` so the canonical backend test configuration is loaded. Use an isolated Linux namespace, the two owned fixture databases described in the acceptance README, the backend qualification runtime, Node and OpenSSL. Set `REFRESH_V2_CACHED_FRONTEND` to a read-only directory containing the lock-matched frontend `node_modules` and `REFRESH_V2_FIXTURE_COMMIT` to the checkout commit. Run the same selection with normal and optimized Python. A skipped fixture provides no integration evidence.

# Issuer transport remediation — October 24, 2026

Issue: [#788](https://github.com/Rodgers31/audit_app/issues/788). Base: `dd776546a4b7b0962c69d5b3543a72046bdcae8b`. Isolated branch: `codex/oct24-issuer-transport`. Separate from authentication/security draft #790.

## Problem and resulting boundary

The old helper followed certificate-controlled URLs and redirects before trusting the returned chain. Its 16 KiB cap was a slice after a buffered download. Local mocks proved both boundaries; no private destination, metadata service or live publisher was contacted.

The helper now admits two reviewed CA files. HTTP/HTTPS AIA identifiers `ye2.i.lencr.org/` and `ye.i.lencr.org/` select `https://letsencrypt.org/certs/gen-y/int-ye2.der` and `https://letsencrypt.org/certs/gen-y/root-ye-by-x2.der`, respectively. Those exact HTTPS file URLs are also admitted. Other authorities, paths, credentials, ports, queries and fragments are refused before I/O. This mapping supports the existing KNBS YE2 → Root YE → ISRG Root X2 workaround. Issuer rotation requires review; unsupported issuers fail visibly.

Official chain and certificate identities: [YE2](https://letsencrypt.org/certs/gen-y/int-ye2.txt), [Root YE signed by X2](https://letsencrypt.org/certs/gen-y/root-ye-by-x2.txt), [chain documentation](https://letsencrypt.org/certificates/). Network integration uses the [documented HTTPcore backend interface](https://www.encode.io/httpcore/network-backends/).

Bounds: zero redirect hops, five distinct pointer attempts, five chain iterations, one 10-second completion budget including publisher leaf retrieval, no automatic retry. DNS runs in an isolated child with a maximum two-second timeout, killed/reaped on timeout, and at most 16 addresses. Every answer must be public; mixed public/private answers fail. Numeric sockets pin admitted answers without a second lookup. Connect/read/write/TLS operations use the remaining budget, capped at two seconds; drip responses cannot reset the total deadline. No proxy environment is inherited. These are application I/O limits, not real-time OS scheduling guarantees.

Issuer responses stream through the real HTTP/1.1 parser without decoding. A 32 KiB accepted wire cap includes headers/framing (at most one extra byte detects overflow); a 16 KiB actual body cap applies independently of Content-Length. Non-200 responses and content encodings fail before body consumption. Sockets, streams, pools and resolver children close or reap on exercised paths. Direct API dependency `httpcore>=1.0.9,<2` is declared; no runtime install or upgrade was performed.

CA/validity/issuer/signature checks through an existing certifi root remain. Only a complete path augments a normal verifying SSL context. Generated-certificate OpenSSL handshakes prove completion succeeds, root-only trust refuses the missing intermediate, and wrong hostname verification still fails. A real TLS regression also exposed Python 3.13 partial-chain trust skipping root DNS NameConstraints: the constrained-root handshake incorrectly succeeded before the fix. The completed context now explicitly disables partial-chain trust, and OpenSSL must validate through the existing root, including ancestor constraints (DNS names, path length and root expiry). The unverified publisher handshake only inspects the leaf of the two declared KNBS hosts on port 443, with public pinned DNS and the shared budget; it never retrieves publication content.

## Entry paths and ownership

- `_fetch_der`: common issuer admission/streaming choke point, including direct calls.
- `build_chain_to_a_trusted_root`: elapsed/depth/attempt/duplicate-pointer bounds and existing cryptographic checks.
- `leaf_certificate` / `completed_ssl_context`: publisher scope, pinned destination and one completion deadline.
- `SeedingHttpClient._client_for`: shared verified factory, retaining per-host client ownership/cleanup. Injected transports still bypass automatic completion as before.
- `opendata.source.fetch_publication`: shared verified factory for its exact pinned KNBS workbook. Publication URL, edition digest, body limits, no-redirect policy and parser/writer contract remain. Failed completion keeps verification enabled; the download may still fail.
- `backend/services/source_reachability.py`: reserved to the parent task, untouched. CRA/other ordinary HTTPS clients are outside this workaround.
- Dormant legacy ETL verification-bypass paths do not call this helper; they were not enabled or changed and are not certified by this draft.

## Executed verification

Raw private evidence: `/tmp/audit-oct24-issuer`, subsequently copied to this session's durable evidence directory. The baseline is extracted from accepted main into an owned temporary file outside the candidate tree. Candidate files are never swapped or stashed.

The runner uses an explicit inert environment, existing read-only cached Python 3.13.9 / HTTPX 0.28.1 / HTTPcore 1.0.9, 90-second wall / 60-second CPU caps, 1.5 GiB aggregate RSS cap, 16-process cap and 8 MiB output cap. No government request, hosted data mutation, paid service or resource upgrade runs.

```sh
P=/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/ENGINEERING_BATCH_14/media/runtime/bin/python
"$P" /tmp/audit-oct24-issuer/run_bounded.py baseline
"$P" /tmp/audit-oct24-issuer/run_bounded.py backend
"$P" /tmp/audit-oct24-issuer/run_bounded.py optimized
```

Initial candidate: 127 selected backend cases pass (11.92 s pytest, 424.7 MiB sampled runner peak). Coverage includes actual HTTP chunk parsing, generated-certificate TLS handshakes, DNS child cleanup, socket pinning/recovery, private/mixed DNS, hostile deadlines/headers, drip/wire/body caps, pointer budget, shared verified factory, original chain controls, OpenData parser/transport, seeding cache/retry and PDF paths. Six pre-existing deprecation warnings are retained. The same 127 cases also passed under optimized Python (12.25 s pytest, 432 MiB peak; assertion-rewrite warning retained). Immutable-baseline replay exits 1 with 12 named transport regressions failing and 14 legitimate/original chain controls passing. The added root-constraint TLS regression exits 1 before its fix (one boundary failure, three controls pass). A Standards reviewer also reproduced duplicate Content-Encoding fields hiding a prior non-identity value behind a final identity field. Two new cases fail before the fix (four header controls pass); every encoding field is now checked before body consumption. No decoding exploit is claimed. Final author selection: 132 cases pass in ordinary Python (11.69 s pytest, 425.2 MiB peak) and the same 132 overlapping cases pass under optimized Python (12.37 s pytest, 432.9 MiB peak). Final runner/receipts retain SHA-256 hashes, staged-tree identity, command selection and raw logs.

Exact final test selection, from `backend/`, with the Python runtime above:

```sh
env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  ENVIRONMENT=test SECRET_BACKEND=env AUTO_SEED_ENABLED=false \
  DATABASE_URL=postgresql://fixture:fixture@127.0.0.1:9/fixture \
  "$P" -m pytest -q -p no:cacheprovider \
  tests/test_issuer_transport_boundaries.py tests/test_issuer_network_budget.py \
  tests/test_completed_chain_tls.py tests/test_tls_chain.py \
  tests/test_b17_opendata_parser.py tests/test_seeding_http_client.py \
  tests/test_http_cache_encoding.py tests/test_pdf_download.py \
  tests/test_b17_opendata_legacy.py tests/test_b17_opendata_fixture_head.py
```

## Independent review

Spec: PASS, zero remaining findings or scope creep. The reviewer reran 132 selected cases and 33 independently authored probes (four ancestor-TLS, 25 transport, four actual socketpair/TLS/DNS cases). Own before/after controls reproduced the ancestor and duplicate-encoding defects and verified both fixes. Socket file descriptors closed, server threads joined, and timed-out/recovery DNS children were killed or exited and were reaped.

Standards/adversarial: PASS, zero remaining product or documented-standard findings and no meaningful Fowler smell. The reviewer reran 132 selected cases plus real HTTPcore/H11 wire cases, malformed/private/mixed DNS, direct URL/deadline calls, numeric pinning, late-connect cleanup, pointer budgets and stalled resolver cleanup. Its initial fake TLS context omitted an API method; that setup failure is preserved separately and is not a vulnerability finding. Both axes retain source-hash manifests and raw evidence; final commit binding accompanies delivery. No live publisher validation is implied by these local passes.

## Acceptance limits

The initial author run made no live publisher request. Coordinator acceptance at22:38UTC on24October used the candidate shared client for one official workbook GET: HTTP200 over verified TLS1.3 with hostname checks,224617bytes matching pinned SHA256887712acdb8ec673f96d6d0fd14491a5861b0450d2ffcf49aedde093a257a5d5,2125 numeric cells and3.132seconds. Bytes stayed in memory; no database connection or object write occurred. This is candidate client/edition acceptance, not an installed-image or native worker execution receipt. No current deployed runtime, global dependency clearance, unrelated HTTPS client, legacy scraper, hosted certificate state or production compromise claim is made.

Publishing, native processing/uploads, supervisor/worker/dispatch and automation enablement remain OFF. No merge, deployment, migration, grants/credential changes, Actions enablement, preview build or paid external reviewer. No Docker fixture is needed. The managed worktree remains for draft review.

## PR review disposition

The final coordinator candidate incorporates accepted main804c16e without changing these transport runtime files. The HTTPcore `origin=` finding is refuted: installed1.0.9 and its actual ConnectionPool call the unchanged backend with `host` and `port`, matching the [official backend API](https://www.encode.io/httpcore/network-backends/). A retained real ConnectionPool test verifies the actual backend, TLS hostname/trust and HTTP parsing over an owned loopback server rather than replacing the backend with MockBackend.

Both blocking-handshake deadline claims are refuted for the supported CPython/OpenSSL I/O semantics. With an actual server continuously dripping valid TLS handshake bytes every15ms, both issuer and publisher-leaf paths stop around121–125ms for a120ms shared budget on Mac/Python3.13 and Linux/Python3.12. The [Python SSL contract](https://docs.python.org/3.12/library/ssl.html#ssl.SSLSocket.do_handshake) defines the socket timeout as the maximum total handshake duration. Permanent tests retain one real drip case per path with scheduling slack; these do not claim hard real-time OS/CPU cancellation.

The supported-host coverage finding is valid. The old failed-completion test passed at the allow-list without invoking its leaf/issuer mocks. A new call assertion failed before the test host was corrected to `www.knbs.or.ke`; it now proves both leaf retrieval and failed issuer completion are exercised. Runtime TLS and trust policy remain unchanged after the reviewed1295146 candidate.

Coordinator review adds `tests/test_pr792_review_paths.py` to the132-case selection above (135 total cases); actual supported-platform network controls, the changed chain test and optimized cohort pass. Storage/custody acceptance is separate: the single OpenData Dry Run does not invoke object storage, and the metadata preflight intentionally leaves its non-authority fields unchanged. Publishing, uploads and dispatch remain off throughout review. Broader provider, recovery, operating-cost and installed runtime acceptance retain their separate scope.

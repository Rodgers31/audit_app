# Retained source bytes across deployments (#472)

## Confirmed failure and code boundary

The coordinator's fresh b19a Render probe found all 12 stored-audit source paths absent; `data/seeding/cache/pdfs` itself was absent. The 12-source query joined stored audits, not the public publication gate. Source 2391 is the known withheld Homa Bay assembly preamble row 901, not a national/public finding. Its original bytes have no reviewed SHA256 here and are deliberately outside initial restoration.

`backend/.dockerignore` excludes `data/seeding/`; `backend/Dockerfile.prod` copies application code and creates `data`, but carries no downloaded PDFs. The database retains its relative `SourceDocument.file_path` while every fresh instance starts with an empty runtime cache. The nightly seed job restores PDFs, but its independent validation job previously did not restore them. A seed-run cache is neither a Render disk nor another runner's filesystem.

The existing strict `verify_adopted_volume` and extraction evidence gates correctly require actual PDF bytes and reviewed SHA256/MD5. An offline reproduction exercised the original verifier against a missing path and reached `PdfDownloadError` rooted in FileNotFoundError. After explicit restoration, that unchanged verifier passed its actual PDF-byte boundary and continued to extraction/cohort verification. No hash check, parser requirement, completeness flag or publication predicate has been weakened.

## Explicit preparation command

The executable and both immutable authority files live inside the backend package; root `tools/` and `docs/` are not runtime dependencies:

```sh
cd /app
python -m seeding.source_cache --database-url-env DATABASE_URL \
  --profile reviewed --receipt /tmp/retained-source-preview.json
```

This default preview checks actual presence and both byte hashes. Missing files produce `ready=false`, `state=missing` and exit 1; corrupt/changed identities fail with exit 1. Preview creates no cache directories and performs no HTTP. A missing preview is a failed readiness result.

After approving the bounded source preparation, run separately:

```sh
python -m seeding.source_cache --database-url-env DATABASE_URL \
  --profile reviewed --fetch --receipt /tmp/retained-source-restored.json
```

The supplied environment-variable name is explicit. Connection URL values are never printed. The CLI establishes PostgreSQL READ ONLY before selecting Kenyan Sources, checks the full current Source image again afterward, and never commits a database transaction. It does not ingest, register, reparse/OCR, alter Source metadata or stamp an extraction attempt. Execute as the application user so the application workers can read the installed files.

Repeat the first command with a fresh receipt filename and require `ready=true`; then run the existing strict operational FULL validation/coverage and publication checks. Preparation certifies retained source bytes only; it does not certify extraction/cohort completeness or live publisher listing freshness. Coverage/API methods never call preparation or fetch PDFs implicitly.

On a checkout/CI runner, `cd backend` uses the same relative `data/seeding/cache/pdfs` contract. On Render, `cd /app` uses `/app/data/seeding/cache/pdfs`. An explicit `--root` changes the filesystem root, not the stored path. Paths must remain the exact URL-hash locator already produced by `fetch_documents`; the locator's SHA256 is not the PDF's content SHA256. Nonstandard/absolute/escaped source paths require separate reviewed reconciliation and are refused here.

### Reviewed profiles and limits

- `county` requires all eight independently reviewed FY2021/22–FY2024/25 county volumes from the unchanged packaged accepted-source manifest. This is the strict county coverage preparation scope.
- `reviewed` requires those eight plus the two reviewed FY2020/21 retained volumes and source 2392's reviewed national FY2024/25 PDF: eleven reviewed editions. The legacy manifest is separately byte-pinned in the helper. National 2392's SHA256/MD5 comes from `2026-09-30-oag-boundary-correction.md`; older pins come from the exact Round21 completed-reader replay. Restoring 2392 does not authorize expanding its 813 stored findings to the parser's 1,867 candidates.
- Source 2391 is excluded. A later independently reviewed artifact pin can be proposed separately; the mechanism never treats MD5 alone or a filename's URL hash as approved content identity.
- Only fixed HTTPS `www.oagkenya.go.ke/wp-content/uploads/` URLs are requested; redirects and HTML/error responses are refused. No arbitrary operator URL/manifest bypass is accepted.
- Total download deadline defaults to 300 seconds (can be reduced by `--max-seconds`), each transfer's network operation timeout is capped at 30 seconds/connect 15 seconds, and each file is capped at 64 MiB. Deadline expiration prevents installation; a currently stalled operation may take its configured timeout to surface failure. There is no retry/OCR loop.
- Every Source identity and every existing cache file is preflighted before network. A valid existing PDF is reused without HTTP. Changed or corrupt existing files are refused and preserved for review. Do not delete or replace them just to make a readiness check pass.
- Downloads stage beneath an opened cache directory, refuse symlinks, validate PDF magic/final EOF and exact SHA256/MD5 (plus existing artifact binding size), fsync, then link exclusively into the expected filename. Concurrent installation succeeds only if the winning file is the same reviewed artifact. Partial, HTML, mismatched or timed-out bodies are removed from staging and never become a retained PDF. Installation is verified before cache bookkeeping. Before a ready receipt, the helper reopens the declared root/cache directory and verifies every artifact again, refusing a detached directory or an earlier file changed during another transfer.
- A successful new download creates the existing `pdf_download` sidecar contract with actual download time, bytes and SHA256; ordinary nightly fetches can reuse it. Existing valid PDF/sidecar state is preserved, avoiding repeat downloads.
- If one later transfer fails, previously restored reviewed artifacts remain useful; the command exits nonzero. A failed command must not be read as full readiness. Receipt filenames are exclusive and must be fresh.

## Nightly and redeploy operation

The separate nightly validation runner now restores `seed-pdf-cache-*`, explicitly invokes `python -m seeding.source_cache --profile county --fetch`, and only then executes FULL validation. Preparation failure blocks that validation stage; no `continue-on-error` or silent fallback is used. Workflow enablement and provider/account prerequisites remain with the owner; this code change does not dispatch or enable Actions.

Every new runtime instance has the same ephemeral filesystem limitation. The deploy/recovery procedure must run explicit preparation before claiming strict validation on that instance. No startup network generator or implicit API hydration is enabled. A provider-managed persistent artifact disk/store could reduce transfers, but is not assumed configured and is not required to invoke this bounded recovery command.

## Executed local evidence and remaining closure

Offline unit/consumer controls cover empty-cache preview, actual strict missing-file failure then byte-boundary recovery, both hashes, cache-hit/no-network reuse, preserved document images, non-PDF/truncated/reissued/status/redirect failures, escaped/symlink paths, duplicate/missing identities, finite/type/byte/time caps, concurrent installation, and backend-only package execution. The test's extraction/cohort continuation is explicitly a sentinel seam; it is not a complete county data replay.

A separate offline smoke restored the actual independently acquired Source2395/2396 PDFs, checked exact byte identities and all 16 original Source image copies unchanged, repeated without network, and removed its owned temporary files. It used HTTPMockTransport for transport only and a two-source authority subset seam; it does not claim full-profile or production acceptance.

| Original requirement | Code/local evidence | Remaining coordinator acceptance |
|---|---|---|
| Strict county evidence remains available after redeploy | Packaged eight-edition authority; explicit preparation before FULL; original strict validators unchanged | Deploy reviewed code, show empty-cache preview fails, perform bounded official eight/eleven-source restoration, then actual strict coverage/FULL passes |
| Source identity/preservation | Both content hashes, whole Source pre/post read-only check, unchanged offline image copies | Capture actual Source images and unchanged relevant stored cohorts; no source/fact mutation |
| Runtime packaging/path contract | Backend-only module/authority test; /app and backend cwd procedures | Invoke exact packaged module in actual Render application-user context |
| Nightly validator receives bytes | Separate-runner cache restore→explicit prepare→FULL ordering | Owner-approved runnable-job acceptance under existing #231; Actions remains OFF until approved |
| Durable recovery and cache economics | Validated exclusive installation; sidecar compatibility and repeat without HTTP | Actual cold-instance recovery and subsequent byte-verified/no-download repeat |

#472 remains open until those actual runtime/provider/strict validation receipts are accepted. Earlier completed ingestion, source corrections and cache-refresh experiments are not rescheduled by this artifact preparation change. #137 retains its unrelated linked obligations, and #234's strict overall closure cannot be inferred from file restoration alone.

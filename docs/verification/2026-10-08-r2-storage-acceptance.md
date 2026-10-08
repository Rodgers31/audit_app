# Private R2 acceptance — 8 October 2026

Refs #137, #481 and #504. No production SQL is written by this acceptance.

## Approved storage and access

Cloudflare account `6929fa03fad58c2f93c70196ec498c69` has two Standard buckets: source `audit-source-evidence-v1` and isolated recovery `audit-source-evidence-recovery-v1`. Public development URLs are disabled; no custom domains/CORS are configured; the observed account has no Workers/Pages projects. The adapter rechecks three privacy configuration APIs during each bounded operation.

The owner specifically approved separate one-year source-bucket-only ObjectRW keys for Render and GitHub seed jobs, a shared one-year account-wide AdminRead privacy-control token, and a recovery-only 24-hour ObjectRW key used solely by root locally. Server credentials are saved as `RECEIPT_R2_ACCESS_KEY_ID`,`RECEIPT_R2_SECRET_ACCESS_KEY`,`RECEIPT_R2_CONTROL_TOKEN`. Recovery credentials never enter Render, GitHub or frontend environments. There are no credential values in this repository.

R2 selection and a 120-second transfer limit are saved at Render and GitHub. Render used Save only; the running deployment is separately verified before activation is claimed. The 512 MB API host has `AUTO_SEEDER_ENABLED=false`; full PDF parsing belongs to the selected Linux seeding worker.

## Executed storage and recovery

- 294-byte retained JSON: actual authenticated put/read, then a new OS process using the separate seed key, exact hash matched.
- 53,561,211-byte retained Controller of Budget PDF: actual upload/readback and fresh-process read matched SHA256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`. Upload/readback 14.905 seconds; fresh read 4.158 seconds. Root macOS byte-operation peaks 384,483,328 and 274,890,752 bytes, respectively. These are storage measurements, not full parser or deployed Linux memory proof.
- Strict independent local archive: five physical objects, 53,562,154 total bytes, exact manifests/parts and whole-source reconstruction validated.
- Isolated recovery: every planned key was confirmed absent before any write; conditional chunks then manifests were inserted and read back exactly. A separate OS process reconstructed both source files with matching hashes. Restore 18.874 seconds including startup; fresh read 7.832 seconds.
- Known JSON and PDF manifests in both buckets were authenticated 200/hash-matched immediately before unsigned requests. Each unsigned request returned HTTP 400 with the exact 113-byte XML `InvalidArgument / Authorization`, and no source bytes. The original 401/403-only test correctly refused; a narrowly repaired, independently tested classifier records this as missing-authentication parser rejection, distinct from an ACL 403. Generic 400, malformed/hostile XML, extra fields, redirects, 404s, oversized bodies and failed prior controls still refuse. This is a fixed-endpoint check plus the configuration checks, not proof of every future public route.

The independently reviewed external archive tool and owned archive remain in the coordinator evidence directory; files have 0600 permissions and archive directory 0700. The restored bucket is in the same provider/account. Neither conditional insertion nor this restore is a WORM guarantee or a separate-provider disaster recovery service.

## Bounded hosted producer gate — actual PASS

`r2-acceptance.yml` is dispatch-only with no automatic triggers. It checks out exact merged507 app commit 420cdc1887502940db32403fe26c6158789f9bc3 / tree 093b3c321197943c0a647f1e763212982ee7cef4 and hashes the reviewed harness before execution. Python 3.12 and the actual backend requirement file are used. Only the acceptance step receives the three source R2 credentials; there is no production database secret.

The gate requires literal destinations, Linux/Python parity, clean pinned checkout, at least 15 GB physical memory, 8 GiB address-space/RSS budget and a 720-second process bound. The whole job is capped at 15 minutes and the combined producer step at 12 minutes. It first performs a marker put/new-process read and one bounded official World Bank acquisition through actual parser/writer/disposable SQLite/public qualification. It then reads the retained PDF from R2, parses all 935 pages with the cache disabled and runs actual budget persistence/public consumers. The complete normalized semantic oracle includes 1,129 tables, 468 records, 378 cell-evidence entries and 1,404 qualification fields. Retained local PDF bytes do not gain publisher HTTP authority.

The single approved [dispatch, run 37776901856](https://github.com/Rodgers31/audit_app/actions/runs/37776901856), succeeded on Linux/Python 3.12.14 with 16,766,410,752 bytes physical memory. The actual full PDF parse used 859,840,512 bytes peak RSS (820.01 MiB), completed in 320.566 seconds and matched the entire semantic oracle SHA256 `cbaa3d98e2aaa96071d90260aff69cd619cf7ffe6794a89f27556cd7b08c33e4`. It persisted 468 budget rows and one extraction in owned SQLite; all 1,404 public qualification fields matched. Public serialization caused zero object GETs. The report was retained local source bytes: publisher HTTP attempts were zero and publisher authority remains false.

The actual World Bank pilot made one bounded official HTTP request, captured 2,320 JSON bytes, stored them in private R2 and produced 11 observations/rows with `verified / retained_source_and_observation_matched` qualifications in disposable SQLite. A separate OS process read the captured bytes exactly; public serialization caused zero object GETs. The marker child is a fresh storage read, not a PDF cache-hit measurement.

The World Bank acceptance preparation uncovered #506: a producer API receipt conflicted with its registered human landing URL. #507 fixed only prospective source registration while retaining the human citation in notes. Foreign hosts remain rejected and historical records are unchanged. Coordinator verification passed 148 tests; #506 is closed.

Prior fixture controls and original false-green probes are retained as preparation/history. The actual run supplements them; independent scope review found no remaining gap for the retained-CoB memory defect. #504 is closed. Neither this native run nor the earlier local controls establish full-PDF fit on the 512 MB Render API host.

At 12:33 UTC the acceptance workflow was disabled and repository Actions was turned off again. CI, Docker, nightly and other verification workflows stayed disabled throughout. No queued or in-progress runs remained at the closeout read.

## Operating boundary

Root retains the independently validated archive and its inventory. Before any destructive storage change, archive the exact selected objects and validate a restore into an empty isolated target. There is no scheduled backup job or automatic retention service from this work. Source and recovery buckets have no completed-object expiry; their incomplete-multipart default is not completed-source retention. The temporary recovery key expires 9 October; source/control keys expire 8 October 2027 and require equivalent renewal before use.

## Deployed reader and public consumers — actual PASS

Render deployment `dep-db3oskc9v7es73dtuvc0` is Live on commit `2d3cd5959df1914bf068cb0381057d1bcbbabf81`. The API image has the same application files as pinned app commit420. A fresh Render Web Shell Python 3.12.15 process verified actual saved `r2` mode, source account/bucket, default jurisdiction, 64 MiB/32 MiB caps, 120-second timeout and `AUTO_SEEDER_ENABLED=false`. It checked both deployed adapter and prospective World Bank file hashes before reading the pilot's 2,320 bytes; exact SHA256 `ae0d0e33a4e6238c808e29da5a6b409322438d5cbb5b6290620bf8fbfdf2ddfb` matched. Read elapsed 4.459 seconds, process peak 85,893,120 bytes. The child overrode only its database URL to owned SQLite and disabled dotenv; it made no production SQL writes or R2 PUTs.

Actual postdeployment GETs returned 200 for `/health`, `/api/v1/economic/indicators?limit=1` and `/api/v1/money-flow/all-counties?year=2024/25`. The economic result retained its existing `qualified` status; it was not relabelled as verified. The county response included 47 counties. These bounded consumer checks do not certify every stored figure or publisher truth.

Sanitized native, archive/restore/privacy, deployed-reader and HTTP receipts with original file hashes are retained in [the actual acceptance receipt](2026-10-08-r2-actual-acceptance.json). Original refused anonymous checks and the narrow classifier review are preserved separately in coordinator history.

#137's approved durable runtime and linked acceptance requirements are complete. #481 remains open: at least seven representative deployed egress days and an operational headroom decision are required before Free downgrade. The Pro cycle reset and these successful tests do not justify immediate downgrade. This acceptance records a bounded pilot, not a new regular seeding run or a production data backfill.

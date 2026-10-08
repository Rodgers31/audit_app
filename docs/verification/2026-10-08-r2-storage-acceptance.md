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

## Bounded hosted producer gate — pending actual execution

`r2-acceptance.yml` is dispatch-only with no automatic triggers. It checks out exact merged507 app commit 420cdc1887502940db32403fe26c6158789f9bc3 / tree 093b3c321197943c0a647f1e763212982ee7cef4 and hashes the reviewed harness before execution. Python 3.12 and the actual backend requirement file are used. Only the acceptance step receives the three source R2 credentials; there is no production database secret.

The gate requires literal destinations, Linux/Python parity, clean pinned checkout, at least 15 GB physical memory, 8 GiB address-space/RSS budget and a 720-second process bound. The whole job is capped at 15 minutes and the combined producer step at 12 minutes. It first performs a marker put/new-process read and one bounded official World Bank acquisition through actual parser/writer/disposable SQLite/public qualification. It then reads the retained PDF from R2, parses all 935 pages with the cache disabled and runs actual budget persistence/public consumers. The complete normalized semantic oracle includes 1,129 tables, 468 records, 378 cell-evidence entries and 1,404 qualification fields. Retained local PDF bytes do not gain publisher HTTP authority.

The prior fixture-only controls and original false-green probes are preserved in local evidence. They are preparation, not hosted acceptance. One approved dispatch will supply actual timing/RSS/counters and safe summaries, then this workflow and repository Actions will be disabled again. Regular CI, Docker and nightly workflows stay disabled throughout.

## Operating boundary

Root retains the independently validated archive and its inventory. Before any destructive storage change, archive the exact selected objects and validate a restore into an empty isolated target. There is no scheduled backup job or automatic retention service from this work. Source and recovery buckets have no completed-object expiry; their incomplete-multipart default is not completed-source retention. The temporary recovery key expires 9 October; source/control keys expire 8 October 2027 and require equivalent renewal before use.

#137 remains open until hosted producer and deployed reader/public acceptance actually pass. #504 remains open for actual selected Linux/R2 headroom. #481 requires at least seven representative deployed egress days; the Pro cycle reset and a successful storage test do not justify immediate Free-plan downgrade.

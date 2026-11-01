The reviewed candidate is `dfc0ea9e3a448ce5e281e15693c56477b280c1a8`. No application or dependency manifest was changed by this validation lane.

Fresh installs from official PyPI succeeded, and each actual installed graph passed `pip check`:

| Profile | Environment | Installed distributions |
| --- | --- | ---: |
| Backend runtime | Linux CPython 3.12.16, arm64 | 87 |
| Backend development | Linux CPython 3.12.16, arm64 | 129 |
| ETL runtime | Linux CPython 3.12.16, arm64 | 52 |
| Restricted worker pins | Linux CPython 3.12.16, arm64 | 93 |
| Native development/test tools | macOS CPython 3.13.9, arm64 | 128 |

The exact versions and official installation artifacts are bound in the respective `*-inventory.json`, `*-runtime.json`, and `*-install-report.json` files. Current range resolution selected AnyIO 4.16.0 rather than the October 31 cache's 4.15.1; the fresh Linux tests use the new resolution. The restricted worker graph stayed unchanged. All three preflight driver manifests were inventoried: batch66 pins psycopg2-binary 2.9.12, and batch71/batch80 pin 2.9.13. The four declared CPython 3.12/3.13 x86_64 wheels passed actual pip `--require-hashes` downloads and matched official PyPI metadata and downloaded bytes.

At `2026-11-01T17:42:19.110077Z`, the final live OSV run completed all **158 distinct package/version queries** across these profiles and the three driver pins, through four batches with no remaining pagination. It returned **zero raw advisory IDs** for those versions. The known old pypdf 6.21.2 positive control returned all seven known advisory IDs. This is a current known-advisory snapshot, not a claim that arbitrary code or native binaries are vulnerability-free.

The private audit verifier was corrected after executed review findings. Clearance now depends only on complete exact-version query coverage and zero raw candidate advisory IDs. Every returned ID is a finding; withdrawal, severity and detail bodies cannot erase it. Malformed versions, truncated driver pins, transport/result shapes, incomplete pagination and partial positive controls refuse clearance. The final helper SHA is `bd5063283f94ca7b036608523e80b3e7319a9c808b4738921e091170207996e5`; independent review executed 62 cases in normal Python and 62 under true `-O`. Earlier verifier versions, RED receipts and raw responses remain archived. `live-osv-verified/` contains the final authoritative requests, responses and summary.

| Existing test selection | Normal | True `-O` | Skips |
| --- | ---: | ---: | ---: |
| Native security/auth/TLS/PDF/media | 533 | 533 | 0 |
| Fresh Linux backend affected selection | 339 | 339 | 0 |
| Fresh ETL maintained PDF readers/xref | 5 | 5 | 0 |
| Actual PostgreSQL-backed financial HTTP captures | 3 | 3 | 0 |
| Fresh locked-worker installer fixture units | 34 | 34 | 0 |

The native and Linux pytest selections overlap by 329 identities. Their complete union with ETL and HTTP cases is **551 distinct pytest cases per mode**, plus the separate 34 fixture-unit controls; platform repetitions are not counted as additional cases. The native run executed 54 actual security PostgreSQL cases and all nine video cases previously skipped for missing ffmpeg. Only uniquely owned loopback PostgreSQL containers and synthetic source/account data were used. Both normal and optimized HTTP captures came from actual current HTTP readers and PostgreSQL rows, and the three resulting JSON files are byte-identical across modes. Those captures are in `financial-http-capture/` for the frontend contract tests. ETL testing added four test-only tools while preserving every original ETL runtime version; those four exact tool versions were already covered by the development advisory queries.

Fresh runtime-only imports of the web app and supervisor module succeeded with all activation flags false, without starting a server or worker. All owned validation containers were removed, the preexisting admin redesign containers were untouched, and the worktree remained clean. No production service, account, media upload, worker, scheduler or financial generation was activated; no paid resource or hosted test was requested.

Limits that remain explicit: foreign x86_64 driver wheels were hash-verified rather than executed on this arm64 host; existing platform qualifications still apply. The ffmpeg 9.0.1 video proof is for the installed macOS binary, not a future production Linux binary. This package audit does not clear operating-system packages, embedded browser/native libraries or an uninspected deployed image. Runtime requirements use ranges, so a later image resolving different versions needs an inventory/advisory comparison. Worker host and media/publishing launch gates remain separate and off.

`FINAL-PYTHON-RECEIPT.json` binds the source, manifests, counts, test results and final advisory result. `SHA256SUMS.json` binds the small evidence files without recursively exporting environments or caches.

# Fixture repairs and dependency acceptance — 26 October 2026

Base: `6fdce855950e94cb30c43dfdcd8307885795b3cf` (PR816), tree
`90724835b5e36a99677314a39f5078e52944d76c`. This lane changes verification
fixtures and this acceptance record only. Requirements, constraints, lockfiles,
application handlers, workflows and production configuration are unchanged.

## Three observed fixture defects

* **803:** the bootstrap regression imported an ambiguous top-level `tests`
  package. The unchanged base fails with `ModuleNotFoundError` before seeding.
  The test now loads the exact sibling fixture file and executes the original
  `initialize_reference_data` bootstrap against its empty SQLite database.
  Both preloaded ETL and unrelated site-package `tests` namespaces are exercised;
  all 47 counties and every stored metric row must retain the official code.
  The fixture's own purge/census/seed cohort is also executed. No bootstrap
  implementation or county identity assertion was weakened.
* **804:** the unchanged optimized child accepts the forged `contracts.py`
  compile filename and prints `recovery-runtime-ok`. All child assertions are
  replaced with explicit runtime guards, including extracted-code identity,
  recovery counts, authorization flags and exception context. Positive and
  forged-filename children execute with explicit optimization values 0 and 1.
  Independent executable mutations additionally exercise every guard family.
* **762:** a real loopback HTTP POST declaring 99 bytes but sending only
  `message=partial` previously returned 200 and created a synthetic post.
  The shared response entry point now consumes exactly the declared bounded
  length before emitting a start event or reaching any effect. Form/text reads
  use at most 64 KiB per read; multipart continues to drain without retaining
  its image body. Duplicate/malformed lengths, transfer encoding and missing
  POST length refuse before that boundary. Complete bounded form and multipart
  requests and all seven existing routes pass real loopback TLS checks.

GET, HEAD and POST all enter `Endpoint.respond`; the framing guard precedes
storage/profile/feed/photo/readback dispatch. This is a synthetic rehearsal
endpoint, not a production application ingress fix or evidence of a public
publishing exploit. The independent HTTP server uses private loopback only.
The TLS contract checks transport, routes, response bytes and inert post state;
the existing direct-handler streaming test separately verifies response hashes.
The prepared image bytes are synthetic and do not qualify actual
native SDK/image workload or performance thresholds.

## Source-bound local validation

Evidence root (external to source):
`/Users/roger/.codex/visualizations/2026/10/26/verification-fixtures/`.
Each `runs/<label>/receipt.json` binds every staged source file, trusted wrapper,
toolchain wheels, exact image ID, command, exit and bounded raw output. Original
failures remain in `base-county`, `base-recovery-opt` and `final-base-eof`.
The early broader `base-endpoint` diagnostic also contains duplicate-framing
timeout/cascading subtest failures; those are not additional proven defects.

The affected cohort passes **58 tests per normal/optimized mode**, zero skips,
with 65 unittest subtests reported separately. Counts overlap with all narrower
runs and independent reviews; do not add them. The normal receipt is
`runs/final-normal`, optimized `runs/green-optimized`. Explicit package-owner
replays use the actual `.github/scripts/run_backend_tests.py` binding functions:
`owned-backend` executes 21 cases with backend ETL ownership and
`owned-legacy-opt` executes 99 cases with legacy ETL ownership, including the
county normalizer. These are selected cohorts, not the full launcher gate.

Python is 3.12.15 on Linux ARM64. Tests run non-root, external-network-none,
read-only source/toolchain, empty allowlisted environment, private 512 MiB
scratch tmpfs, 768 MiB RAM, one CPU, 192 PIDs, file/CPU limits and 160-second
wall timeout. No host socket or credentials are mounted. The exact source
bootstrap fixture uses SQLite; **no PostgreSQL cases are claimed by this lane**.
There is no changed database/ORM behavior requiring a PostgreSQL repair proof.
No hosted gate, minimum-Python, full backend, native x86 or browser run is claimed.

## Dependency acceptance matrix

`dependencies/reconciliation.json` is produced by the trusted metadata-only
`reconcile_dependencies.py`, with generator/input hashes and disk readback.
It imports no target code, installs nothing and transmits only public
package/version metadata to OSV. Raw requests and responses are retained.

| Scope | Exact evidence and result | Remaining boundary |
|---|---|---|
| Captured serving Python | B89 observation at 2026-10-26 00:25:54 UTC: 81 distributions. Normalized names/versions exactly equal the retained rebased production-image inventory. Fresh query included all 81, zero matches. | This is reconciliation of a captured census, not a new inventory after the coordinator's current release. |
| Backend production requirements | SHA256 `bdae2d75e7f322723670e0c9ed54b8ed971d8dc9b30591b06002c6553856515d`; constraints `bcc71d82d36edf3fb33f005d8ff146900cdeeef5530938714940bc8c3c30e3c9`, matching captured production/review inputs. | Ranges permit future different resolutions. No immutable complete Python lock is created by this PR. |
| Captured development Python | Prior resolved 137-distribution graph plus later 129-distribution review graph freshly queried, zero matches. | Distinct historical graph scopes, not a fresh complete installation. Later source file differences are enumerated in reconciliation; requirements equality is not application byte equality. |
| Captured legacy ETL | Prior resolved 52-distribution graph plus later 58-distribution review graph freshly queried, zero matches. Current requirements hash `0ce8b3e673d351f7aa838b8c225a22bf3cbb78e03061e5083bad77fa9518fa34` matches captured input. | Extra review packages are not deployed ETL packages. No fresh resolution/browser install or full ETL acceptance. |
| Combined advisory lookup | 162 unique normalized PyPI package/version pairs across the six inventories; zero OSV matches in the fresh response. | Package matches alone would require advisory-detail and reachability analysis. Absence of matches is not a security certificate. |
| Locked JavaScript | Lock `1ef0054e2dd0ea42374855b093842225c55fa2151e9a65bb0f0a4130135431a4`: 900 dependency records, 173 not marked dev (root record excluded). B94 full and production npm audits each exit 0, zero entries. | B94 audit receipts are retained evidence, not rerun here. Optional architecture records are not proof every binary was installed/executed. |
| Current ETL direct pins | B94 requirements-derived 18 direct exact pins: zero matches. | Historical pre-fix 17-pin lookup remains SUPERSEDED; no current finding is inferred from it. |
| PHP | No tracked PHP/composer input in this base. | No PHP application coverage is implied. |
| Local native fixture | Fresh local runtime inventory: 97 Python distributions, 118 Debian binary packages; Linux ARM64/Python 3.12.15/OpenSSL 3.5.7. JPEG decode and PDFium blank-page render pass; PDFium reports `156.0.8076.0`. | This cached toolchain differs from production: notably Pillow 12.3.0 versus serving 13.0.0, plus older pip/certifi and unused python-jose/ecdsa. It is fixture evidence, not compliant serving dependency acceptance. |
| OS/container base | Local Debian package inventory and exact sandbox image identity retained in `runs/local-native-inventory`. Production/ETL use mutable `python:3.12-slim`; frontend uses mutable `node:22-bookworm-slim`. | No exact current deployed OS/image census or vendor OS advisory match is available in this lane. Local package inventory cannot certify production; rebuilding with network is excluded. |
| ffmpeg/OCR/Java/Node/browser | The fresh sandbox inventory explicitly finds no ffmpeg, ffprobe, tesseract, pdftoppm, Java, Node, Chromium or Firefox executable in PATH. | Production Dockerfile's ffmpeg install and ETL Playwright installation are source intent, not a binary census. Old cached host-fixture images are separate historical environments. |
| Native x86 media | Earlier dependency report retains bounded child failures under Rosetta/address-space enforcement, while ARM image controls passed. | The native x86 limitation remains open; no guard was relaxed and no new media activation is authorized. |
| Model/ONNX/browser assets | Exact locked native JS package versions are listed in reconciliation. | No model assets, actual inference, browser bundle or WASM/native cross-platform gate is newly executed. Existing historical narrower receipts retain their original scope. |

No currently confirmed advisory in the captured candidate/serving inventories
requires a dependency change. No package or lock upgrade is included. This does
not accept the older cached test image as a production image or erase known
historical findings in it. Advisory data is time-bound; full OS/native coverage,
release-installed inventory and reproducible range resolution remain under 494.

## Review, release and rollback

Two independent Spec and Standards reviewers run executable normal/optimized
controls with their own evidence directories, source hashes and adversarial
fixtures. Their reports and exact receipts are retained under `reviews/`.
Their review covers the changed fixture boundaries, not whole-app security.

803, 804 and 762 have scoped code/regression repairs prepared for coordinator
review. 494 remains open for its wider acceptance. No issue auto-closing keywords
are used. Rollback is a normal revert of the fixture-only commit; no migration,
provider setting or dependency rollback is needed. Review/merge/deploy remain
with the coordinator. Chrome was reserved and untouched; no live availability
probe, provider operation, source upload, publishing/upload activation, Actions
enablement, bot-review request or new cost occurred.

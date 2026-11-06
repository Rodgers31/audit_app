# Controlled ingestion runtime candidate — 5 November 2026

**The97-artifact image below has scoped37-case local evidence. The separately sealed104-artifact Git candidate remains unbuilt/unqualified.** Its1800-second resource queue expired without starting a build; the complete38-case rerun remains pending.

**No writer profiles are approved.** The absent `migrate.json`, `bootstrap.json`, `seed.json` and `validate.json` remain an intentional admission hold. Do not copy an observed profile into those paths merely to satisfy the workflow's existence check.

The local engineering candidate uses a frozen Linux amd64 OCI rootfs and fixed-prefix fresh Python installations. Full OS/dpkg/native executable/library/language/JVM identity remains normative inside that rootfs. Capture the separate runner's complete inventory as diagnostics; an Ubuntu runner fingerprint must not be compared to, or represented by, this Debian container inventory.

| Input | Exact identity |
| --- | --- |
| Official Python base index | `docker.io/library/python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30` |
| Local native OCI manifest | `sha256:bd7a326f556c4087619f5d11a6b51ec043165935fc68fb16fd15ed3ba37e2e6c` |
| Exported archive | 163,647,488 bytes; SHA256 `5decf376a34a69f90cbb169ba734f3be6eeca8679eee51e1d6562fa48ecb1037` |
| Python | CPython 3.12.16, Linux x86_64, `cpython-312-x86_64-linux-gnu` |
| Python executable | SHA256 `0e6475dfda68a9b2d93501449fc47593ca169010e8f4881577b97463fd0c1263` |
| Standard library/libpython | SHA256 `d642d157e4cef7200cb604b2b2b25ac76119ed85265268f9e2fe66627fa93ebb` |
| Native package inputs | `tools/nightly_acceptance_20261105/native_runtime/native-artifacts.lock.json`; 97 official Debian artifacts, 84,404,264 bytes |
| Installed native census | Debian13.7; 184 dpkg entries; 256 linked-library/JVM files; eng/osd trained data |

The exported rootfs is the reproducible **execution artifact**. Rebuilding it is a new candidate, not a promise of identical OCI metadata or generated Java trust-store bytes. Freeze and qualify the new artifact independently. The original nightly used Ubuntu; the candidate is not Ubuntu parity.

The complete selected JVM home is bound, including linked configuration directories, dynamically loaded libjvm/module/security bytes and its linked launcher libraries. The Python86 and qualification95 locks and payload manifest are unchanged. The qualification graph preserves every production wheel row. RECORD, generated wrappers, interpreter, stdlib and installed-bytecode guards remain mandatory.

All four writer jobs would use one shared complete approved base:

| Job | Actual needs |
| --- | --- |
| migrate | Database driver, TLS and schema tools; no PDF execution |
| bootstrap | Reference handlers and their imports; optional native reader paths |
| seed | Text/scanned PDFs, Poppler, Tesseract eng/osd and selected tabula/JVM paths |
| validate | Database checks and retained PDF/publication readers |

Git is additionally required by the qualification recorder's owned source fixture. The97-deb image lacks it, and the unchanged original runtime-bound recorder case was executed red with `FileNotFoundError: git`. The proposed `native-artifacts-with-git.lock.json` is now sealed at SHA256 `1c0036610e5841068bd96362b439a8f0ae01ee7f593b368b0805e9c2c8a78858`:104 exact artifacts/103,155,140 bytes, with all97 original rows unchanged and seven additions. The build waited1800.393s with1793 no-work busy returns, then expired before creating any image output. No new image,38-case pass or new-image native-negative proof exists. The existing37-case results do not qualify the104-deb candidate. The cached Git overlay was not silently mounted. An available shared-heavy-lock slot is needed to execute the prepared finite build/qualification/control stages.

A future approved environment bundle uses `controlled-ingestion-environment-v1`: digest-bound base/image/archive, native-lock/corpus digests, four same-base v1 profiles, and authenticated complete runtime observations for `/opt/ingestion` and `/opt/qualification`. `native_environment.verify_environment(path, job, role='production')` verifies those observations; its verdict explicitly withholds production admission. It hashes and parses the same input bytes, refuses alias paths and native/interpreter overrides, and retains the existing runtime.py v1 return/schema contracts.

Use the existing runtime.py `wheels`, `install` and `verify` commands **inside** the exact independently approved image/CPU boundary. Production86 installs at `/opt/ingestion`; qualification95 installs separately at `/opt/qualification`. Validate the archive SHA/size and actual loaded OCI manifest before startup. Use an explicit local engine socket, empty Docker client configuration/environment, no implicit pull, read-only source/rootfs/toolchain and owned scratch. For qualification, deny network and credentials and bound CPU/memory/PIDs/file bytes/wall time. `native_corpus.py` needs that outer sandbox and finite deadline; it is not itself an OS isolation boundary.

`native_image.py` supports an offline local candidate build from exact sealed debs. It holds the shared heavy lock across validation, descriptor-bound private input capture, installation, export and cleanup. It refuses ambient Docker context selection, records source/helper identities, and records unexpected/cleanup failures as failed. `native_artifacts.py` reports byte integrity only; signed repository provenance and advisory review are separate.

Do not admit this candidate yet:

- Official Debian security pages list open advisories affecting the selected Poppler, Tesseract, JVM and Perl versions. The bundled tabula jar has additional Maven components requiring transitive advisory review. Applicability, bounded invocation, mitigation or patched replacement must be reviewed; no application exploit is asserted by this packet.
- Tesseract's full version probe includes AVX2/AVX/FMA/SSE4.1 detection. The image digest does not freeze CPU features. V1 refuses a changed report. A supported CPU policy or versioned normative/diagnostic split needs review and actual corpus qualification; do not strip diagnostic lines to pass.
- No hosted archive distribution, quota/retention approval or hosted/native CPU execution is supplied. No image was published or hosted job dispatched.
- Final combined source/actual-PG/native authority, full15 and weekly workload acceptance remain separate. The915-page text benchmark is not a full ingestion-plan run.

Bind cache/proposal reuse to the approved environment/profile/runtime hashes, exact source/edition/origin, parser bytes, current rows/dependent facts and retained evidence. Native success cannot waive the four clipped OAG title holds, invent a publication day/origin or refresh an old reconciliation proposal.

See the [review and evidence packet](../../../releases/deployment-native-runtime-20261105/README.md). Workflow changes belong to workflow_refresh. Publishing, uploads, publishing workers and financial generation remain off; native/source admission remains held and pin/schedule settings are unchanged.

# Owned PostgreSQL test image prerequisites

Issue #498: fresh CI workers must have the immutable images used by the local
backup and logical restore fixtures before backend tests start. The PostgreSQL
service's `postgres:17` pull does not establish either fixture pin in the cache.
The first retained hosted backend attempt stopped on media failures before these
fixtures ran; it provided no cold-cache PostgreSQL fixture acceptance.

Both CI and the manual verification workflow run the preparation helper before
backend tests, with `--service-postgres-ref` set to the approved exact PostgreSQL
17 ECR service pin. Running
`python .github/scripts/prepare_postgres_test_images.py` without this option
prepares only the two fixture images and never changes a local image alias.
The helper reads the two literal pins from `tools/bounded_pg_backup.py`, checks
the native Linux Docker platform, and pulls each missing exact digest once. It
then checks the publisher RepoDigest, local image ID, OS and architecture.
Preparation has a shared 240-second deadline and a five-minute workflow step
limit. The backend job has a 20-minute limit, including the full test suite;
the measured capacity decision is in `bounded-backend-job-capacity.md`.
A failed pull, missing or
malformed readback, wrong pin, wrong platform or timeout fails preparation.
The logical fixture retains `--pull never` and its isolated local database.

## Publisher and container identity

The existing publisher index digests are unchanged. Direct registry OCI index inspection
on 2026-10-03 confirmed native Linux amd64 and arm64 descriptors in both.

| Image | Publisher index digest | Native amd64 manifest digest |
| --- | --- | --- |
| PostgreSQL 17.11 fixture | `67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675` | `d13db94ae661d517c5ed57c509a578d5ea64aae639871ba25294f4f42d83de28` |
| Supabase PostgreSQL 17.6 fixture | `21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab` | `5e52ca81790ae3aa1c2f8c20df41dd96404c8ab29632dddf113b881de785ee92` |

The amd64 compressed layer sums were 161,285,178 and 363,100,569 bytes,
respectively. These are registry sizes, not measured hosted download times.

Docker image IDs and publisher index digests can differ. The logical verifier
now inspects the exact pinned publisher reference, requires that exact
RepoDigest, and compares its inspected local ID to the owned container's
`Image`. This supports classic Docker configuration IDs and the index IDs
reported by the local Docker Desktop image store. The name, network isolation,
ports, running-state, Unix socket, PostgreSQL 17.6, database and catalog checks
remain required. Existing completed ARM receipts remain historical evidence of
their actual executions.

See Docker's primary documentation for [digest-pinned pulls and platform
selection](https://docs.docker.com/reference/cli/docker/image/pull/) and
[image inspection](https://docs.docker.com/reference/cli/docker/image/inspect/).

## Bounded verification

Regression controls fail the previous workflow setup and previous direct
container/index comparison. The preparation CLI is executed through an owned
Docker command fixture for cold and cached images, native amd64 and arm64,
wrong pins/platforms, malformed metadata, failed pulls and failed post-pull
readback. Timeout and deadline controls refuse without retries.

The complete focused local suites passed: 27 workflow/helper tests, 24 logical
restore tests and 52 backup/acquisition tests. Actual cached native ARM image
preparation and owned PostgreSQL lifecycles passed, including read-only logical
collection through the new identity binding and real negative database changes
rolled back after each control. No fixture skips were used. Hosted native amd64
cold-cache execution remains the final acceptance gate; local ARM execution and
registry manifests do not substitute for that run.

## Failure diagnostics

The third retained hosted attempt at `c504d8a2031e9fe596b06cf051777cc5d2a4c056`
prepared PostgreSQL, then returned only `image_preparation_command_failed`.
Its destroyed runner's discarded child diagnostics cannot establish the
underlying cause. A later successful registry control cannot recover it.

Failures now emit one bounded JSON receipt with the command phase, exact public
image pin, native platform, exit code and a fixed diagnostic category. Only the
first 8192 stderr bytes are inspected for classification; raw child text, URLs,
tokens and credentials are never printed. The receipt reports stderr byte
count and whether the classification sample was truncated. Categories describe
message patterns rather than proving a root cause; unknown messages remain
`unclassified`. Timeouts and unavailable clients have explicit categories.

Cached inspection authorizes a pull only for exit 1 with the exact image-bound
`No such image` diagnostic and empty/empty-list stdout. An unavailable or denied
daemon, wrong image or ambiguous inspection failure refuses preparation. This
also fixes an exercised false success where an inspect daemon failure was
mistaken for a cache miss and a subsequent pull/readback masked it. Post-pull
inspection remains mandatory; failures identify `inspect_pulled`. The shared
240-second deadline, no retries, immutable pins, platform/identity checks,
workflow step and job limits are unchanged.

## Official distribution transport repair (#598)

Hosted run `37989790306` at `1ccc71a56ce7e84a0bfc15a3a406d5f022dba298`
failed at two explicit Docker Hub pulls: the backend's PostgreSQL service before
checkout and the original browser fixture before its cases ran. Both logs retain
the registry's unauthenticated pull-limit message. That run provides no backend
or complete original-browser execution acceptance. The optional coverage report's
missing checkout script was a subsequent setup consequence.

The ordinary fixture reference is now
`public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`
in the backup tool and complete browser runner. PostgreSQL and Redis services in
`ci.yml` and `verification.yml` use the approved DOI ECR index pins below.
The parser accepts only the exact ordinary DOI ECR and existing Supabase repository
prefixes, with immutable digests. There is no registry fallback or daemon proxy.
AWS documents [Docker Official Images on ECR Public](https://aws.amazon.com/blogs/containers/docker-official-images-now-available-on-amazon-elastic-container-registry-public/)
and [anonymous digest-pinned pulls](https://docs.aws.amazon.com/AmazonECR/latest/public/docker-pull-ecr-image.html).

| Purpose | Index SHA-256 | amd64 manifest SHA-256 | arm64 manifest SHA-256 |
| --- | --- | --- | --- |
| Existing PostgreSQL fixture | `67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675` | `d13db94ae661d517c5ed57c509a578d5ea64aae639871ba25294f4f42d83de28` | `413da4542e091471785b7f18f1a2258df134bc6506ab4e1e53725aa8bcfdb650` |
| PostgreSQL 17 service | `2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3` | `3cec7eb015ba8adb28139fa5c83b8489cdf0e666e53dfdf20f598ae0cc8739e3` | `2d46d14f5a051d8c1e4f9d7c07dbeb877ae08150654d69ca32903ccbae4a5421` |
| Redis 7 Alpine service | `858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` | `ca0acbb137c1dc3339c8b147a58fd6f42775d4599327b50e7b116c23de501af2` | `1f09a89a207d794a8c61d9edfc26e7c58427de10ccef7c5d18d638df79a63b85` |

Captured public registry indexes, both architecture manifests and their config
bytes are byte-identical to Docker Hub, with each SHA-256 verified. The service
pins freeze the inspected `17` and `7-alpine` tags; the failed hosted setup did
not load either mutable tag, so it cannot establish an earlier loaded identity.
Both PostgreSQL indexes report `17.11-1.pgdg13+2`; Redis reports `7.4.11`.
The Supabase fixture pin remains unchanged.

The existing role/RLS fixture requires a cached `postgres:17` alias. The opt-in
preparation mode accepts only the exact approved service reference, validates its
cached RepoDigest, native Linux architecture and immutable local ID, then inspects
the alias. An existing different alias refuses without overwriting it; an identical
alias needs no write. An absent alias is created from the verified service ID and
read back with that same ID and native platform. Service preparation never pulls an
image, and unsafe arguments are rejected before entering diagnostic context.
Actual alias creation remains a required fresh hosted runner check. Local
verification performed no alias writes.

Evidence is retained under
`BATCH_9_SESSIONS/CI_RESTORATION/REGISTRY_TRANSPORT_598`:

- `metadata-attempt1/receipt.json` binds the registry proof generator and all 34
  retained response files, including both platforms and tag/index comparisons.
- `docker-attempt2/receipt.json` binds six actual anonymous Docker pulls and owned
  network-none PostgreSQL/Redis lifecycles, exact publisher/child identity,
  platform and cleanup. Cached layers were retained on the shared local daemon;
  these results do not substitute for a cold fresh hosted runner.
- The initial Docker harness failure is retained in `docker-attempt1`: Docker
  Desktop's platform-qualified image inspection returns the child ID while
  `container.Image` retains the publisher index ID. The second generator checks
  both views and the actual container child descriptor; the first generator and
  failed receipt were preserved.
- The new transport and alias controls were executed red against `f63db60` before
  implementation. Final **71 current workflow controls** pass. Minimum Python
  passes the **25 image, five configuration and 12 manual workflow controls**;
  this selection overlaps the current suite. The broader minimum attempt's five
  launcher failures remain recorded because that runtime lacks coverage and
  pytest-cov dependencies; it is not claimed green.
- Real scoped backup, logical restore, acquisition and role/RLS suites pass
  **92 cases without skips on each runtime**, using distinct caller-owned private
  temporary directories. The existing cached role alias was genuinely present;
  the cases were executed. Critical Python lint and workflow parity pass.

Independent executable review also reproduced inherited acceptance of mixed
valid-plus-malformed `RepoDigests`. New controls observed seven false successes
before correction. Every digest-list member must now be a string with a nonempty
repository and a valid SHA-256 suffix; valid canonical metadata aliases coexist
with required exact ECR membership. A malformed server architecture list/dict
previously raised an unstructured `TypeError`; its two red cases now produce a
bounded refusal before image or alias commands. Both corrections are scoped to
the preparation validator and covered on current and minimum Python.

The post-transport complete local original-browser replay accounted for all
**323 identities: 312 passed, 11 existing skips, no unexpected or flaky outcomes**.
All six cohorts exited zero and the owned database was removed. Its actual
browser generator and fixture hashes stayed unchanged while preparation-helper
and control corrections were made. It is a working-tree browser receipt, not a
whole-tree frozen run; the first and second source freezes remain separate.

The transport edits change the backup and browser generator hashes. Previous main
and combined-source receipts precede these edits and remain historical evidence;
they are not rebound to the new generators. Newly generated receipts carry the
executed source hashes. Schema, migration, acquisition and restore behavior were
not changed. A fresh immutable full hosted run must still execute every required
backend case and all 323 original browser identities, with healthy PostgreSQL and
Redis services and validated alias creation.

The inactive `docker-build-deploy.yml` test services still use Docker Hub tags.
Their migration is a remaining deployment-preflight gate under #545/#598. This
repair does not migrate or certify that production workflow, its build/publish
references, or production compose images.

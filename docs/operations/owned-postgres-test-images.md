# Owned PostgreSQL test image prerequisites

Issue #498: fresh CI workers must have the immutable images used by the local
backup and logical restore fixtures before backend tests start. The PostgreSQL
service's `postgres:17` pull does not establish either fixture pin in the cache.
The first retained hosted backend attempt stopped on media failures before these
fixtures ran; it provided no cold-cache PostgreSQL fixture acceptance.

Both CI and the manual verification workflow run
`python .github/scripts/prepare_postgres_test_images.py` before backend tests.
The helper reads the two literal pins from `tools/bounded_pg_backup.py`, checks
the native Linux Docker platform, and pulls each missing exact digest once. It
then checks the publisher RepoDigest, local image ID, OS and architecture.
Preparation has a shared 240-second deadline and a five-minute workflow step
limit. The backend job retains its 15-minute limit. A failed pull, missing or
malformed readback, wrong pin, wrong platform or timeout fails preparation.
The logical fixture retains `--pull never` and its isolated local database.

## Publisher and container identity

The existing publisher pins are unchanged. Direct registry OCI index inspection
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

# Executed validation and limits

The final backend inventory contains **928 unique cases**, replayed normally
and with Python optimization. Each replay has 2,784 passing setup/call/teardown
records, no skips or xfails, and **295 unique actual PostgreSQL cases**.
The independent 149-case hostile-input probe and original 36-case family are
subsets of that inventory. The original family is **35 actual PostgreSQL cases
plus one constant**, not 36 database cases. Counts from overlapping runs are
not added together.

`BACKEND-INVENTORY-READBACK-v2.json` independently verifies both phase
inventories and every consumed backend/ETL/corpus hash against the candidate.
The raw recorder's `candidate_matches_snapshot=false` has one documented
cause: an immutable external adversarial probe was injected into the snapshot.
It is absent from the checkout. Every actual candidate input matches.

The final frontend run executes **341 unique cases in 32 suites**, with no
skips or todos. This includes five source-bound candidate fiscal-year
selections on the real budget page, picker, flow, donut, trend and source
reconciliation components, plus a conservative withdrawal scenario. Expected
values preserve each fiscal column's vintage and the separate FY 2022/23
APDMR/BROP observations. The fixture comes from the final isolated-PG HTTP
export. Text and numeric assertions are not a production screenshot or browser
layout qualification. An unrelated APDR endpoint absent from the export is
explicitly mocked as unavailable. The existing optional county reader test
consumes hash-bound, committed historical PostgreSQL HTTP fixture payloads;
this is not a new county source acquisition.

The target TypeScript 5.9.3 full-project check passes with `--noEmit` and
`--incremental false`. Frontend source hashes match both final receipts.

Execution uses existing cached resources: Linux amd64 Docker image
`sha256:bc6b9576f5d8c1b4b1797fd72a629c244499c220686d1aa433a40db55a93da9a`,
Python 3.12.16, SQLAlchemy 2.0.55, Pydantic 2.14.2 and an isolated owned
PostgreSQL container. Frontend tests use target React 19.3.1, Next 15.5.28 and
TypeScript 5.9.3 with Node 24.22.1, but cached Jest 29.7 tooling. Target Jest 30
native artifacts and Next SWC are unavailable in the existing offline cache.
That limitation remains explicit; no dependency download or new paid build
was requested. The approved native workflow/runtime and pruned production
build are separate holds.

All heavy runs own the shared flock. Sources and caches are mounted read-only;
tests receive an empty allowlisted environment, bounded CPU/memory/PIDs/bytes/
wall time and scratch writes. Provider and production egress are denied.
PostgreSQL uses only the owned container's loopback namespace. Receipts record
actual database identity and zero remaining fixture tables; owned containers
are removed by exact identity and checked independently afterward.

Historical failures remain diagnostic. These include meaningful pre-fix
publication regressions as well as distinct setup failures: truncated harness
reports, exhausted test scratch retention, initial TypeScript heap exhaustion,
and missing/unstable frontend mock providers. They cannot establish passing
behavior. The stale-identity-map regression was repaired and replayed against
an immutable pre-fix adapter overlay after earlier transaction/column fixture
errors; that later red establishes the defect without rewriting the timeline.

Independent Standards, Spec and executed-adversarial review artifacts, exact
red/green mappings, generator/runtime hashes and final cleanup are bound in
`DELIVERY-v1.json` in the external lane packet. GitHub replies remain local
drafts until the coordinator pushes and posts them. There is no full-suite,
CI, production-source adoption, deployment or serving-freshness claim.

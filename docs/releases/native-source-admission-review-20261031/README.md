# PR #865 refresh-boundary acceptance

This packet supports the [review correction](../native-source-admission-review-20261031.md).
The initial source-admission packet is historical. This packet supersedes its
coverage of a previously admitted row being rewritten while admission is OFF.

| Execution | Result |
| --- | --- |
| Root pre-fix three-writer same/changed refresh | Six expected assertion failures; zero errors/skips |
| Root final focused controls | 26 passed |
| Root final affected selection | 675 passed normally and the same 675 under true Python `-O`; zero failures/errors/skips |
| Genuine retained national/KRA checks | Three passed in each mode at 512 MiB; zero failures/errors/skips |
| Independent Spec | 152 passed per mode: 22 actual PostgreSQL/installed-worker cases plus 130 direct hostile-input controls |
| Independent Standards | 47 passed per mode |
| Independent pre-fix gate-only counterfactual | Each review independently reproduced all six expected failures |

Different Python modes execute the same inventories. Independent scopes overlap
with root corroboration; their counts are not added to a unique total. Original
JUnit, exact command producers, commands and case ledgers preserve the results.
Initial fixture/import/ORM-equality failures are retained in the independent
archive and explicitly excluded from successful acceptance.

The genuine retained official-source checks use the unchanged supplementary
test sources and [input pins](../native-source-admission-20261031/official-inputs.json).
Their compressed JUnit and command receipts are retained here. They exercise
the full national producer, writer and reader, ten rows/twenty cells and retained
reacquisition, plus the dated historical KRA article. All financial generation
is OFF; the hook returns `financial_environment_disabled` and creates no social
state. These are retained official contents with local acquisition/job clocks,
not new provider acquisition, current-year KRA acceptance or production adoption.

## Exact source and replay

`reviewed-source-sha256.json` pins the four changed runtime/test paths and
unchanged reader, authority and generation seams. The full frozen candidate is
6,617 files, canonical mapping SHA256
`1780790d6e2921c3f2aa2ae232a78346b4979cc1d6aef9cc6fc414316ff0c9e4`.
The only runtime change from pushed `1e349292` is the shared gate. Final release
documentation and this packet were added after executable verification.

To reconstruct the exact frozen tree, extract a `git archive` of full commit
`1e349292ad7496406322abd8f1b0b7f93704045f` into a fresh evidence directory
**outside the repository/test tree**, then overlay only the four pinned repaired
runtime/test files from the reviewed PR head. This retains the initial release
document and excludes final packaging, matching the frozen full manifest.
Do not restore files into an active checkout or copy a baseline under tests.

Extract `independent-artifacts.tar.gz` outside that source tree. It contains 99
original scripts, manifests, command/exit receipts, JUnit, case ledgers, reports
and cleanup records, including the direct Spec lane. Duplicate source snapshots
and deleted generated credentials are excluded. Reports explain their source
projections and owned database setup. Adapt original local paths deliberately;
the archived paths and narrow fixture names preserve execution provenance.

Standards' `verify_packet.py` validates 38 archived artifact hashes, 94 final
case executions and the six expected negatives without a database. Functional
replays require the pinned cached Python/PG images, a reconstructed candidate
and separately owned network-none PostgreSQL fixtures. Their setup scripts
generate throwaway credentials; no production credential is needed. Do not
reuse shared/owner databases or overwrite sealed receipts.

`run-tests.py.bytes` preserves the root's exact historical command producer.
`runtime.env.example` contains its inert loopback-only inputs. A root replay
also requires separately owned current-head `b83_social_test` on internal55412
and compatibility `social_domain_test` on internal62124. `selection.txt` lists
the 33 repository modules. The supplementary official input bodies are retained
outside the public repository; missing/mismatched inputs must fail, not skip.

The cached local profile is Python 3.12.16 / SQLAlchemy 2.0.55 / Linux arm64,
PostgreSQL17 at Alembic `a756b20a0001`. A full Render image/architecture is not
recreated. The genuine national test is capped at 512 MiB. No provider delivery,
production adoption or deployment is certified by these local results.

`SHA256SUMS.json` seals the packet. Hash verification proves artifact integrity;
it does not replace executing the application or authorize source admission,
generation, a worker, upload or publication.

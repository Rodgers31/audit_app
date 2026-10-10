# Durable audit pagination design, bounded proof

Addresses [#611](https://github.com/Rodgers31/audit_app/issues/611). Launch source:
`bcb5ff99854de595bbe3f7d60cc8796b7ada5a20`, tree
`9d0061928c16d173859f98cb6daa5f2f591b257c`. The issue body/comments matched the
frozen issue on 2026-10-10. #548/#562 are accepted predecessor contracts.

This delivery is a design prototype plus compatible client bookmark parsing.
Production continues to use the unchanged epoch-zero xmin guard. No durable
production router/model or Alembic migration is activated by this packet.
The coordinator must first provide accepted #602 ancestry or explicitly release
its reservation. No `e611b11a0001` file or guessed `down_revision` is published.

## Chosen provenance

Store PostgreSQL `xid8` in an ordinary nullable `root_xid` column, assigned by an
ALWAYS BEFORE INSERT trigger using `pg_current_xact_id()`. Refuse caller-supplied
values. Do not cast wrapped row xmin, derive epoch from current server state, or
use commit timestamps. On a savepoint insert, row xmin is a subtransaction ID;
the stored root ID is the top-level ID included in a `pg_snapshot`.

A fresh read captures `pg_current_snapshot()`. Every later page applies
`pg_visible_in_snapshot(root_xid, bookmark_snapshot)` together with the existing
fixed timestamp and ID ceiling, filters and descending time/ID order. Ordinary
MVCC also limits reads to actually committed, surviving rows. A lower-ID writer
that commits after capture remains excluded; its root ID was active or beyond
the snapshot horizon. The visibility predicate alone does not certify that an
arbitrary imported transaction committed. Stored provenance must come from the
trusted database insertion path and remain immutable.

The source primitives and the subtransaction restriction are documented by
[PostgreSQL 17 transaction information functions](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-PG-SNAPSHOT).
User-column persistence across maintenance is an inference from that storage
choice, tested here with actual VACUUM FREEZE and VACUUM FULL. It does not follow
from system xmin remaining unchanged. PostgreSQL's
[system-column contract](https://www.postgresql.org/docs/17/ddl-system-columns.html)
does not provide durable full transaction provenance.

## Bookmarks and unavailable states

Use `v2:<canonical dataset UUID>:<xmin>:<xmax>:<active root IDs>` in the existing
`visibility_snapshot` string. Transport it atomically with `snapshot_id` and
`as_of`. Parse decimal xid8 values with exact integer arithmetic (Python int /
JavaScript BigInt), bounded to uint64 and the existing 4096-character budget.
The client preserves all bytes through URL/history and sends no fragment of a
malformed bookmark. The existing unversioned parser retains its epoch-zero bound.

An old unversioned bookmark presented to the prototype gets private 422 with
Refresh guidance; a scope mismatch, future horizon after counter rollback, or
expired 15-minute bookmark also requires Refresh. A missing/unsafe schema or
unknown legacy provenance produces sanitized private/no-store 503, never a
successful zero. Filter changes can reuse a valid captured population via the
API; the UI starts a fresh population on Apply filters. Role and actor cache
contracts, payload redaction, page/day/size bounds and UTC interpretation remain.

## Legacy history and migration admission

Never backfill root_xid from xmin, the migration transaction, bootstrap history,
or a present-day epoch guess. Preexisting rows stay NULL and historical insertion
provenance stays unknown. This prototype refuses the entire dataset when any
unknown row exists; even a filter apparently excluding that row does not erase
the uncertainty. It proves correctness on a freshly provisioned empty dataset.
It deliberately cannot activate a deployed audit table containing history.

A possible later legacy seal would acquire an exclusive table lock, wait for all
writers, copy/seal the exact committed immutable population, and record separate
`known_visible_at_activation` provenance. That is visibility at a measured seal,
not historical writer provenance. This packet neither implements nor certifies
that option. A production migration must preserve the rows and report that
unmet capability, rather than manufacturing a successful historical backfill.

## Authority and supported operations

The executable installer is restricted to loopback PG55534 / database issue611 /
owner inert. It is test scaffolding, not a deployment entrypoint. Fixtures use
distinct actual LOGIN reader/writer roles without owner, superuser or BYPASSRLS
authority. Column INSERT privileges exclude provenance and IDs. Reader policy
and privileges are checked; no UPDATE column grant, DELETE, TRUNCATE or TRIGGER
authority is accepted. Unknown extra/disabled/changed trigger bodies and changed
RLS policy definitions refuse. Raw INSERT, ORM INSERT and savepoint INSERT all
reach the same database trigger. ALWAYS triggers also run in replica mode.

The append-only statement trigger refuses UPDATE, DELETE and TRUNCATE, including
owner-issued statements. The capability read holds ACCESS SHARE table locks
through queries to prevent ordinary concurrent table DDL. Trusted schema owners
and superusers remain outside that threat boundary: they can alter functions,
policies, grants or data and must follow a separately accepted maintenance
protocol. A catalog check does not fence a malicious privileged operator.

| Operation | Bounded support |
| --- | --- |
| Root writer, raw INSERT, ORM INSERT, savepoint INSERT/rollback | Stored top-level provenance; actual owned transaction controls |
| uint32 epoch boundary and uint64 parser bounds | PostgreSQL xid8 predicate controls; actual epoch-one server/root transactions |
| Actual natural four-billion-transaction wrap | Not executed; no universal wrap claim |
| VACUUM FREEZE / VACUUM FULL rewrite | Actual maintenance preserves stored provenance and bookmark result |
| Application UPDATE / DELETE / TRUNCATE / provenance spoof | Actual ACL/trigger refusals preserve rows |
| Missing schema, changed RLS/trigger, unknown provenance | Actual private sanitized 503 |
| Retention | Refused by append-only trigger. A future maintenance protocol must disable capability, rotate scope and recertify before reads resume |
| Logical restore, physical restore, PITR, cloning, replication promotion | Unsupported in this prototype. Ordinary xid8 values can belong to a different transaction namespace. Restored readiness/UUID cannot self-certify origin; scope rotation alone does not repair imported root IDs |
| Prepared transactions / production pooler / deployment roles | Not certified; production prerequisites remain #583 |

No autonomous restore detector or externally anchored incarnation authority is
implemented. A stored UUID plus `ready=true` can be copied by a privileged restore.
Consequently **do not connect this prototype to a restored database or activate it
in production**. Production readiness must remain false until trusted namespace
and maintenance/restore authority are established. Capability catalog checks in
this proof cover their tested fixture profile, not every possible catalog object
or hostile superuser race.

## Measured evidence

The unchanged real HTTP launch fixture returned 200 in epoch zero and sanitized
503 in epoch one with snapshot `4294968298:4294968298:`. The identical retained
capability and lower-ID late-commit test functions pass using the prototype
reader. The fresh owned cluster's epoch was set offline after clean shutdown
using `pg_resetwal -e 1 -x 1000`; no forced reset or live server modification was
used. This is a controlled epoch fixture, not evidence of a natural lifetime
wrap or permission to reset a production cluster. The
[official pg_resetwal options](https://www.postgresql.org/docs/17/app-pgresetwal.html)
describe the epoch/counter inputs and require the server to be stopped.

At the first bounded green: 35 prototype cases passed on SQLAlchemy 2.0.54 /
Python 3.13.9 and 35 on SQLAlchemy 2.0.23 / Python 3.12.15. SQLAlchemy 2.0.23 on
Python 3.13 failed during import; that setup attempt is not behavioral red.
An RLS policy changed to `false` produced a false empty 200 before the capability
repair; the six-control refusal replay retained five positive controls and one
observed failure. These are prototype defects, not new production issue claims.
The client regression was observed red (3 failures / 10 passes), then the complete
overview/audit client cohort passed 65 cases. Later final receipts and independent
reviews bind the published bytes; historical passes remain historical.

## Integration still required

After coordinator-approved ancestry: author and test the actual ordered migration,
design legacy admission without fabricated history, establish production roles
and complete schema capability proof, integrate the router/model, certify restore
and retention refusal/recertification, replay the relevant full backend cohort
and hosted checks. #611 and #583 remain open. This bounded draft cannot be used as
hosted acceptance or production readiness.

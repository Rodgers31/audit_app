# Round20 recovery configuration supplement

The actual verified session-pooler preflight observed PostgreSQL17.6, UTF8,
ICU `en-US`, `en_US.UTF-8` collation/ctype and collation version `153.121`.
The source database owner is postgres, its tablespace is pg_default, and its
database ACL is nondefault. The pg_catalog and information_schema schema owners
are supabase_admin with explicit ACLs. Nine role/database setting records contain
15 settings. A local pinned Supabase17.6 target reproduced these properties,
ACLs and settings exactly. This is a template check, not a production archive
restore or issue-closure certificate.

Both cron.database_name and pg_net.database_name identify the observed postgres
database. It is the only non-template database, and it contains no cron/net
relations. Preloaded background worker names therefore do not identify runnable
application jobs to deactivate. The observed clients were idle; this observation
does not replace root's actual provider/service freeze receipt.

Vault secrets, storage objects/buckets, foreign servers/tables, subscriptions,
security labels, external tablespaces and custom base-type bindings were zero.
Two auth.users rows remain logical archive data. Private provider/login
credentials and service configuration remain separate recovery inputs. No Vault
root-key or storage-content retrieval was required or performed for the observed
empty Vault/storage state.

## Acquisition change

The reviewed helper appends one read-only supplemental SELECT to its existing
inventory transaction, using the same imported repeatable-read snapshot,
namespace, wall bound and sampled transport abort. It adds no connection. The
supplement captures current database creation properties and ACL, role/database
settings, system-schema ACLs, nondefault system relation/column/routine ACLs,
parameter ACLs, and counts of current activity. It captures no built-in routine
bodies or system table contents. Activity is an observation, not freeze proof.

The helper requires and validates the supplemental object before publishing
`recovery_prerequisites.json` alongside the existing archive, roles and full
non-system inventory. Its digest appears in the acquired receipt. Publication
still reports restore/completeness pending. Every changed helper byte requires a
fresh reviewed request hash before any live acquisition. The inventory helper
and its original full comparison criteria remain unchanged.

## Restore

Use a fresh exclusively owned local Supabase17.6 target. Import the role dump,
preserving ALTER statements for the pre-existing bootstrap supabase_admin role.
Create postgres from template0 with the captured owner, encoding, locale
provider, locale, collation/ctype, tablespace and connection properties. Do not
force COLLATION_VERSION to disguise a runtime mismatch: compare its actual value
against the captured value. Reproduce captured ACLs and role/database settings;
SQL list settings must use individually quoted entries rather than one quoted
comma-separated string.

Retain the reviewed compatible extension/schema placement and exact TOC
disposition from Round19. Restore with error-on-failure semantics, compare the
original full source/target inventory, then compare the supplemental durable
configuration with `compare_recovery_prerequisites`. Only transient activity is
excluded from that comparison. Restore failures, missing supplemental data or
different durable properties/permissions/settings cannot produce acceptance.

The real archive acquisition and source-to-target restore remain root-owned.
Provider configuration/freeze, a hash-bound expiring operation decision, actual
capture/restore, correction checkpoint and runtime/public validation remain
necessary before closure. The 128MiB sampled abort remains explicitly below a
hard provider ceiling; the latest local test observed 4,780,815 bytes of sampled
overshoot, superseding the previous maximum of4,766,801.

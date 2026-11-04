# Stage A recovery and offline operation accounting

Stage A restores only the first retained image and its initial manual draft into
an isolated social schema. Full application schemas are refused, including empty
non-social tables; the social migration subset is not full-head application
migration qualification. It cannot merge a capsule into an existing application
database. Before insertion, every stored table in that target schema must belong
to the explicit `EMPTY_TARGET_TABLES` inventory and contain zero rows. Accounts,
encrypted credentials, source events, worker ownership, policy state and retained
history receive no exception. An unknown table refuses even when empty. The only
permitted nonempty infrastructure table record is one `alembic_version.version_num`
equal to the reviewed `TARGET_SCHEMA_REVISION` (`a756b20a0001`). Other revisions,
multiple markers and unexpected marker columns refuse. No state is deleted to
make a target eligible.

The migration marker alone does not qualify DDL or ACLs.

The current social migrations also create two SERIAL sequences:
`social_generation_controls_id_seq` and `social_policy_selection_id_seq`. Only
those exact counters, owned by the current role, attached to the expected `id`
column, with the reviewed integer/start/increment/cache/cycle definition and
initial `last_value=1,is_called=false` are permitted. An unknown or consumed
counter refuses; no counter is reset. Views and all current-connection temporary
relations, including temporary views and sequences, refuse. No other session's
temporary namespace or view body is read.

PostgreSQL must resolve every capsule model into the selected target schema. The
current role must own that schema and every stored table, have SELECT visibility,
and use `row_security=off`; a permission or RLS failure is a typed refusal. Foreign,
materialized, inherited and partitioned storage requires another contract. Both
parent and child inheritance edges refuse, including an empty outside child.
Inheritance is rechecked after acquiring target table locks. Those locks hold
the table-row census until the caller ends its transaction; qualified stable
DDL and the isolated operator envelope remain separate prerequisites. SQLite
supports only the inert `main` target without attached, view or temporary state. These
guards establish the bounded empty-target precondition; separately qualified
migrations, DDL, ACLs, network isolation, source snapshots and custody remain
required. This is no replacement for the complete database recovery protocol.

Malformed or duplicate-key JSON, excessive JSON recursion, circular/nonfinite values and invalid
historical document or packet shapes raise `RecoveryScopeError`. Restore unwinds
its savepoint before translating input errors, so a caller can catch a refusal
and commit without keeping partial inserts. Packet readers close their directory
descriptors and preserve custody bytes. Capture validates history and all required
codec/key/size/hash/fence metadata before creating the custody directory or reading
storage. Embedded fence JSON uses the same strict decoder as rows and packet
readback. IO, database-operation failures outside
the target-census proof and interrupts retain their operational error semantics.

The V2 offline capacity assessor binds Graph confirmation routes to the selected
cohort target's account and its one observed Graph account/version scope. The
current producer cannot establish arbitrary multi-account route mappings, so
those scopes refuse. Saved remote IDs retain their target/account ownership;
duplicated ownership and a composite post ID naming another Graph account refuse.
Repeated references to the same target's same ID remain valid. These checks do
not authenticate telemetry, qualify a host, or activate any account or worker.

Both retained payloads remain charged at their full combined size. Missing or
same-size corrupted bytes, lost history, unknown write epochs, pending ownership,
unsettled fences and omitted incoming dependencies still refuse. The packet's
final directory inventory remains required. No refund, force settlement, original
deletion, retention change or production restore is introduced. Actual emulated
media-inspector and host-directory binding limitations remain launch gates.

# Reviewed logical PostgreSQL restore comparison

An ordinary logical dump recreates active SQL columns, rather than dropped
physical attribute slots. PostgreSQL 17.6's `shouldPrintColumn` excludes dropped
columns outside binary-upgrade mode. A restored active column can therefore
have a different `pg_attribute.attnum` while retaining its logical order.
ACL arrays can also contain identical items in a different order. These
representations do not justify ignoring missing privileges.

The standalone `tools/verify_logical_pg_restore.py` is an explicit alternative
to the physical inventory comparator. It does not change the original
comparator or acquisition callers. It connects only to an already restored
owned local target using the pinned PostgreSQL 17.6 image, with network `none`
and no published ports. By default it performs read-only collection as `postgres`, with
captured durable role/database settings and the inventory's UTC/date/float GUCs.
It neither restores a dump nor repairs grants.

The operator must review a private JSON request and pass its SHA-256. The request
binds the current verifier bytes, archive, capture receipt, original failed
restore receipt, target, comparison mode and these exact permitted equivalences:

- Replace each positive, strictly increasing active column number with its
  relative ordinal within that relation. Preserve active column names and order,
  types, nullability, defaults, identity/generated flags and column ACLs.
- Sort ACL array items while retaining every item verbatim, including grantee,
  grantor, privilege and grant option. Null and explicit ACLs remain different.
- For `realtime.schema_migrations` alone, permit the captured explicit ACL
  `supabase_admin=arwdDxtm/supabase_admin` to match a target null ACL only when
  both owners are `supabase_admin`, both relation kinds are ordinary tables, and
  a fresh target `acldefault('r', relowner)` readback exactly matches that item.

All remaining inventory fields, table counts and hashes, sequence states and
definitions must agree. Durable configuration uses the reviewed supplement
comparator, which excludes transient activity and compares ACL items without
array ordering. Deparser text is retained exactly; schema qualification is not
normalized. Missing GraphQL USAGE grants, including grant options, must be
repaired from the captured before-images before this verifier can pass.

Request shape (substitute reviewed SHA-256 values and the owned target):

```json
{
  "comparison_mode": "reviewed_logical_database_restore",
  "verifier_sha256": "<current verifier SHA-256>",
  "local_target": "round20_s1_actual_restore_<12 lowercase hex characters>",
  "bundle_receipt_sha256": "<capture receipt SHA-256>",
  "archive_sha256": "<database.dump SHA-256>",
  "original_failed_receipt_sha256": "<original failed restore receipt SHA-256>",
  "allowed_equivalences": [
    "active_column_physical_number_to_relative_ordinal",
    "ACL_array_order_preserving_verbatim_items",
    "realtime.schema_migrations_owner_default_with_live_readback"
  ]
}
```

```sh
python3 tools/verify_logical_pg_restore.py \
  --bundle /private/acquired_bundle \
  --target round20_s1_actual_restore_<12hex> \
  --original-failure /private/original_restore_receipt.json \
  --request /private/reviewed_logical_request.json \
  --approved-request-sha256 <reviewed request SHA-256> \
  --out /private/new_logical_verification_receipt.json
```

The output is exclusive and private, names the generator and source hashes,
records the approved comparison mode and request hash, and retains the original
failed receipt hash and the physical comparator result. A logical database pass
does not certify external storage bytes, provider credentials or application
deployment. Old receipts remain immutable; a new logical pass explains the
measurement change rather than replacing the failed physical verdict.

## Explicit proof for two legacy CHECK spellings

PostgreSQL can reparse an older stored CHECK tree into a different canonical
spelling during logical restore. A text mismatch still refuses by default.
The optional `tools/logical_restore_check_proof.py` supports only these two
existing predicates:

- `public.etl_dispatch_domains.ck_etl_dispatch_domain`: the six supported
  domain literals, including the array/per-element text coercion roundtrip.
- `public.social_privacy_ownership.ck_social_privacy_subject`: the existing
  text-length bounds, including nested/flattened AND roundtrips.

This is not a general expression normalizer. Every other catalog field, grant,
table hash and sequence state must still match through the existing comparator.
The source predicates must first pass a narrow grammar with explicit builtin
text coercions. Unknown predicates, functions, operators, types, collations,
inheritance, partitions and changed validation flags refuse.

The operator separately reviews a private plan (0600, current owner), with
exactly the two distinct identities. Each entry binds the UTF-8 SHA-256 of the
source and target definitions and the source column context. The context is
the compact JSON array of active columns in order, selecting name, formatted
type, not-null, identity and generated fields; use
`logical_restore_check_proof.column_context()` and `canonical()` to reproduce
its hash. The plan has this shape:

```json
{
  "version": 1,
  "constraints": [
    {
      "schema": "public",
      "table": "etl_dispatch_domains",
      "name": "ck_etl_dispatch_domain",
      "source_definition_sha256": "<source UTF-8 digest>",
      "target_definition_sha256": "<target UTF-8 digest>",
      "column_context_sha256": "<column context digest>"
    },
    { "schema": "public", "table": "social_privacy_ownership", "name": "ck_social_privacy_subject", "source_definition_sha256": "<digest>", "target_definition_sha256": "<digest>", "column_context_sha256": "<digest>" }
  ]
}
```

The ordinary approved request must also include this exact additional member:

```json
"isolated_check_reparse": {
  "plan_sha256": "<reviewed plan digest>",
  "proof_generator_sha256": "<current logical_restore_check_proof.py digest>",
  "grammar_sha256": "<current logical_restore_check_grammar.py digest>"
}
```

Pass `--check-reparse-plan /private/plan.json` and
`--approved-check-reparse-plan-sha256 <digest>` along with the ordinary arguments.
There is no automatic retry or silent fallback to this mode. These hash
checkpoints record operator review; they are not digital signatures.

The proof extracts only selected pre-data from the hash-bound archive, rejecting
COLLATE anywhere in that output. It checks fresh column/name resolution and
builtin dependencies on the already inspected target. It then disables local
DDL hooks inside a transaction, assumes the captured `postgres` role/search
path, and adds fresh **NOT VALID** witness constraints. A current operation
nonce binds every returned witness. PostgreSQL must produce the exact target
definition, expression, column keys and dependencies. No rows are scanned or
original constraints altered. The transaction rolls back, and full inventory,
durable prerequisites and hooks are recollected and must be unchanged, even
when witness execution fails. The local `supabase_admin` executor must have the
required authority; do not grant production privileges for this proof.

All proof artifacts live in a new private `<output stem>.check_proof` directory.
The final receipt records temporary `mutations: true`,
`persistent_mutations: false`, the raw physical mismatch and the separate proof.
Input, producer and helper hashes are rechecked before success publication.
Archive extraction is limited to 128 MiB input and 1 MiB selected SQL output.
The capture/earlier failures are never overwritten. This proves the supported
logical CHECK roundtrip, not provider recovery or a separate global effective
permission profile. Runtime temporary namespaces are not broadly filtered from
the captured catalog or ACL checks.

The collector uses LF JSON framing throughout. U+0085/U+2028/U+2029 inside
valid JSON strings are preserved; malformed UTF-8, blank interior records and
truncated JSON still refuse.

Focused verification includes an actual owned PostgreSQL 17.6 dump/restore
fixture with a middle dropped column, reordered ACL entries and the reviewed
explicit/null default ACL. Negative controls change logical column order, type,
default, grant, grantee, grantor, grant option, table presence, row data, sequence,
RLS and constraints. Run without application or shared pytest bootstrap:

```sh
env -i PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 backend/tests/test_verify_logical_pg_restore.py -v
```

References: [PostgreSQL 17 attribute catalog](https://www.postgresql.org/docs/17/catalog-pg-attribute.html),
[PostgreSQL 17.6 dump implementation](https://github.com/postgres/postgres/blob/REL_17_6/src/bin/pg_dump/pg_dump.c).
The actual source `pg_init_privs` was not captured. Provider initial-ACL
suppression is an inference, not a proven explanation for omitted GraphQL ACL
archive entries.

### Persistent permission supplement

The ordinary catalog inventory excludes `pg_` schemas. Its ACL/configuration
checks alone do not establish the separately required effective permission
profile. For original recovery acceptance, also run
`tools/verify_persistent_pg_privileges.py`; require both successful receipts.
This portable path replaces the B42 operation-specific profile comparator. It
uses the same pinned profile contract and exact SQL, retaining persistent system
schema rows while excluding only `pg_temp_[0-9]+` and
`pg_toast_temp_[0-9]+` **schema rows**. Other object/profile scope is unchanged;
this is not a blanket exclusion of temporary tables or arbitrary `pg_` objects.

Keep the original unfiltered permission matrix, capture-bound source proof and
exact source producer bytes beside the private acquisition artifacts. The
source producer must have been independently reviewed and actually executed
through the separately authorized read-only source transport. The proof binds
its producer, SQL, contract, original catalog, durable prerequisites, original
unfiltered profile and all captured roles. The verifier does **not** execute that
producer or connect to production. An approved request hash is an operator
checkpoint, not a cryptographic signature or independent proof that arbitrary
producer bytes ran; never approve a fabricated source packet.

The supported source packet is the reviewed B42 profile contract, with a valid
40-character captured commit and the original execution fields: PostgreSQL17.6,
read-only/TLS verified, publishing disabled,12off switches, zero mutations,
disposed connection and removed temporary material. Retained capture evidence
can be used later for its bound archive; its timestamp stays in the result and
is never represented as a fresh production observation. Current-source or
external-provider acceptance requires its own observation.

Prepare a new owner-only request file with this exact shape (all digests are
SHA-256; `version` must be integer1):

```json
{
  "version": 1,
  "local_target": "round20_s1_actual_restore_<12 lowercase hex>",
  "verifier_sha256": "<verify_persistent_pg_privileges.py>",
  "source_hashes": {
    "verifier": "<same verifier digest>",
    "logical": "<verify_logical_pg_restore.py>",
    "acquisition": "<reviewed_pg_acquisition.py>",
    "inventory": "<bounded_pg_backup.py>",
    "contract": "<persistent_privilege_contract.py>",
    "check_helper": "<logical_restore_check_proof.py>",
    "check_grammar": "<logical_restore_check_grammar.py>",
    "sql": "<persistent_pg_privileges.sql>"
  },
  "input_hashes": {
    "logical_receipt": "<prior logical PASS receipt>",
    "source_proof": "<retained source metadata proof>",
    "source_generator": "<actually executed reviewed source producer>",
    "original_privileges": "<original unfiltered source matrix>",
    "bundle/receipt.json": "<acquisition receipt>",
    "bundle/database.dump": "<archive>",
    "bundle/roles.sql": "<roles artifact>",
    "bundle/inventory.json": "<source inventory>",
    "bundle/recovery_prerequisites.json": "<source durable configuration>",
    "reviewed_request": "<logical receipt's reviewed request>",
    "original_failed_receipt": "<logical receipt's original failure>",
    "restored_inventory": "<logical receipt's restored inventory>",
    "restored_prerequisites": "<logical receipt's restored prerequisites>"
  }
}
```

For an approved CHECK reparse, add `input_hashes.check_plan` and pass that exact
plan with `--check-reparse-plan`. Otherwise omit both. No missing proof or failed
logical receipt is silently downgraded to a weaker acceptance mode.

```sh
python3 tools/verify_persistent_pg_privileges.py \
  --bundle /private/recovery/acquired \
  --target round20_s1_actual_restore_<reviewed-id> \
  --logical-receipt /private/recovery/logical.json \
  --source-proof /private/recovery/source-permission-proof.json \
  --source-generator /private/recovery/reviewed-source-producer.py \
  --original-privileges /private/recovery/original-privileges.json \
  --request /private/recovery/permission-request.json \
  --approved-request-sha256 <reviewed-request-sha256> \
  --out /private/recovery/persistent-permissions.json
```

The tool re-executes the approved logical verification on the live isolated
clone; a matching PASS file alone is insufficient. That may repeat only the
explicitly approved, rolled-back CHECK witness DDL and is disclosed in the
result. It then reads the complete inventory, durable configuration and
per-role permission matrix in one read-only snapshot, verifies safe catalog
resolution and checks the state again. The current supported resolution is
exactly `pg_catalog, public`; another effective schema path refuses rather than
assuming equivalent routine-argument deparse behavior. No original proof,
unfiltered matrix or failure is rewritten. New readbacks remain private; a final
PASS is published only after input and producer checks and exclusive readback.

Regression evidence includes an actual local `pg_toast` schema permission
change: ordinary logical-only verification passes, whereas this supplement
refuses. The fixture also verifies that exact runtime temp-schema creation
leaves the persistent profile unchanged and persistent `pg_catalog` /
`information_schema` permission changes remain visible. No production grant is
made by these tests or by this tool. Storage objects, provider credentials,
privacy/deletion history, host configuration and broader operational acceptance
remain separate recovery inputs.

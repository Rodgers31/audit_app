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

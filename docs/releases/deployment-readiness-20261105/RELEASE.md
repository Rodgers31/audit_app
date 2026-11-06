# Stage 6 — freeze and qualify before release authority

This is a command preparation packet. No merge, deployment, pin update, source
adoption, hosted dispatch, cloud build/download or cache invalidation is included.

1. Receive each immutable `DELIVERY-vN.json`, reviewed local commit/tree, changed
   path/hash inventory, original executions and Standards/Spec/adversarial results.
   Read dependency artifacts only. Confirm common baseline and exclusive ownership;
   hash interfaces separately from delivered bytes. Do not consume a live sibling
   worktree as final input. At this packet's freeze, no final paired source,
   backend/frontend shipping artifact, approved four native profiles or current
   schema/role readback is supplied. Those fields remain pending.
2. The coordinator prepares the exact pair for #914/#915 in an owned checkout;
   verify commit, tree, clean status and complete consumed corpus before and after
   qualification. Review all ten fresh inline findings and later material again
   at publication. Empty hosted checks do not constitute CI. No push/reply/resolve
   is part of this lane. Inspect staged files and secret/whitespace diff first.
3. Bind the approved Linux x86_64 CPython **3.12.16**, sealed 86 production artifacts
   and separate 95-package qualification set preserving those 86. Use only the
   immutable runtime lane's supported installer/verifier and already available
   caches. Two fresh owned installations must agree on installed bytes, RECORD,
   interpreter, OS, native linked libraries and OCR trained data. Retain full-host
   diagnostic inventory and security/advisory review separately from integrity.
   Migrate/bootstrap/seed/validate each need their real qualified profile. A
   Debian image, a host label or macOS stdlib tooling pass supplies no Ubuntu
   native parity. Parser/cache/proposal/readback proofs bind the same corpus.
4. Run the final affected application, transport, fiscal/debt/OAG, workflow,
   runtime timing, actual-PG helpers and supported acceptance tooling in normal
   and optimized Python. Include all original affected families, with explicit
   collected/called/JUnit inventories, no unknown skips/XPASS and exact owned
   process/container/schema cleanup. The original 36 family is **35 actual-PG
   cases plus one constant**; the fiscal API case is a direct route call. Keep
   selections separate, preserve failed originals and do not sum overlapping
   profiles. Every correction needs a witnessed pre-fix failure and final green.
5. Production runtime qualification is separate from that test environment.
   [backend/Dockerfile.prod](../../../backend/Dockerfile.prod) currently starts
   from mutable `python:3.12-slim` twice, resolves apt packages and pip wheels,
   and launches `social_worker_supervisor`. Its runtime installs ffmpeg and
   Tesseract/English, but does not request Poppler. It is **not** the sealed
   ingestion runtime/artifact. The release/runtime owner must prepare the exact
   reviewed digest-bound production-pruned artifact using approved cached bytes,
   record installed wheel/native/application inventories and resolved controls,
   and qualify startup/auth/privacy/public withholding under the nonroot launcher.
   No networked Docker build or new artifact is pulled here. Missing cached exact
   base/native/package capability remains a concrete hold; never silently use
   the development image. Preserve default-off supervisor and generation.
6. [frontend/Dockerfile.prod](../../../frontend/Dockerfile.prod) builds with dev
   tooling and optional dependencies, then prunes dev dependencies before the
   nonroot runner. It uses mutable `node:24-bookworm-slim`, while
   `frontend/.nvmrc` pins **24.22.1**. Freeze actual Node/npm/glibc/lock/public
   config/build and artifact identities, not that tag. In an owned copy only,
   use verified existing package/native caches with network denied; do not prune
   a shared installation. Execute the existing runtime and native verifiers on
   the resulting runtime tree; preserve Sharp/optional dependencies and bound
   Next public config at both build and start. Do not label Jest/typechecks a
   production build. The current local shell has no Node on PATH and Python
   3.9.6; it cannot qualify the required shipping target. No substitute installed.

Prepared frontend commands, after the exact owned cache/runtime/sandbox and public
configuration are reviewed (not executed by this packet):

```sh
node scripts/verify-node-runtime.cjs
npm ci --offline --include=dev --include=optional --no-audit --no-fund
node scripts/apply-tooling-repairs.cjs --check
node scripts/verify-tooling-inputs.cjs
node scripts/container-config.cjs validate
npm run build
node scripts/container-config.cjs record
NATIVE_VERIFY_CACHE_DIR="$QUALIFIED_EXISTING_MODEL_CACHE" npm run verify:native
npm prune --offline --omit=dev --include=optional --ignore-scripts --no-audit --no-fund
node scripts/verify-runtime-dependencies.cjs
node scripts/container-config.cjs runtime
```

These commands have a read-only source template and writable **owned** build copy,
scratch HOME/cache/tmp, no inherited credentials or lifecycle configuration,
`NEXT_TELEMETRY_DISABLED=1`, reviewed `ONNXRUNTIME_NODE_INSTALL=skip`, explicit
public `NEXT_PUBLIC_*` values, resource/time/byte bounds and the shared heavy lock.
Offline npm refuses absent cached artifacts; it is not permission to fetch them.
The existing model cache must be complete and hash-qualified before the native
embedding check: prepareModel may otherwise attempt a download, which the sandbox
must deny. Run that build-tool check before pruning Transformers/ONNX; the pruned
runtime verifier separately exercises Next/Sharp image decode afterward.
Qualify the complete final runner artifact with health/private-route/public-data
checks on isolated loopback under the same bounds. Record any lifecycle refusal
as a missing prerequisite. Do not start the serving app or social worker.

## Schema, role, TLS and serving preflight

Use only an existing approved bounded read observer; no credential discovery,
key/grant changes or DDL. The prepared
[catalog_preflight.sql](../../../scripts/verification/deployment_readiness_20261105/catalog_preflight.sql)
uses RR READ ONLY, row_security off, 3-second statements and 1-second locks. Its
`public` namespace is explicit; a different actual namespace requires review.
Connect through the existing qualified reader with verify-full and existing CA,
connect timeout 3 seconds and outer deadline at most 35 seconds. Driver TLS/target
qualification covers the caller-to-pooler leg; pg_stat_ssl describes the connected
PostgreSQL backend leg and cannot attest every proxy/client or physical identity. Read only hashed
endpoint/login references, actual TLS, schema, catalog ACL/RLS/membership/view
metadata and process counts; do not export application rows or SQL text.

The optional native view pair's names, normalized definition SHA256, owner equality,
private snapshot/table and column ACLs, exact security barrier, five columns/types
and sole valid `_RETURN` rule must match final
`backend/social/worker/role_contract.py:452–478`, including when generation is OFF.
The report views have their separate three-column contract. Raw MD5s from the
prepared SQL are drift indicators, **not** the normalized verifier result.
The actual worker verifier also takes `SELECT ... FOR UPDATE` (`:490`), so do not
call it as a read-only production observer. Exact role/trigger/policy acceptance
needs the final approved contract and separately reviewed installed observation;
no automatic installation/update is provided here. Verify migrations as an
actual single graph, not inferred from table existence. No timed migration.

Before any later release decision: fill rollback packet; exact source/public
withholding/adoption authority; production schema/role/TLS preflight; all four
OFF controls plus separate drafts/shadow master and source-hook witnesses;
account pauses; worker/process census; current health/auth/privacy. Reconcile
repository writer source and serving source as distinct identities. Only later
explicit release authority can authorize merge/deploy. Only after production
readback can separate exact-source authority advance the ingestion pin. Preserve
branch rules, disabled deployment automation and cost guards.

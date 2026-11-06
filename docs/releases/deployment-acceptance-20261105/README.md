# Supported local acceptance interfaces — 5 November 2026

The recorder now supports the actual backend cohorts, owned PostgreSQL fixtures, and optimized Python. Local execution, source authority, database observations, and operational acceptance remain distinct. No local verdict authorizes source adoption, hosted dispatch, deployment, admission-pin changes, publishing, uploads, publishing workers, or financial draft generation.

## Recorder and verifier

Run inside a bounded OS sandbox: source/toolchain read-only; scratch-only writes; no external network; an isolated loopback namespace shared only with owned PostgreSQL; explicit CPU, memory, process, file-size, disk and wall-clock ceilings. Hold `/tmp/auditgava-launch-heavy-20261103.lock` outside the sandbox for the entire resource lifetime. The recorder also locks inside its own namespace. No nested recorder suite should run while that same inner lock is held.

Supply a fresh external output, an exact nonempty JSON list of expected pytest node IDs, the sealed runtime lock, and this explicit backend configuration:

```json
{
  "schema": "nightly-backend-config-v1",
  "plugins": ["pytest_asyncio.plugin", "acceptance_backend"],
  "pg_url": "postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture",
  "fixture_token": "REPLACE_WITH_32_LOWERCASE_HEX_DIGITS",
  "original_family": "none"
}
```

`original_family` is `none` for a cohort without the original source family. For `original36`, the frozen inventory in `acceptance_inventory.py` must execute: **35 actual PostgreSQL cases and one constant**. Collection establishes the expected inventory only; successful setup/call/teardown phases, JUnit identities, observer results and cleanup must independently match it. Skips, xfail/XPASS, duplicates, absent cases, source/corpus/helper/runtime changes and nonzero exits refuse.

From the sandbox, with `REPO`, `OUT`, `EXPECTED` and `CONFIG` referring to its measured checkout and fresh external scratch paths:

```sh
python -B "$REPO/tools/nightly_acceptance_20261105/record.py" \
  --repo "$REPO" --output "$OUT" --expected "$EXPECTED" \
  --backend-config "$CONFIG" \
  --runtime-lock "$REPO/backend/ingestion-qualification.lock.json" \
  --timeout 500 backend/tests/test_refresh_current_run_postgres.py
python -B "$REPO/tools/nightly_acceptance_20261105/verify.py" "$OUT/execution.json" --repo "$REPO"
```

The expected inventory and selected targets must describe the same actual cohort; select the original36 nodes as well when that profile is required. Repeat into a different fresh output with `--optimized`; this actually starts the pytest child with `-O`. The keyword-only Python API is `record.run(..., backend_config=..., optimized=False, native_profile=None)`. A native run additionally requires its actual reviewed `--native-profile`; the Python-only qualification profile cannot certify native/Ubuntu parity.

Configured runs use `nightly-local-execution-v2`. Ordinary pre-existing v1 invocations and common helper APIs remain supported. The verifier reconstructs the exact configured argv/environment, validates the retained invocation, reads original receipt/artifact paths through held no-follow descriptors, and rechecks their identities through consumption. Symlink ancestors, hardlink aliases, same-byte substitutions and changed originals refuse.

## PostgreSQL ownership

The provisioner must own the ephemeral server, including its isolated namespace and storage. Before the tests start, create the dedicated `auditgava_refresh_fixture` and `fiscal_fixture` databases and place this exact database comment on each:

`nightly-acceptance-owned-v1:` followed by the run's 32-character token.

This comment is an ownership marker for a separately isolated test server, not production authentication. Never mark an existing/shared/production database to make a test pass. The fixtures observe actual database/server/port, session/current role, database owner and the shared-catalog marker before DDL. They reject every URL option, fragment, encoded alias, password, other target/port/driver, absent token and ambient `PG*` override. Libpq receives pinned loopback hostaddr/host/port/database/user, an inert absent passfile, bounded connect/statement/lock/idle timeouts, and no ambient production credentials.

`backend/tests/acceptance_owned_pg.py` supplies `owned_schema()` for each fixture, with a unique schema, owner/comment revalidation before exact drop, and a new-connection absence check. Population cleanup cannot drop a neighboring current-run fixture or unrelated public `IngestionJob`. The canonical backend fixture still executes its real application/transaction behavior inside that owned schema. `owned_reader(schema, token=...)` opens an existing owned schema read-only with a coherent snapshot; it creates, repairs and drops nothing.

The outer provisioner must independently prove exact process/container/network/volume absence. A schema observation or reaped pytest leader cannot substitute for physical container cleanup. Do not prune shared resources.

## Semantic importers and plans

`operational.validate()` remains a structural-only full15 reader with a pending verdict. Weekly/bootstrap coverage uses the distinct `nightly-weekly-operational-envelope-v1` schema and `validate_weekly()` / `--kind weekly-bootstrap-native`. Its inventory is OpenData plus the ordinary fifteen domains with bootstrap enabled. Ordinary full15 never widens silently.

The supported semantic interface is `operational.observe_local(input, backend_config=..., signing_key_file=...)`, also exposed through `operational.py --semantic-local` and `ledger.py check-semantic-local`. It consumes `nightly-semantic-local-input-v1`, using exact artifact references (`path`, `sha256`, `size`) for the plan, current-run context/report, signed refresh capture and serving census; an owned `pg_schema`; explicit run binding; OAG source observations; and fiscal/debt expectations. Unknown fields/schemas refuse.

The importer opens only the ownership-checked fixture reader, recomputes the actual current-run classifier against stored PostgreSQL jobs, observes actual schema revision/role/columns/constraints/RLS/ACL, verifies HMACs and exact worker/page acknowledgments, and calls the domain authority adapters. An arbitrary attachment or an asserted success cannot establish these observations. A recognized source hold may remain refresh-eligible while source completion is red. The result stays `LOCAL_SEMANTIC_OBSERVATIONS_ONLY_OPERATIONAL_GATES_PENDING`; prepared ledgers remain pending.

`acceptance_refresh.capture_loopback()` observes real Linux serving children/listener identities, sends genuine signed requests to loopback cache routes, requires generation/source/adoption acknowledgment from every serving worker before contacting the frontend, and retains exact requests/responses plus a sealed transcript. Header/body reads share an absolute deadline; timeout, false/missing/duplicate/stale/wrong-source acknowledgments and partial page sets refuse. `verify_capture()` performs genuine offline HMAC verification against an explicitly supplied key and expected run/census. Offline verification is not a new live-host observation. Tests use only inert keys and an inert frontend responder; actual deployed page/rendered-value acceptance remains separate.

`observe_oag_acquisition()` checks real source/job/extraction/origin lineage and identical original/retained bytes without granting publication authority. `observe_oag_report()` additionally invokes the actual current native publication reader and binds the exact source bytes. Inert PDF envelopes cannot earn native publication authority. Fiscal/debt observations consume the fiscal lane's static `services.fiscal_authority.verify_fiscal_debt_authority` port; until its immutable delivered schema is integrated, that authority remains held.

## Remaining integration authorities

Local fixture evidence cannot close final native runtime/corpus qualification, original provider retention and current-job source adoption, the final fiscal/OAG delivered contracts, actual release role/schema policy, deployed serving identity/rendered pages, or full15/replay/daily/weekly hosted observations. Those require their specific immutable deliveries and separately authorized observations. No pending ledger is stamped passed by this tooling.

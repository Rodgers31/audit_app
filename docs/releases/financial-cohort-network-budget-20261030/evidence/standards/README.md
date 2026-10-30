This is the portable **original candidate-7 Standards evidence**, not a new test run or acceptance of the later per-phase timer repair. The original 74 cases and 450.008-second sleeping-driver result describe the backend at `d0da4996327213049614cd8f09b373bcaa856a23`, bridged by exact file hashes to frozen candidate 7. Current phase-repair validation is separate.

`index.json` maps all 27 final-receipt artifact declarations, three imported independent fixtures, the prior diagnostic receipt and its 33 hashed artifacts. Original bytes are unchanged. Python inputs use `.py.bytes` storage names to avoid pytest discovery; replay projects them back to their original filenames outside the repository. Initial harness failures and the 130 ms desired RED are historical diagnostics, excluded from the final 74 passing identities. Retained-fixture status files are historical; `FINAL7-CLEANUP.json` is the final cleanup record.

The original full 5,814-file manifest is included. `source/source-bridge.json` pins all 1,451 backend files plus the seed workflow from the Git commit above. It does not claim full-tree equality after release documentation was appended. No source snapshot is copied. One prior-diagnostic parent-production checksum remains explicitly reference-only: its data dump is not a final-74 input and is not bundled. No primary acceptance artifact or fixture is missing.

Inspect without workstation paths, from any checkout containing this packet:

```sh
PACKET="$PWD/docs/releases/financial-cohort-network-budget-20261030/evidence/standards"
docker run --pull never --rm --network none --cpus 1 --memory 2g --pids-limit 256 \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PACKET:/packet:ro" \
  admin-redesign-python-runtime:local python /packet/tools/verify_packet.py
```

Success says `verified_archive` and `tests_rerun: false`. It checks the complete physical inventory, generator hashes, every declared byte hash, source bridge, recorded child exits and all 74 unique JUnit identities. Missing, changed or linked artifacts refuse. It does not convert a copied receipt into fresh acceptance.

For an optional fresh replay, use a clean historical worktree at the commit above. The replay tool verifies the complete backend inventory before mounting it; it refuses a modified/current phase-repair tree and never checks out or changes source for you. Use a fresh output directory outside both source and packet:

```sh
PYTHONDONTWRITEBYTECODE=1 python "$PACKET/tools/replay.py" \
  --repo /path/to/clean-d0-worktree --out /path/to/fresh-replay
```

This default prints the exact capped Docker plan and runs no tests. Add `--execute` to provision a new isolated PG namespace, apply the unchanged migrations, execute the original 74 cases, reconcile their identities and remove that owned container/tmpfs. It takes roughly eight minutes. It mounts only the verified backend, seed workflow and external replay inputs; it forwards no provider environment. Old absolute paths and commands in archived receipts are provenance text, not replay inputs. Fresh outputs never overwrite historical artifacts.

Replay requires Docker and the cached Python/PostgreSQL image IDs in the original receipt. Images/dependencies are not bundled; the tool uses `--pull never`, refuses missing prerequisites, and performs no installation, download or build. The only DSN in preserved commands is the password-free, isolated loopback test database. No private environment files or production data dump are included. `tools/publish_index.py` is the one-time packaging producer and deliberately refuses an existing index.

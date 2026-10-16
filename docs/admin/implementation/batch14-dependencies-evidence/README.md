# Batch 14 dependency investigation packet

Read [the handoff](../BATCH_14_DEPENDENCIES_HANDOFF.md) for the rejected-candidate decision and limits. This packet ships documentation and executable investigation fixtures. The argparse 2 override is not applied to the application.

## Supported portable replay

Prerequisites: Git with frozen commit `3f3b1f1981b93c3317e204defbd235121c1df084`, Python 3.9+, Node compatible with the frozen manifest, npm, `patch`, and network access to the official npm registry. No developer home paths or pre-existing candidate are required. Use absolute caller-selected paths for `REPO`, `PACKET`, `FIXTURE`, and `RUNS`; both output directories must be fresh and external to the repository. Run from any cwd:

```sh
REPO=/absolute/path/to/audit_app
PACKET="$REPO/docs/admin/implementation/batch14-dependencies-evidence"
FIXTURE=/absolute/owned/fresh-fixture
RUNS=/absolute/owned/fresh-runs

python3 -I "$PACKET/portable-replay.py" prepare --source "$REPO" --output "$FIXTURE"
# baseline lifecycle succeeds; candidate lifecycle must fail with:
# tooling repair: missing locked sprintf-js

node "$PACKET/spec-review/blocker.cjs" \
  --baseline "$FIXTURE/baseline/frontend" --candidate "$FIXTURE/candidate/frontend" --output "$RUNS/blocker"
node "$PACKET/spec-review/review.cjs" \
  --baseline "$FIXTURE/baseline/frontend" --candidate "$FIXTURE/candidate/frontend" --output "$RUNS/spec"
python3 -I "$PACKET/standards-review/run.py" \
  --baseline "$FIXTURE/baseline/frontend" --candidate "$FIXTURE/candidate/frontend" --output "$RUNS/standards"

# Same modes are directly available through the isolated Python entry point:
# python3 -I "$PACKET/portable-replay.py" spec --baseline ... --candidate ... --output ...

BATCH14_REPLAY_BASELINE="$FIXTURE/baseline/frontend" \
BATCH14_REPLAY_CANDIDATE="$FIXTURE/candidate/frontend" \
BATCH14_REPLAY_TEST_OUTPUT="$RUNS/regression" \
  python3 -I "$PACKET/portable-replay.test.py"
python3 -I "$PACKET/replay-boundaries.test.py"
python3 -I -O "$PACKET/replay-boundaries.test.py"
```

`prepare` copies only the complete frozen `scripts/`, `eslint-rules/`, manifest and lock install inputs from Git, then applies both committed patches using `patch -p2`. It checks exact source hashes before npm runs. It performs normal script-enabled `npm ci --include=dev --include=optional --no-audit --no-fund` on each graph. `ONNXRUNTIME_NODE_INSTALL=skip` follows the existing CPU install setup and avoids the optional GPU download. The candidate's expected lifecycle rejection still leaves installed packages available for bounded diagnostic investigation. Do not treat it as an accepted install.

Each invocation uses a new owned temporary HOME, TMPDIR, npm cache and empty user/global npm configuration, forwards only explicit inert environment values, and removes those temporary resources even on errors. Unexpected `.npmrc`/`npm-shrinkwrap.json` files and modified/missing frozen inputs are refused before npm runs. `standards` also installs another candidate copy in its own temporary tree. It does not audit the registry or refresh historical advisory counts. Missing/invalid roots, repeated output paths, source changes and unexpected child outcomes fail visibly. All outputs stay external; no historical receipt is overwritten.

Receipts record actual argv/cwd, safe child environment, generator/input hashes, starting Git HEAD/tree/status, raw output hashes and separate child/verification results. Source binding covers the replay executables, candidate patches, frozen install inputs and installed JS/JSON/patch bytes. Installed links are refused except npm bin links to real files within the same node_modules and the exact frozen local eslint plugin; allowed literal/resolved targets and target bytes are bound. Cycles and escapes are refused. It does not attest native binaries, a complete operating system, production parity or advisory freshness. `spec` executes nine NYC config cases, thirteen real CLI cases including both version flags, and both repair modes on each graph. `blocker` independently reaches the exact missing-lock guard with valid repaired braces in both repair modes. Success means the expected observations were reproduced, including the candidate's empty version output and rejected installation. `candidate_compatible` remains false.

The fixture output retains installed baseline/candidate trees until the caller finishes all replays. Remove **only the exact owned** `$FIXTURE/baseline` and `$FIXTURE/candidate` directories after verification; keep raw receipts/results. These are disposable copies. No service, browser, account, database or application write is involved.

## Historical evidence and integrity

All original raw stdout/stderr, JSON results and receipts describe the original October 16 investigation. `HISTORICAL_ARTIFACTS.json` maps their unchanged hashes and original commit. Old generators are preserved as `historical-source/*.txt`; the original reports explicitly retain their historical commands/draft hashes. Their author paths may no longer exist. Earlier receipts that recorded `cwd: "None"` do not establish the actual execution cwd. Fresh portable receipts record a real absolute cwd.

The original packet `SHA256SUMS.json` verified all 87 entries at the original head; the reviewed draft snapshots were already qualified as earlier text. The current manifest is refreshed after this repair. Its hashes establish packet byte identity, not compatibility or remote acceptance. Validate the whole current inventory with `python3 -I "$PACKET/verify-packet.py"`. That verifier refuses missing/extra files, links and changed bytes.

`probe-argparse.cjs` remains diagnostic: exit 0 means observations were emitted. Read nested child outcomes, `repair` and `nycConfig`; no PASS/compatibility verdict follows. `cli-version.test.cjs` is the original package-version assertion: baseline passes, candidate fails at the first flag because stdout is empty. The portable specification cases separately execute both flags. Original audit/advisory/registry snapshots remain capture-time evidence and must be refreshed before a future upgrade decision. No full frontend/native/hosted acceptance is claimed.

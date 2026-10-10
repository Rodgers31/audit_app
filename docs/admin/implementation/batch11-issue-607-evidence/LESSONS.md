# Evidence-backed proposals for coordinator review

Shared skills were read-only. These are proposed clarifications, not policy edits.

- `diagnosing-bugs`: distinguish an actual server 200 from its delivery/commit.
  The pending-delivery control reproduced the exact original URL assertion but
  cannot establish the old completed-response cause. Keep both facts visible.
- `receipt-provenance`: source-set checks must include test/config/probe inputs,
  not only product files. The v3 recorder omitted a new external probe directory;
  its prelaunch generated-source manifest is retained as a separate limitation.
  The later recorder measures both source and known helper bytes before/after.
- `claims-need-receipts`: configured workers and actual workers are different
  facts. One sequential spec file can run on one worker despite a two-worker
  configuration; failed cases may create replacement workers.
- `adversarial-verify`: require a semantic red and explicit focused-case counts.
  Independent executable controls found that the first packet checker accepted
  a red-labeled all-pass report, producer drift, and skipped focused checks.
  Identical hostile inputs demonstrate the corrected rejection. Duration,
  Docker running state and child exit metadata also reject boolean coercion.
- `regression-fixture-on-fix`: preserve the original case byte-for-byte and add
  observable boundary checks separately. An incorrect selector is a harness
  error, not product red. No invented scroll reset, added sleep or widened
  saved-position assertion explains the historical #601 observation.

The next #601 experiment should record the actual saved restoration target,
layout clamp limit, native/Next scroll calls and focus across the historical
hosted environment. Local successes and forced Y=0 controls cannot settle it.

- `tool-verdict-discipline`: a valid failure corpus can pass integrity checks
  while full behavioral acceptance remains false. Keep an explicit mode and
  false acceptance flag, and require default rejection of unexpected cases.
  Independent hostile controls cover the failed-corpus mode and boolean typing.
- `prove-baseline-alive`: a stale disposable database can fail fixture startup
  before any browser case. Preserve that setup receipt, verify exact container
  ownership, and recreate only the owned fixture databases before resuming.
  A setup retry must not be described as a behavioral red/green.

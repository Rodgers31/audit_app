# County tab navigation: causal verification for #450

The county-tab stall is caused by a lost render retry in the Flight navigation
started by `router.replace` for a client-only tab selection. The app now uses
Next's integrated native `history.replaceState` for that query change. The real
lazy tab still loads on selection and consumes its normal API reader. The
server page continues to use `fy` for its prefetch; it does not consume `tab`.

This is a local county-tab fix. The verification uses a production build with
invented fixture data, and does not establish deployed behavior or a general
React/Next scheduler fix.

## Captured cause

The fresh baseline, `b8256d20d396b6fb642f8246a93ba74474e60a97`, reproduced the
original stall on iteration 3 of `FAST_BASELINE_V1`. The selected converted
loader Promise fulfilled with the exact MoneyFlowTab export and the exact lazy
payload result. The URL stayed on Overview, the tab remained a skeleton, and
no money-flow API request occurred before intervention. The first valid Health
button click resumed rendering and caused the actual money-flow request and
visible procurement note.

The first renderer observation was insufficient on its own: a fulfilled
wakeable ping during render and `callbackPriority=0` also occurred in healthy
runs. An independent reducer found healthy fallback-commit timers, so later
probes captured `timeoutHandle`, `callbackNode`, and `cancelPendingCommit`.

The reduced reproduction delivers three unchanged segments of the actual
county navigation Flight response:

1. Send the shell and hold the outer county model, record `2`.
2. After React attaches its first real RSC wakeable, deliver that model and
   the client module reference, while holding the child model, record `e`.
3. When React throws the child wakeable, hold its next MessageChannel task,
   deliver the remaining stream, wait for the decoder's `resolved_model`
   status, and resume the original queued task in order.

The pending child is then initialized synchronously by its real RSC `then`.
Its ping occurs with the same rendering root, exit status 4, execution context
2, and matching lanes already suspended. The vendored renderer's
`pingSuspendedRoot` branch leaves the work-in-progress ping mask at zero. The
following `markRootSuspended` clears the matching root ping lanes. The frozen
root has pending/suspended/warm lanes, no pinged lanes, `callbackPriority=0`,
`callbackNode=false`, `timeoutHandle=-1`, and `cancelPendingCommit=false`.
The gate has resumed and its queue is empty; the real RSC response is 200,
the selected tab module is resolved, and the real money-flow reader has not
been requested. The Health click revives the same page.

The initial controlled loop was **4 failures / 5 observations**. The healthy
observation received a money-flow store update while the task was held, which
replaced the suspended render. Settling the initial fiscal-year and
accountability notifications before selection produced **3 failures / 3
observations**. These are controlled-order results, not incidence estimates.

## Fix and negative control

`CountyDetailClient` keeps the immediate tab selection and lazy imports. It
reads the current browser URL, changes only the tab parameter, and replaces
the history entry through Next's supported History API integration. This
preserves fiscal year, other parameters (including duplicates), pathname,
hash, and history length. URL changes from back/forward also synchronize the
selected tab. The existing tab-bar scrolling and rejected-chunk boundary are
retained.

The fixed client source SHA-256 is
`884b105e4e40e1d7398dfd1d5aa8bf55f2096c49ee5b4bcd90870a57739e1c1e`.
The negative control restores only `router.replace`, its import/reference,
and callback dependency; it retains the new URL composition and URL-tab sync.
Its source SHA-256 is
`40450f0916f4f291865817884043d8f89828df9cab73a37aed15c1cfdd5b0580`.

| Exact source/order | Outcome |
| --- | --- |
| Original client, settled two-stage stream order | 3/3 stalled |
| Fixed client, same producer and order setup | 3/3 passed; no tab Flight request; actual API/data visible |
| Navigation-call-only negative control | 3/3 stalled; same resolved-module/no-request signature |
| Restored fixed client, final production build | 3/3 passed; no tab Flight request; actual API/data visible |

The method-only negative control isolates the removal of the asynchronous
Flight navigation as the causal change. This does not rely on healthy-run
exhaustion, a module mock, a hand-built lazy payload, an added retry, eager
loading, changed product timeouts, or upgraded dependencies.

## Durable and independent verification

The new `county-tab-navigation.spec.ts` holds the actual manifest-selected
Money chunk, then releases it and requires a real money-flow 200 response,
the selected FY2024/25, rendered KES 8.00B allocation, procurement note, and
source link. A tab-induced Flight request is held as a hostile transport
condition and must never be issued. Tests also require URL/hash/duplicate
query preservation, stable document and history length, reload, Overview
canonicalization, and same-page history restoration at 375 and 1280 pixels.

All four new cases failed against the original build. The navigation-only
negative control failed both transport cases specifically because it issued
one Flight request. The final build passed **12 browser cases**, including
all four new cases, all four inherited chunk-recovery cases, three-stage
data, fiscal-year switching, the committed-amount note, and reload/history.
There were no retries, skips, or flaky results.

An independent agent executed **4 additional browser cases**, using actual
DOM clicks through six rapid selections while the real Money chunk was
pending, keyboard activation, grade-button navigation, invalid tabs,
encoded/duplicate parameters, fiscal-year back/forward changes, reload,
real API responses, rendered data, and source links at 375/1280 pixels.
Its source binding matches the final client bytes.

The existing shell unit tests now assert the actual jsdom URL and history
instead of a mocked router replacement call. The focused shell, Money tab
state, and amount-coverage suites passed **26 tests**. The final Next build
passed lint and type validation; `git diff --check` passed.

## Evidence and reproduction

The immutable evidence bank is:

`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170`

Key artifacts use the `ROUND20_SESSION_4_` prefix:

- `STREAM_GATE_V3.mjs`: actual loopback response splitter.
- `STREAM_ORDER_PROBE_V6.mjs`: exact settled-order producer used for all four
  source variants; receipt includes its SHA-256 and per-case trace.
- `FAST_STREAM_SETTLED_RED_V1.json`, `FAST_STREAM_SETTLED_FIXED_V1.json`,
  `FAST_STREAM_SETTLED_NEGATIVE_V1.json`, `FAST_STREAM_SETTLED_FINAL_V1.json`.
- `FIXED_CLIENT_V1.tsx`, `NEGATIVE_CLIENT_V1.tsx`: frozen source variants.
- `BASELINE_BROWSER_RESULTS.json`, `NEGATIVE_BROWSER_RESULTS_V1.json`,
  `FINAL_BROWSER_RESULTS.json`, `JEST_V1.log`, `JEST_V2.log`.
- `ADVERSARIAL_STREAM_REDUCTION.json`, `ADVERSARIAL_GATE_VALIDATION.json`,
  `ADVERSARIAL_FIXED_V1.json`, `ADVERSARIAL_REPORT.md`,
  `ADVERSARIAL_FINAL_REPORT.md` and their generators.
- Build directories and hash inventories for the baseline, fixed, negative,
  and final sources; final handoff and receipt inventory.

In the assigned worktree, services ran on task-owned loopback ports 3364
(frontend), 8364 (API), and 3365 (stream-order proxy). Node was 22.19.0.
The backend ran in the existing Python 3.13 environment with a disposable
SQLite fixture, both environment-file loaders disabled, external HTTP
blocked, and seeders/warmups disabled. Browser external hosts were blocked.
No live PostgreSQL, provider, GitHub, Actions, paid, or desktop UI operations
were used. Shared dependency bytes were read-only.

The bank runner provides the exact allowlisted build/start/API environment.
These are the recorded commands from separate owned terminals. Replay from a
fresh evidence copy with a new embedded artifact prefix and receipt label;
the bank's existing output paths are frozen.

```sh
B=/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170
NODE=/Users/roger/.nvm/versions/node/v22.19.0/bin/node
python3 "$B/ROUND20_SESSION_4_RUN.py" api
python3 "$B/ROUND20_SESSION_4_RUN.py" build
python3 "$B/ROUND20_SESSION_4_RUN.py" start
"$NODE" "$B/ROUND20_SESSION_4_STREAM_GATE_V3.mjs"
"$NODE" "$B/ROUND20_SESSION_4_STREAM_ORDER_PROBE_V6.mjs" 3 FAST_STREAM_SETTLED_FINAL_V1
python3 "$B/ROUND20_SESSION_4_FINAL_RUN.py" browser county-tab-navigation.spec.ts county-tab-recovery.spec.ts follow-the-money.spec.ts user-flows.spec.ts --grep 'county tabs at|follows restored query state|recovers rejected code|renders exactly three stages|switching fiscal year changes|committed-amount note|detail tab selection survives'
```

For a new experiment, use a fresh receipt label and a fresh proxy artifact
prefix so existing evidence is not overwritten. A red replay needs the frozen
original or navigation-only negative source in an owned disposable checkout.
The current fixed source deliberately never enters the tab Flight gate.

The gate's MessageChannel wrapper is global; the observed held queue contains
one original task. Independent execution verified FIFO resumption and exact
concatenation of the three saved upstream response segments. Browser traces
verify RSC status/network completion, but do not contain a separate wire-body
dump. Renderer instrumentation is diagnostic and is not shipped in the app.
The retained invalid broad-prefetch proxy attempt is excluded from product
failure and healthy-run counts.

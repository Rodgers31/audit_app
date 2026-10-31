# Overview capacity retry: independent executable Spec review

**Scoped frontend acceptance. No remaining confirmed finding.** The final run executes105 passing cases, zero failures/skips:60 independent controls plus45 repository retry cases. All five independent integrations render the actual Overview with real QueryClient, real Axios interceptors and real decoders. Backend repairs and production recovery are outside this result.

## Reviewed identity and execution

Base HEAD: `12b79d361eea0cfb7113d51155bf7a2489a1d076`. The final immutable frontend projection has838 files, mapping SHA256 `898853c53c560452bc03f44b63e7ff4241536f52abf220a29900fbc10e7f2bf8`.

- `frontend/lib/api/axios.ts`: `8bf17d9e1ab78965a9f904cd77a4d598faca49114334c25b0786cdf6f8df3fa4`
- `frontend/__tests__/lib/api/retryAfter.test.ts`: `7d021f0c15f6b2dbdd7bf18c26b0a3f9aa30f75024dabc9d79e26713ade3b768`
- Independent fixture: `90970753a17d47e6663cc769a425e3b9be80619a1efff4d26f807ce163370965`

All838 projected files and corresponding checkout inputs were rehashed unchanged after execution. `final-2.command.json` retains the exact command: cached Docker image `sha256:e1582112fb9f152ed38eefcd712efc93fee1becb519fdfa57574d5e07eaa5e7d`, linux/amd64,1CPU,1GiB,256PIDs, networknone, read-only source and dependencies. Actual runtime checked Node24.22.1 and locked Axios1.20.0. Jest uses explicit `/work/frontend` root/module resolution and an external evidence harness; no install occurred.

The recorded invocation runs the independent fixture and three repository suites through actual Axios custom adapters. Result: **105/105, exit0**,1.971s Jest. Repository counts are25 current Retry-After,19 original browser-budget and1 server-budget cases. `CASE-LEDGER.json` lists every unique executed test identity; repeated prior executions are not added to this count.

## Independent controls

| Group | Cases | Executed outcome |
|---|---:|---|
| Malformed or outside-contract normalized headers |30|Arrays/objects/null, NaN/infinities/negative/bool, empty, fractions/exponents/hex, comma/date, non-ASCII digits/spacing, over-budget and normalized nonnumeric values refuse without replay.|
| Axios-normalized valid raw headers |2|Raw LF/CRLF suffixes become numeric1 upstream and recover in two bounded attempts.|
| Valid finite delay and minimum backoff |7|0/1 use1500ms;2 uses2000ms;3 and003 use3000ms; permitted spaces/tabs retain bounds.|
| Repeated capacity refusal |3|Exactly three dispatches;4500ms total waiting for0/1 and6000ms for3.|
| Mutation refusal |5|POST/PUT/PATCH/DELETE/OPTIONS dispatch once.|
| Mixed statuses, HEAD/case handling, other permanent statuses |3|A single shared attempt budget; HEAD recovers;401/403/404/429 stay failures.|
| Cancellation boundaries |3|Pre-abort sends zero adapters; one request can cancel without cancelling an independent request; abort during pending session retrieval prevents dispatch.|
| Payload/request integrity and token refresh |2|Exact successful object, parameters, headers and signal survive retry; same-session refreshed token is reacquired.|
| Actual Overview integrations |5|Detailed below.|

Every independent case asserts zero unexpected fetch/XHR calls. HTTP behavior is provided through an owned Axios adapter; no real HTTP/provider call is credited.

## Actual Overview integration

The real page issues seven concurrent reads for ingestion totals, calendar schedule, calendar health, people, recorded actions, failures and social status. With one503/Retry-After1 per endpoint, all seven dispatch once, remain pending before1500ms, then recover on their second dispatch:14 total adapter calls, seven successful query states, correct decoded UI and enabled Refresh button. No manual refresh action occurs. Publishing remains shown paused and unavailable worker evidence stays explicitly unavailable; this does not invent a healthy worker.

Permanent503 without advice and malformed advice stay unavailable after one dispatch each. A recovered200 with NaN ingestion totals is rejected by the actual decoder after two dispatches. The remaining valid responses recover normally; no invalid evidence is rendered as a count.

Switching verified actorA to actorB during all seven backoffs aborts every old signal. There are exactly seven A dispatches and seven fresh B dispatches, no A replay, and only B query keys remain. Revoking admin/session while the seven reads wait produces seven total dispatches, all signals aborted, no replay and the access-required state. Unmount similarly aborts all seven pending logical reads without replay. These controls use controlled auth/session ports; they do not claim to exercise real Supabase events or unsignalled callers.

## Rejected S1 hypothesis and retained failures

I initially called raw LF/CRLF acceptance a strict application-header defect and attributed it to JavaScript's final-dollar anchor. That causal claim was incomplete. Executable probes show locked Axios1.20.0 sanitizes both raw objects and mutated AxiosHeaders instances before the application interceptor sees them. Their boundary value is valid numeric1. The original raw-byte refusal expectation was therefore wrong for this integration. **S1 is refuted as an application defect.** Root retained a defensive CR/LF check without claiming the application can reject bytes already removed upstream.

The final controls explicitly test bounded recovery after that normalization and refusal of values that remain malformed, such as raw interior linebreak plus a nonnumeric suffix normalizing to1x. `sanitizer-probe-values.json` and dependency hashes preserve the causal evidence. Initial2RED/98green, the attempted explicit-guard4RED/98green and the class-instance counterprobe2RED/2green remain retained as rejected raw-contract hypotheses, not unresolved product failures or green acceptance.

The first Docker launch failed before Jest because the immutable projection lacked an empty dependency mountpoint. The first100-case harness also had one fixture default-argument error and duplicate-root/formatter resolver noise; those were corrected only in external evidence files. All failed commands/results remain in run1/run2 artifacts. The final accepted result is solely `final-2.*`.

## Limits and cleanup

This review covers the frontend retry change, the actual JSDOM Overview/query/decoder flow and the listed adversarial boundaries. It does not certify browser layout, a real network transport, backend/JWKS/source-monitor fixes, production availability or any activation control. No checkout product/test files were edited, no shared container was changed, and no production/provider/paid service, upload, publishing or worker action occurred. Owned Docker containers were removed; `cleanup.json` records zero remaining owned containers.

`FINAL-RECEIPT.json` pins inputs, commands, raw results, failure history, runtime and cleanup. `SOURCE-AFTER.json` records zero source drift. Prior failed attempts and the initial classification remain intact for auditability.

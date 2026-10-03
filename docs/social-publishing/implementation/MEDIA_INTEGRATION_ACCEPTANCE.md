# Media integration and verification receipts

## Integrated behavior

The registered media API uses the existing Supabase administrator boundary. A composer can upload an original file, receive a ready asset only after server byte inspection, reuse a compact paged library and request a short private preview. Master and account overrides contain stable asset references and alt/caption metadata, never upload URLs or credentials. No publishing adapter or live storage configuration is enabled.

The integrator registers media models on the existing Base, refreshes the authoritative social table set once, and mounts the complete media route prefix alongside editorial and Meta routes. Status reports runtime media availability as a strict boolean while all four generation/automatic controls stay false. Pillow is directly declared using the existing tested installation; nothing was installed.

Migration `a42b86e1d310` follows Meta `c96d13e2f411`, leaving one Alembic head. Actual disposable PostgreSQL checks execute both additive migrations, inspect all sixteen social tables, RLS and PUBLIC/browser-role revocation, the asset foreign key, nonnegative budgets and history-refusing downgrade. Empty media downgrade retains the fourteen-table Meta/domain schema. A concurrent same-intent test reserves one asset and both temporary/original copies exactly once.

## Executed independent review

The following failures were reproduced before correction, rather than accepted from comments alone:

- Stale cleanup candidates could release one reservation twice. Candidates now recheck accounting/state under the global→actor→asset locks.
- A late worker finalize could create an untracked original after cleanup. Durable finalization epoch/settlement evidence now retains both-copy quota and pending capacity while outcome is unknown.
- A matching HEAD after a timed-out SDK PUT could conceal another outstanding wire attempt. The real installed botocore transport demonstrated that `max_attempts=1` permits two attempts; `total_max_attempts=1` allows one. Only confirmed single-attempt success or definitive zero-retry HTTP412 reaches actual byte verification. Ambiguous writes remain unresolved.
- Unknown finalizations or active cleanup leases consumed the candidate limit and delayed eligible work. Both are filtered before the limit and rechecked after locking.
- Corrupt/truncated final video or audio samples could follow a valid first frame. Full packet/frame accounting and bounded ffprobe decoding reject these specimens while positive H.264/AAC baselines pass.
- The integrated composer kept Publish Now enabled during inspection and attached an account upload to the account selected later. Both root regressions failed before wiring, then passed. Explicit post/account contexts, account remount boundaries, latest callbacks and a pending-operation command guard preserve newer text/overrides and prevent wrong-account attachment. Completed but detached uploads remain available in the library.
- Success and typed failures lacked a consistent HTTP trace event. The two telemetry regressions failed before the shared completion event, then passed. Logs contain request ID, static route template, validated UUID identities, duration, status and stable error code; query strings, bodies, filenames, grants and raw exceptions are excluded. Durable feature audit records remain authoritative.

An independent reviewer reran six hostile cleanup/transport cases against the integrated tree: **6 passed**. No real external storage or provider was used.

## Final verification

- Combined social backend: **534 passed**, including actual migrations, PostgreSQL locks/races, media byte inspectors, Meta fake HTTP and existing worker/domain boundaries.
- Final test-fixture portability update: **259 media tests passed**. PostgreSQL is opt-in through the existing explicitly assigned test DSN and rejects non-loopback/unassigned destinations before connecting; native video fixtures discover existing tools instead of assuming a Mac path. Missing native tools skip the native acceptance lane rather than install dependencies or fabricate evidence.
- Combined frontend: **373 passed across 20 suites**. TypeScript and scoped ESLint passed. The earlier permanently-unavailable bare media fixture now uses its actual query provider/runtime response.
- Single Alembic head and socket-denied full app route-registration smoke passed without entering application lifespan.
- Actual component markup rendered at 1440, 768, 390 and 320 pixels: no horizontal overflow, controls labelled, buttons at least44px and visible3px keyboard focus. External requests were blocked. Interactions run in Jest; these screenshots are not authenticated application or live CORS acceptance.

## Operational gates and remaining work

See #490 before enabling storage or invoking maintenance. The cleanup port is deliberately unwired. Private bucket/CORS/create-only/length behavior, restricted keys, installed native tools, request/resource limits, clocks, storage inventory and hosting costs still need authorized validation. Unknown finalization recovery requires explicit operator reconciliation; never clear its marker or reservation because a database lease expired. Ready-original automatic deletion remains deferred until domain saves and retention share reference/deletion locks.

Before activating quarantine cleanup, separate browser grant-renewal deadlines from orphan expiry and establish conservative handling of in-flight signed PUTs. A signed request can begin before expiry; an age timestamp or DELETE alone does not establish that all client writes stopped. This is a maintenance activation gate tracked in #490, not a claim validated against live R2 in this batch. Keep cleanup disabled until that contract is established.

These PRs add tested code, not production migration, deployment, account connection, publication, billing or environment changes. Hosted Actions remain disabled by the existing workflow; local results are not hosted CI.

# Shared authentication lifecycle repair

The retained test reproduces the SDK lock cycle with an inert, lock-faithful client: GoTrue waits for its subscriber while holding its auth lock; the asynchronous subscriber's profile transport waits for `getSession()` to acquire that same lock. Installed dependency source confirms the awaited subscriber and token acquisition edges. This executed reproduction establishes the mechanism; the coordinator separately observed the real production browser hard-navigation hang twice and reports it disappeared after this repair.

`frontend/lib/auth/AuthProvider.tsx` now returns synchronously from auth notifications and schedules profile work after the callback. Identity changes revoke the previous profile immediately. Generation guards protect initial restoration, event profile reads, login, registration, refresh, logout, and unmount from late writes. Lookup/auth errors settle loading and withhold stale profile evidence. Existing reset-password, password update, email change, account-delete, and citizen registration interfaces remain compatible.

The spec reviewer additionally found a same-identity registration refresh race. A fresh registration retry now owns a new profile generation within its original identity lifetime. Newer role observations and sign-out/reentry still defeat older reads.

Verification:

- Before the shared lifecycle repair: **10 failed / 2 passed**, including the explicit lock deadlock, stale initial restoration, and late privilege restoration (`session_lifecycle.observed_red.txt`).
- Before the additional registration repair: **1 failed / 22 passed** (`session_lifecycle.registration_red.txt`).
- Final retained lifecycle suite: **23 passed**; full users/auth scope: **127 passed in seven suites**. No React act warnings or console errors.
- TypeScript and scoped ESLint pass with the existing configuration. Timer cleanup uses `Set.forEach`, compatible with the repository's TypeScript target.
- Coordinator's final replay on this frozen auth hash passes Operations **6** and Users **4** production browser journeys. The final Overview/Audit **5** replay remains coordinator-owned and is running; its earlier replay passed all five.
- Coordinator reports the full frontend suite passes **1,932 tests**, with one unrelated skipped test; production builds targeting inert APIs on ports 8151/8152 and lint pass. The coordinator committed the users/auth/policy repair as `bca7633` and integrated current main locally.

Source SHA256: `a3bc744e0f7535e66386df585aa38602ff56ef5addea3444484f198d78f308a5`. Retained lifecycle test SHA256: `ef9934a01653ff3948fe3eb6516665d5c46cc525511d4ba98212f0d40484842e`.

No Git, external service, provider, live authentication, or deployment mutation was performed by this reviewer.

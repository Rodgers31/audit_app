# Independent Spec review — final candidate v2

2026-10-16. Checkout `/Users/roger/.codex/worktrees/b15-platforms/audit_app`, branch `codex/b15-platforms`, base/HEAD `06896185005d822c4b29888138b984510dd1fdbd` with uncommitted platform changes. Append-only review record. No product changes/commits/live provider calls/costs. Used code-review/adversarial-verify procedures, existing source blueprint and full COORDINATION.md already read in initial review.

## Observed-red final-delta finding

**P1 — server-ready TikTok OAuth config cannot launch frontend authorization.** Blueprint852–860 requires the complete authenticated flow;862 requires exact callback allowlisting. `TikTokOAuthConfig.__post_init__` accepts missing `redirect_uri` in the console authorization URL; `begin_url` does not insert it. `PlatformAccounts.start` requires URL `redirect_uri` equal to the configured callback. Accepted server configuration therefore advertises ready but fails before navigating to TikTok. Independent local-only provider configuration probe, using `test_platform_runtime.environment('tiktok')` and actual `TikTokConnectionProvider.authorize_url`:

```text
tiktok_ready_config [] ui_callback_expected https://admin.example.test/admin/social/accounts/callback/ returned None ui_launch_accepts False
```

Reproducer `final_spec_probe_v2.py` is adjacent. Root has confirmed and is implementing strict exact-console callback requirement, with no silent identity/scope construction. No code correction was made by reviewer. This finding remains open until rerun below.

### Source hashes for observed-red boundary
5fb75f4fe866d39ae6aa3ec2802cb68b67ed636641e173e158fbb00b56cb4bd0  backend/social/adapters/tiktok_oauth.py
015b32533924f0afde1568696857988f52fe7d05528796f240f5c615fc914da9  backend/social/platform_runtime.py
ac065e26665f2e5f5ae804377e092150982b169392512f68946ad12112780a36  frontend/components/admin/social/connections/PlatformAccounts.tsx
de8a7d97013aecdaaa696976ffb96b6ed8734bc9180fec64e7ca1c43693c06f2  /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/reviews/final_spec_probe_v2.py

## Additional observed-red final-delta rate finding

**P1 — TikTok discards valid long/date Retry-After then allows early retry.** Blueprint1698 requires “Honor provider reset/Retry-After; no early retry”;19.2 says provider delay wins and is never capped downward. `tiktok_http.py` recognizes only1–6 digit Retry-After and `tiktok.py:_failure` grants `retry_safe=True` for RATE_LIMITED even without parsed timing. Executed direct publication adapter with local429 sanitized fixtures (before root correction):

```text
tiktok_retry_after Sat, 17 Oct 2026 02:00:00 GMT definite_failure RATE_LIMITED None True
tiktok_retry_after 1000000 definite_failure RATE_LIMITED None True
```

The date is NOW+6hours;1,000,000seconds is a valid long delta. Discarding either permits worker jitter to retry earlier. Reproducer `final_tiktok_rate_probe_v2.py` adjacent. No real network or costs.

### Source hashes for observed-red TikTok rate boundary
c37baea22776c0270b32879fb36ce739ee8b0487d70511e3f88ccfc82c8e6e36  backend/social/adapters/tiktok_http.py
1e06fec2dd0f4edcc677e0c5a42f38903771721fcc3baf0ac71f46dd44de3057  backend/social/adapters/tiktok.py
5382003c6b541d651e126656e49ddf5cf8e4457fb66fa995656cf4f46ad6342d  /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/reviews/final_tiktok_rate_probe_v2.py

### Same provider-delay defect on Threads

`threads.py` newly imports the inherited `meta_http._retry_time`; that helper clamps dates/deltas to86400 and ignores integer deltas longer than6digits. Executed direct quota read with sanitized429 errorcode4:

```text
threads_retry_after Wed, 21 Oct 2026 12:00:00 GMT definite_failure RATE_LIMITED 2026-10-17 12:00:00+00:00 True
threads_retry_after 1000000 definite_failure RATE_LIMITED None True
```

The first date is NOW+5days but result is only+1day; the second permits routine retry without required timing. Same blueprint1698/19.2 requirement. Probe is adjacent `final_threads_rate_probe_v2.py`. Root notified; no product edits by reviewer.

### Source hashes for observed-red Threads rate boundary
7a4cfe9566d2453d5869cb430f53f6de23f43b8bdea1d18d0eb98ec800d7ea65  backend/social/adapters/threads.py
bd54476f7c46b02ee48c1942522a9fd89504eda511437df2e8ba95ae79ae88f0  backend/social/adapters/meta_http.py
4b3edec1d5569b0f0cc78d995b5ecad645255e3f17a2aca5f07d98aa72b0f2e2  /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/reviews/final_threads_rate_probe_v2.py

### TikTok status handling also drops parsed delay

Even a currently recognized86400delta is swallowed by `_status`, which converts rate errors into a generic180second processing result. Direct submitted-task status probe (same sanitized429 fixture):

```text
tiktok_status_retry_after86400 processing PUBLICATION_LOOKUP_UNAVAILABLE 2026-10-16 20:03:00+00:00 required 2026-10-17 20:00:00+00:00
```

`reconcile` also derives its next-check timing from this status result. Provider delay must survive all status/recovery paths, not only parse correctly at transport. Probe adjacent `final_tiktok_status_rate_probe_v2.py`; parent notified.
1e06fec2dd0f4edcc677e0c5a42f38903771721fcc3baf0ac71f46dd44de3057  backend/social/adapters/tiktok.py
92d4b473688c00530d6ea640f1dc056fa9a2f94c2fb2adbcbc95a0a3ab6cd30b  /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/reviews/final_tiktok_status_rate_probe_v2.py

### Provider event consumer shortens retained rate hold

Final full-chain seam for same blueprint1698 requirement: persisted processing/poll target has `error_code=RATE_LIMITED`, `next_action_at=NOW+6hours`; a matching signed Threads event accepted into the durable inbox causes `process_pending_events` to set next_action_at=NOW. Event hints do not waive provider API quota. Executed localSQLite probe:

```text
rate_limited_event_nudge RATE_LIMITED 2026-10-16 12:00:00+00:00 required 2026-10-16 18:00:00+00:00
```

Probe adjacent `final_event_rate_probe_v2.py`. Root notified. A retained provider not-before must survive event nudges as well as status/reconciliation returns.
3dc210ed5f93ddd6ab38bda23e83138854d7d0255b752fb9d8762a0583b641d1  backend/social/platform_events.py
96ada7b1ffade8cf030d8c7cc26bd18b6a5d4eef5c6b0346d154ff2699b49b96  /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/platforms-evidence/reviews/final_event_rate_probe_v2.py

## Backend final corrections reverified

All initial findings and final-delta OAuth/provider-timing findings are corrected on the backend source hashes recorded below. No remaining backend Spec finding was identified in the reviewed lane changes. This is a tested-code conclusion, not external/live acceptance.

- `PYTHONPATH=backend <python> -m pytest --confcutdir=backend/tests/social` with `test_threads_adapter.py test_x_adapter.py test_tiktok_adapter.py test_platform_connections.py test_platform_events.py test_platform_boundary_regressions.py test_platform_runtime.py test_platform_worker_role_contract.py`: **440passed,0failed,0skipped**,1.84seconds; two existing SQLAlchemy deprecation warnings.
- Same exact command under `python -O`: **440passed,0failed,0skipped**,1.96seconds; expected pytest warning that non-rewritten helper assertions are disabled plus the two deprecation warnings. Guard code was executed in both interpreter modes; this does not imply all helper assertions remain active under optimization.
- Assigned local55398 fixture only, `B15_PLATFORMS_TEST_DATABASE_URL=<explicit local fixture> PYTHONPATH=backend <python> -m pytest --confcutdir=backend/tests/social test_platforms_postgres.py test_platform_worker_role_postgres.py`: **42passed,0failed,0skipped**,10.75seconds; two existing SQLAlchemy deprecation warnings. Includes full empty-database Alembic chain, role isolation, target-only retries, combined quotas, workflow scheduling guards, exact paid reservation and recovery paths. Each test owned and cleaned a uniquely named schema/database; the shared container was not stopped or changed.
- Earlier frontend command `frontend/node_modules/.bin/jest --runInBand __tests__/admin/social/platform-controls.test.tsx __tests__/admin/social/platform-counters.test.ts __tests__/social-connections/platform-callback-route.test.ts`: **3suites/57tests passed**,0.447seconds. A final consent-reset UI delta was still being completed; its final rereview follows below.
- `git diff --check`:exit0.

### Independent exact probe results after corrections

The unchanged external review probes were rerun, not replaced with assertion-only source checks:

```text
x_absent_access_expiry definite_failure TOKEN_EXPIRED []
tiktok_default_off_reconcile unknown None []
threads_expired_data_access definite_failure TOKEN_EXPIRED []
x_budget_hostile_cost_successes []
x_budget_hostile_state_successes []
configured_platform_startup_registry None
configured_platform_connections_available True
```

The startup probe's empty environment deliberately keeps adapters off; the connection state is now installed. Actual accepted platform-only/mixed startup/closure is additionally executed by `test_platform_runtime.py`, with injected transport/storage ports.

```text
x_retry_after_only definite_failure RATE_LIMITED 2026-10-17 12:00:00+00:00 True
x_conflicting_rate_headers definite_failure RATE_LIMITED 2026-10-17 12:00:00+00:00 True
tiktok_ready_config [] ui_callback_expected https://admin.example.test/admin/social/accounts/callback/ returned https://admin.example.test/admin/social/accounts/callback/ ui_launch_accepts True
x_crash_first_recovery reconciling reconcile 1
x_crash_final published public 777 1 reserved 85000
x_crash_provider_calls [('POST', '/2/tweets'), ('GET', '/2/users/901/tweets')]
tiktok_retry_after Sat, 17 Oct 2026 02:00:00 GMT definite_failure RATE_LIMITED 2026-10-17 02:00:00+00:00 True
tiktok_retry_after 1000000 definite_failure RATE_LIMITED 2026-10-28 09:46:40+00:00 True
threads_retry_after Wed, 21 Oct 2026 12:00:00 GMT definite_failure RATE_LIMITED 2026-10-21 12:00:00+00:00 True
threads_retry_after 1000000 definite_failure RATE_LIMITED 2026-10-28 01:46:40+00:00 True
tiktok_status_retry_after86400 processing RATE_LIMITED 2026-10-17 20:00:00+00:00 required 2026-10-17 20:00:00+00:00
rate_limited_event_nudge RATE_LIMITED 2026-10-16 18:00:00+00:00 required 2026-10-16 18:00:00+00:00
```

The independent PostgreSQL X probe creates an accepted-publication crash by dropping durable response persistence, expires only the fixture leases, invokes actual lease recovery, verifies bounded wait with no timeline request before window closure, advances only fixture dispatch time to avoid sleeping, then binds the strong provider match to original fingerprint/dispatch. Budget retains15000original+35000wait reservation+35000lookup=85000; only one publication POST occurs. Its isolated schema is cleaned in `finally`.

### Backend source SHA256 at final replay
a226667358b0c0d813f56f327e02fcf714c21a0970ef8137932abfe2ad438af8  backend/social/adapters/threads.py
4750d3a89ce110974e1299e3d2c015cfe7586a578887a90069a159e96f2db663  backend/social/adapters/x.py
573f68476f121713c4358a1fd17f997e70f506f3ab40a49913688ef50ad793fa  backend/social/adapters/tiktok.py
78464ac3d698b8c2fefccb72ef6c66a50f1e2e1e74414c04cd0388be0c558cde  backend/social/adapters/tiktok_http.py
639bd69d8ff12798e146176c3d8580812d2d3556583eff21e3269b5e93dda918  backend/social/adapters/tiktok_oauth.py
5eabdde6aaf5bd1bb38e71d6d496865248152660dea58eeec9271b62db0726f8  backend/social/adapters/platform_http.py
015b32533924f0afde1568696857988f52fe7d05528796f240f5c615fc914da9  backend/social/platform_runtime.py
0f47cf9f075fd1313923b7a149c8026893f34baaae253da3f15754fccf94203f  backend/social/platform_events.py
e265413d2b375892cf871f40120bed6163e49d6eaeef8558b61229692b7ad52d  backend/social/platform_event_models.py
a96a3f670a3da767a379c0cecf68b230ab8f76d4c3ee7085ea586bb0f7736e27  backend/social/platform_materials.py
ff485637d6f8e461ad7ff524e6c59b205f6e3eb9fdeaa9ad25fd2d9b57be38b5  backend/social/platform_budget.py
f085f4bccbb2afa731423aa94fab2f6e9bb0a39f31e99a5b854ca86c60e8c511  backend/social/platform_connections/config.py
8df8b959ad2a4f70f470ca445a6f24cadef27041ea0be4f1a8f5e828f95322df  backend/social/platform_connections/service.py
dd41be0883913655fb2db5671cc4474e54f2e093d6f8886a1ad61bf6caec2ccc  backend/social/platform_connections/provider.py
ba3d5adf350891c269b69360b39388d334ea6bdc9f0236e5100b3be8bab43346  backend/social/worker/startup.py
f3705560a9d5af3a5e0413ee717832d80674556519487a581daeb6a7c1469c94  backend/social/worker/native_runtime.py
764ad3b9e4384affc158621c07ce7cf1b1fe01467154bb539a50f9d8491106bb  backend/social/worker/repository.py
3e1f8f4acc9fd4d9a1f8f3267ec1760b41af993c91202a52bc81e9c2dcd14fcc  backend/social/worker/runner.py
b1f9d4782fd72745740327085c371cb21a709e8f513e9446461c95505c7fe86d  backend/social/worker/role_contract.py
b1b5928d7e558882e3c43dd4f61121d2766362e954e7bf76dc455a3c4fd0ba42  backend/social/service.py
f843891f19245225119ad619883b452c5f2f454d7b21da7090f4455face993e6  backend/social/validation.py
cf407928eda4f08a115b2ee99d78f93d94b371debaafd6be999b54fdddf76876  backend/social/contracts.py
31bb7c252029cad2d84dc6194a72205a6c43d8adf2b7d3ed3006ec2751a3b958  backend/alembic/versions/a703b15a0001_platform_connections.py

## Final frontend consent delta and Spec verdict

Read actual `tiktokConsent.ts` and functional composer edit path. Canonical account/format/resolved text/link/ordered hashtags/ordered media/accessibility fields and all non-confirmation TikTok choices bind the consent. Effective content changes clear upload, music and branded-policy confirmations; changing internal draft metadata or checking another confirmation preserves reviewed consent. A per-account override whose effective content stays identical preserves only that target's consent. The original objects are not mutated.

Executed from `frontend`:

```text
./node_modules/.bin/jest --runInBand
  __tests__/admin/social/tiktok-consent-binding.test.tsx
  __tests__/admin/social/composer.test.tsx
  __tests__/admin/social/composer-media-integration.test.tsx
  __tests__/admin/social/platform-controls.test.tsx
  __tests__/admin/social/platform-counters.test.ts
  __tests__/social-connections/platform-callback-route.test.ts
```

**6suites,100tests passed;0failed,0skipped;1.514seconds.** `git diff --check`:exit0. No browser/provider session or live UI publication was used. No remaining actionable Spec finding in reviewed source delta.

### Final frontend source SHA256
36766799897de9b86d08867185bfb6c85a8a7dbfce59933e46a1e96f68a20480  frontend/components/admin/social/tiktokConsent.ts
7448563767b2dbdeb1664d9cae5b6e50116da17bb02d597519a03cd620154947  frontend/components/admin/social/SocialComposer.tsx
31b3650deb34c9cc507b58ae69f1760654a84bf482dcef994cf02d7b3e3213c8  frontend/components/admin/social/TikTokControls.tsx
b0909f9f75f8020687e49102834fa5c15e302854e5af84f94db35e30185ac5d1  frontend/components/admin/social/SocialPreview.tsx
ac065e26665f2e5f5ae804377e092150982b169392512f68946ad12112780a36  frontend/components/admin/social/connections/PlatformAccounts.tsx
1f0164d1ca70c41b1ca84b0b78a3d6f40b00014717e430a1382716939c928887  frontend/lib/api/socialPlatformConnections.ts
d8bd7964d99c8bfebe1871db540b75e67c8a4e8e44201ce56c879a1c207d7467  frontend/lib/socialPlatformCounters.ts
06648a7f763896cbb1b8aa4fe48e5f90004b250d6a0b7cd426f27d8559407032  frontend/__tests__/admin/social/tiktok-consent-binding.test.tsx

### Tested implementation versus unresolved external/integration gates

- **CODE IMPLEMENTED / TESTED:** reachable default-off environment/API/native worker composition; official product OAuth and rotated/encrypted credentials; exact callback/actor/session/state/PKCE binding; platform preview/counters and explicit TikTok controls; durable scoped material/intent/receipt/fencing integration; Threads quota/container/poll/readback and signed event hints; X operation-bound conservative paid reservation/media/checkpoint/exact/bounded lookup recovery; TikTok approved access/origin/direct/draft/status and separate future-delivery workflow gates; event inbox/retention and target-only wakeup/retry behavior. Tests establish sanitized contract behavior and local PostgreSQL chain only.
- **THREADS PUBLIC VISIBILITY:** official authenticated own-post retrieval does not establish anonymous/public availability. This implementation deliberately retains Processing/unknown, never synthesizes public proof from permalink. A source-supported provider proof or audited manual reconciliation remains an explicit acceptance limitation; phase6 must not be called live-complete from these fixtures.
- **EXTERNALLY BLOCKED / UNEXERCISED:** genuine Threads/X/TikTok app/product/scopes/terms/access; approved X budgets and current billing ceilings; TikTok accepted unattended workflow and verified owned media origins; subscriptions and live provider interoperability/acceptance; stable key custody/recovery inventory; production grants and migration/integration sequencing. No real grants, keys, posts, uploads, credentials or paid access were exercised.
- **COORDINATOR INTEGRATION:** issue700 worker-only media-read composition with uploads OFF remains worker/media/coordinator dependency. Local injected enabled media fixtures do not establish this live boundary. Candidate migration predecessor still must be serialized/replayed with other lanes before integration. No production deployment/merge/grant changes were attempted.
- Reviewer resource cleanup: no persistent processes/containers/tabs created; only uniquely owned temporary PostgreSQL schemas/databases through lane fixture lifecycle, all cleaned; existing shared55398container retained. Product checkout was not edited by reviewer; evidence/probe files are external and append-only report retains initial failures.

## Post-review material-limit correction addendum

Root's broader replay exposed an existing image-limit regression after the video ceiling expansion. Root retained its source-bound red receipt `final-20261016T201649Z-fd35b55f`; this reviewer did not independently recreate the prior source. Reviewed the frozen correction at `worker/materials.py:_read`: reject non-`InspectedAsset` before field access; select100,000,000byte request ceiling for `video/mp4` and8,000,000for other assets; retain exact integer/no-bool input and selected-asset-size checks. Later immutable-storage/checksum/authorization verification remains in place. This restores the existing image constraint while preserving bounded video support. No new actionable finding.

Independently executed:

- `PYTHONPATH=backend /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest --confcutdir=backend/tests/social backend/tests/social/test_worker_materials.py backend/tests/social/test_worker_materials_adversary.py -q`: **79passed,0failed,0skipped**,1.54seconds; one existing SQLAlchemy warning.
- Identical command with `python -O`: **79passed,0failed,0skipped**,1.52seconds; expected pytest optimization warning plus existing SQLAlchemy warning.
- Direct `_read` guard probe on an uninitialized `VerifiedMediaAccess`, with `_snapshot` replaced only by a sentinel exception to prove which inputs reach the next verification stage:

```text
untyped MEDIA_OUTSIDE_AUTHORIZATION
image_8M_plus1 MEDIA_BYTE_LIMIT
image_8M VALIDATION_CONTINUES_TO_SNAPSHOT
video_100M VALIDATION_CONTINUES_TO_SNAPSHOT
video_100M_plus1 MEDIA_BYTE_LIMIT
```

The sentinel continuation is a guard-boundary result, not successful media transfer. No storage/provider I/O, PostgreSQL or resources were needed. `git diff --check`:exit0. Product checkout unchanged by reviewer. Root reports broader corrected801passed/14legacyPGskips in normal and optimized Python and617Jest; those broader totals are root evidence, not independently rerun by this addendum.

### Corrected material source/test SHA256

```text
418d263f3cb810a6f654d9ce32254a4578972b3dba5d24a54fa4fdbc8f380bf3  backend/social/worker/materials.py
f0283270a4792e3116575084709d3e3c2564de1f8fe385b093045feb0ad9053d  backend/tests/social/test_worker_materials.py
4e8adfc28de7b4075b248d62dceb3715fa99ac6eca6b884f64ce620db3daeeed  backend/tests/social/test_worker_materials_adversary.py
```

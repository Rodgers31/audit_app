# Overview 503 recovery and source warnings — 2026-10-31

The candidate fixes recovery from temporary cold authentication/admission
refusals and removes CoB's unnecessary homepage redirect. KNBS and Treasury
still fail certificate verification; their warnings now explain the publisher
repair required. This candidate is reviewed locally and **not deployed**.
Production remains at `12b79d361eea0cfb7113d51155bf7a2489a1d076`.

## Changes and boundaries

The Overview's seven concurrent reads can encounter the existing one-fetch
JWKS admission guard. Cold followers previously received a bare 503 and the
shared client did not retry it. The backend now supplies short retry advice for
an in-flight fetch and truthful remaining advice for a failed-fetch cooldown.
Existing CORS exposes Retry-After. The shared client honors only short numeric
advice for safe reads, preserving its two-retry ceiling, 1.5/3-second minimum
backoff, cancellation and authentication. Ordinary 503 errors remain visible.

No database limit, middleware admission limit, authentication/signature/role
rule, source TLS policy, scheduler or operational activation changes.
GET/HEAD are the only replayed methods. The client still refuses dates,
over-budget values, malformed values and ambiguous direct raw-header aliases.
The locked Axios transport's own header normalization remains explicit in tests.

Source diagnostics are additive: v2 `failure_reason` and fixed alert messages;
legacy consumers retain their existing row structure and get the same safe
messages. Missing/stale evidence remains unknown. A later verified observation
clears prior failure reasons. No private exception text is returned.

See [decision 0004](../adr/0004-bounded-overview-recovery.md).

## The three upstream warnings

| Publisher | Executed observation | Disposition |
|---|---|---|
| CoB | www redirects to the canonical bare host. The production-network installed monitor timed out; candidate bytes observed HTTP 200 at the direct host under unchanged limits. | Change only the configured homepage to `https://cob.go.ke`. This is a point-in-time success, not an uptime promise. |
| KNBS | Production network fails certificate verification with code 20. Independent strict OpenSSL inspection sees only the valid leaf, issued by Let's Encrypt YE2, with no served intermediate. Both www and bare hosts fail. | Preserve the warning, classify `certificate_chain_unverified`. Publisher must serve its complete trusted chain. No hostname substitution or verification bypass. |
| Treasury | Production network fails with verification code 10. The served leaf expired at **2026-10-31 11:16:02 UTC**. Both hostname variants fail. | Preserve the warning, classify `certificate_expired`. Publisher must renew and deploy the certificate. |

The installed-vs-candidate experiment executed the exact source module bytes
in a separate read-only diagnostic process on the existing Render service.
It did not install the candidate, change the serving process, access business
data or generate drafts. Candidate module hash is pinned in
`production-source-comparison.json`. CBK and OAG remained verified HTTP 200;
KNBS/Treasury stayed failed. Official homepage reachability is separate from
document ingestion and source acceptance. No publisher contact was sent.

## Validation

| Scope | Final executed result |
|---|---|
| Root affected backend selection | 140 passed normally and 140 under actual Python `-O`; zero failures, errors or skips |
| Independent backend Standards review | 31 independent controls per mode; separate 140-case corroboration per mode; no unresolved scoped finding |
| Root full frontend | 215 suites, **2,898 tests passed**, zero failures/skips |
| Optional PostgreSQL HTTP capture prerequisite | Three real PostgreSQL/HTTP parameter cases passed, 38 intentionally deselected; no skip. Synthetic persisted fixtures, not official amounts. |
| Independent frontend Spec review | Final bridge: 60 independent controls plus 48 repository controls; separate eight direct raw-boundary controls. All pass, focused strict TypeScript passes. |
| TypeScript and changed-file lint | Full `tsc --noEmit --incremental false` clean; ESLint zero warnings/errors |
| Actual production build and mandatory shell browser gate | `npm run test:admin-shell` built the real app, then 12/12 browser cases passed at 1728/768/375/320px with real root layout, middleware and CSS |

Repeated executions and overlapping author/independent controls are not added
as unique coverage. Backend runs use cached Python 3.12.15 / OpenSSL 3.5.7.
Frontend uses Node 24.22.1 and locked Axios 1.20.0. Network-isolated containers
and inert credentials were used for tests; the shell build used an owned local
copy and cloned cached native dependencies. A local runner added Git from
Debian's official package repository. No application dependency install, hosted
CI rerun, paid review, model, new service, plan, quota or server-size increase.

The old default frontend skip was the captured PostgreSQL HTTP absence reader.
Its three captures were produced by the actual PostgreSQL HTTP fixture; the
final full frontend run consumed them and has zero skipped tests. The owned
database container and its fixtures were removed afterward. Shared containers
and the dirty primary checkout were preserved.

## Review dispositions and retained non-green evidence

- **Valid P3, fixed:** a failed JWKS fetch consuming 4.25 seconds advertised a
  fresh 30-second wait to its leader while followers correctly advertised 26.
  Root reproduced the mismatch; the permanent regression and unchanged
  independent control pass after calculating remaining cooldown under the lock.
- **Valid defensive S2, fixed:** the TypeScript-compatible raw-object fallback
  initially accepted the first of conflicting Retry-After aliases. Root's
  direct registered-interceptor fixture failed in two of three order/value
  cases before the fix and all pass afterward. Require exactly one matching
  key. This is the direct fallback boundary; normal Axios transports normalize
  headers before this hook and no ordinary transport exploit was demonstrated.
- **Refuted S1:** initial raw LF/CRLF refusal expectations ignored locked Axios
  sanitization to valid numeric `1` before the hook. Executed counterprobes
  retain that causal evidence. Those REDs are rejected test hypotheses, not
  unresolved product defects or credited fixed defects.
- Root pre-fix fixtures also executed RED for safe-read recovery, cancellation,
  missing auth advice/CORS exposure, source diagnostic classification and CoB's
  extra redirect. A nested string-only certificate wrapper regression executed
  RED while implementing the classifier, then passed after preserving fallback.
- Earlier combined backend collection failed on an absolute sibling-test
  import. It now uses the package-relative import; final selection needs no
  tests-directory PYTHONPATH override. An initial CORS fixture referenced the
  wrong settings object; corrected actual-middleware REDs are separate.
- Initial full frontend runner lacked Git needed by the existing frozen-paint
  test. A local Git-enabled runner passed that control with actual read-only
  repository metadata. The first PostgreSQL capture mount lacked sibling ETL;
  the corrected full-source mount passed. Initial full TypeScript found a raw
  header union mismatch, now fixed. The shell gate initially refused the wrong
  working directory and then symlinked dependencies; the final owned dependency
  copy passed the unmodified gate. These are retained setup/type failures,
  not silently omitted or represented as green application results.

## Operational readback and rollout

At **2026-10-31 16:26 UTC**, read-only production SQL with verify-full TLS and
bounded statement/lock timeouts showed publishing/auto-approval/scheduling/
publishing controls false at version 1. Facebook and Instagram publishing
remain false. Media is false; native/financial generation, hooks, policy,
studio and supervisor flags remain unset/default-off. Autoseeder and admin
dispatch are false. No worker/consumer/supervisor process was running.
The retained worker heartbeat is stopped. Five posts, zero publications,
targets, assets, uploads or publishing attempts; unchanged from the baseline.
No flag or business data was changed during this work.

Production remains on the base SHA. No merge/deploy override is inherited from
earlier PRs. Automatic Copilot review, new-push review and draft review were
read back off; repository rules add no Copilot auto-review. The normal CI and
deployment workflows remain disabled. The PR is held as a finished draft to
avoid automatic paid review. No review requests or workflow dispatches are
part of this change.

The existing Vercel project already has preview deployments disabled. A scoped
read-only CLI/API check confirmed that setting and the unchanged production
deployment `dpl_7FSLXMFFtcQ89hxg2x86mgzst7V7`; no build-policy setting was changed
to push this branch. The Ignored Build Step remains its original empty value.

After an authorized deployment, verify a fresh authenticated Overview and its
seven reads recover from a cold cache, while an actual provider outage stays
unavailable. Recheck source observations: CoB should use the direct host;
KNBS/Treasury must continue warning until verified publisher repairs succeed.
Publishing, uploads, workers and financial generation must remain off. No
migration, backfill, source admission or generation activation is required.

Evidence is under [overview-source-health-20261031](overview-source-health-20261031/).
`SHA256SUMS` covers the retained packet; `candidate-final-source-sha256.json`
pins executable changes. Independent source projections are represented by
their complete manifests and the base/candidate Git contents; bulk temporary
copies are not duplicated here. Historical commands and scripts retain their
original absolute cached-runtime paths and are evidence, not a new portable
release tool. Permanent regressions are the normal runnable repository tests.

The [PR #863 review addendum](overview-source-health-20261031/review-20261031/REVIEW.md)
classifies the body-only optimized-assertion findings using executed negative
controls and retains live verification as a rollout requirement. This review
round preserves all original executable source pins and sealed evidence.

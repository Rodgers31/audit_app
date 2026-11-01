# Final dependency and application-boundary audit — 1 November 2026

The security review for PR866 and the weekly-update policy in PR867 is complete
for the scopes below. The candidate includes the current production source from
PR869. It introduces no migration, production permission, worker, publication,
media upload, financial generator, paid review or hosted test run.

This supersedes the limited review status in
[DEPENDENCY_REVIEW_2026_11_01.md](DEPENDENCY_REVIEW_2026_11_01.md). Earlier reports
remain historical evidence. Current code was tested at `dfc0ea9e3a448ce5e281e15693c56477b280c1a8`;
subsequent final-report edits change documentation only. The
[verification packet](dependencies/2026-11-01/final/verification.json) records
executable source trees, exact environments and current limits. Deployment
acceptance is a separate readback after the authorized merge.

## Advisory results and repairs

| Actual resolved scope | Result |
| --- | --- |
| Production npm graph | Zero reported vulnerabilities; raw audit exit0 |
| Full npm graph | Five low entries, zero moderate/high/critical; raw audit exit1 retained |
| Python runtime / development / ETL / worker fixture | Fresh installs of 87 / 129 / 52 / 93 distributions; all pass pip check |
| Native Python development validation | 128 installed distributions; pip check passes |
| Python plus all three preflight driver profiles |158 distinct exact versions queried; zero returned advisory IDs |

The five npm entries are one low advisory in deepmerge 4.3.1 propagated through
Jest's development tooling. The [GitHub advisory](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
currently lists no patched release. Its installed CJS, UMD and source bytes are
repaired by the existing application-owned, hash-bound installer. Independent
execution reproduces the defect on pristine upstream bytes and proves the
repaired behavior in Node and browser-shaped execution. All 1,161 inventory file
hashes match. The registry version and advisory are not hidden or relabelled;
production pruning removes this development graph. A future upstream/package
layout change must pass manual repair review, rather than bypass its hash gate.

The final OSV checker counts **every raw advisory ID** as a release finding;
withdrawn or malformed advisory metadata cannot erase a match. All 158 candidate
versions completed across four batches, with exact cardinalities and no pending
pagination. The separate old-pypdf positive control returned all seven known
advisories. Its62 independent cases per Python mode cover missing batches,
malformed responses, incomplete/cyclic pages, invalid versions and driver pins,
partial positive controls, transport failures and findings in the final batch.
Initial verifier false greens are corrected; the final raw requests/responses
and source-bound checker are retained in the packet. No advisory exclusion is used.

An offline manifest smoke layer also passes for the ten active manifest inputs.
An initial recursive scan treated installed vendors' development declarations
and archived inputs as resolved dependencies, producing old lodash/express
flags. The origin classification is retained; the current complete npm graph
and exact installed Python graphs are the authoritative resolution evidence.
The offline tool's small historical pattern set is not current CVE coverage.

## Executed compatibility and security coverage

- Clean npm ci with peer checks and all seven source repairs; complete npm ls
  reports no graph problems. TypeScript and lint pass for 361 current lint files.
- All 215 Jest suites pass: 2,904 cases in the full run. Its one optional integration
  case subsequently passes with three newly captured PostgreSQL HTTP responses,
  giving 2,905 distinct covered cases. The supplied responses are synthetic
  source-shaped controls served by the real current HTTP/PostgreSQL readers,
  not invented JSON or production data.
- 217 dependency controls and nine runtime/isolation controls pass. Native model
  CPU inference, real image decode and installer ZIP extraction execute.
- 14 Chromium admin-shell cases pass at desktop/mobile sizes, including covered
  header refusal, reachable controls and signed-out/editor access refusal.
- 551 distinct affected Python cases pass in normal and actual optimized modes,
  with zero final failures/errors/skips. Native 533 and Linux 339 selections
  overlap; they are not added together as unique coverage. Actual PostgreSQL
  security cases and the nine previously skipped video cases execute. The
  worker fixture's separate 34 unit controls also pass per mode.
- Independent backend review passes 259 cases per mode (222 behavioral cases
  and 37 source-reference checks), plus one sandbox isolation case, with
  54 PostgreSQL cases and zero final skips.
  It independently reproduces 11 of the14 public-disclosure regressions on the
  old main module; the current 14 pass. File paths, arbitrary exception text and
  the private ETL job map stay out of public responses while operator logs and
  authorized diagnostics retain their purpose.
- Four CPython 3.12/3.13 x86 Linux driver wheels match their reviewed hashes and
  current official PyPI bytes. These foreign-ABI wheels were not executed on
  the arm64 test host. Native psycopg2 executed real local PostgreSQL cases.

Fresh Linux 3.12.16 environments and native macOS 3.13.9 tests are distinguished.
The macOS ffmpeg 9.0.1 media proof is not a Linux worker-host media qualification.
The ETL test harness adds four pytest-tool distributions already covered by
the development advisory queries. The dependency tests do not grant a worker
launch, full host capacity or confinement
sign-off. Cached test images are not claimed to equal every deployed OS package.
Any different resolved deployment graph requires an explicit comparison and
additional affected validation before acceptance.

## Source-fetching boundary remains explicit

No confirmed anonymous URL-control or authorization-bypass path was found in
this review. Public docs/resolve looks up the stored manifest; admin source
inputs select whitelisted keys. The deployed web image cannot import the legacy
etl.kenya_pipeline module, so that admin discovery path refuses before execution.
The actual operator settings select official HTTPS COB/Treasury hosts without
userinfo. These observations narrow reachability; they do not establish a full
ingestion egress guarantee.

The native ingestion path still trusts links/redirect destinations derived from
the configured publisher's HTML/JSON. Controlled local transport tests confirm
that this boundary needs hardening if those upstream responses become hostile.
Ordinary GitHub nightly ingestion remains enabled. Financial generation and
source admission being OFF do **not** prevent its fetches or ordinary source
writes. There is no newly approved security exception or blanket SSRF clearance.

Keep this existing ingestion trust assumption and hardening boundary in the
#802/launch review: require HTTPS, approved publisher/alias hosts, no userinfo and
approved ports before listing requests, selected-URL HEAD/GET and **each** redirect
hop. Preserve supported WPDM queries and relative links; review legitimate CDN
exceptions explicitly. That smaller policy differs from a full public-address
and peer-pinning guarantee, which needs separate transport qualification. This
PR does not silently change report selection, parser financial results or source
availability to claim that broader policy has already been implemented.

## Weekly updater and release controls

PR867 covers frontend npm, backend runtime/dev/constraints, ETL, the restricted
worker fixture and all three actual driver manifests. Monday checks are
staggered 08:00–09:00 America/Chicago. Version PR caps are 4/3/2/2/1, routine compatible
updates are grouped, and majors remain separately reviewable. There is no
custom updater workflow, auto-merge, automatic deployment or new secret.
Dependabot's standard GitHub-hosted update jobs do not consume included Actions
minutes; larger paid runners are not configured. See
[GitHub's runner documentation](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-on-actions).
Manual review and validation remain required for every proposed update.

The existing automatic Copilot review, review-on-push and review-draft controls
were read as OFF. Ordinary disabled CI/deployment workflows remain disabled;
branch protections remain unchanged. The existing production project settings
are retained. The local Linux x86 production artifact uses Node 24.22.1 and only
public production build values; auth/OIDC/revalidation secrets are excluded from
the builder and are absent from the output. Its 842 tracked frontend inputs match
exactly; 104 Node functions and one edge function resolve to seven owned bundles.
No upload or deployment is claimed by this pre-merge packet.

Publishing, media uploads, workers, financial generation and native financial
source admission remain OFF through deployment. The release must finish with
main, the actual backend revision and the approved ingestion pin aligned,
unchanged business/social state and an explicit rollback target. Source
acceptance for #802, full platform/worker launch gates and #494 remain separate;
none is automatically closed by this audit or by a successful dependency build.

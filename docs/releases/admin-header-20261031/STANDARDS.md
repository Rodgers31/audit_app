# Independent Standards review — admin header ownership

Assessment: PASS for the bounded source and browser scope below. No remaining actionable product finding was found in that executed scope. This is not approval to merge through a repository gate or a certification of the full application.

The reviewed candidate is the isolated `codex/admin-header-ownership` checkout based on `33999e215fe7a1a776685615c832dad4793acd19`. Source digests and local production BUILD_ID are retained in `reviewed-candidate.json`. The executed application is the actual Next 15.5.28 production build on loopback 3137, with the real RootLayout, Navigation, middleware and AuthProvider, rather than the earlier replacement-layout preview. Runtime: official Node 24.22.1 and Chromium via the locked Playwright 1.58.2 package.

## Executed browser scope

`browser-controls.cjs` / `browser-controls.log` / `results.json`: all eight independent scenario groups pass.

- Actual authenticated overview and header hit targets at 320, 375, 600, 601, 768, 1024, 1280 and 1728 CSS pixels; exactly seven real admin route links; no document overflow.
- Correct single current destination and one private navigation on `/status`, `/admin/social`, `/admin/social/new`, `/admin/users`, `/admin/ingestion`, `/admin/etl` and `/admin/audit-log`. Expected route headings are asserted, including explicit error-state System Status wording.
- Mobile Menu keyboard Enter, route selection closing the menu, and browser Back restoring a reachable menu.
- Theme switching, private-route persistence and a full reload.
- Public header retained on `/administrator`, `/adminish`, `/statusboard` and `/about`.
- Actual client navigation from the admin public-site link, opening the public mobile overlay, browser Back into admin and Forward to public; no stranded body scroll lock or retained open overlay.
- Account utility leads to public account page and its User menu; Sign out retires private controls and restores the public signed-out header.
- Anonymous middleware redirect never counts as successful private-shell coverage.

`auth-boundaries.cjs` / `auth-boundaries.log` / `auth-results.json`: all three independent auth groups pass.

- Holding the browser profile read leaves the actual Verifying access placeholder with neither private work nor either navigation; releasing it mounts the real admin shell.
- An editor browser profile, after an authorized middleware response, causes private content to retire and the public header to return.
- A synthetic editor is refused by real middleware on both `/admin` and `/status`.

These independent browser runs deliberately return unavailable 503 responses for browser application-data APIs. They test shell behavior and truthful unavailable-data handling, complementing the author's populated inert fixtures. They do not validate financial figures or backend data correctness. Root-layout providers and the actual browser auth transport remain in the path. Non-loopback requests are blocked.

## Adversarial harness finding, repaired

Valid finding S1: the original new `reachable()` helper accepted a fully transparent control (`opacity: 0`) as visible and clickable, because Playwright visibility excludes opacity. This was a new acceptance-test false green, not a claimed current production CSS defect.

`harness-controls.cjs` extracts and transpiles the exact candidate helper, then executes it in real Chromium. The initial five-control run accepted the transparent control incorrectly while correctly refusing absent, CSS-hidden and covered controls. `harness-controls-red.log` and the author's independent `harness-control-root-red.log` preserve that executed failure. The author added ancestor opacity checks and permanent browser controls.

The final helper run (`harness-controls-green.log`, `harness-results.json`) has six correct dispositions: ordinary visible link accepted; missing target, CSS-hidden target, covering header, transparent ancestor and transparent leaf all refused. The product source bytes did not change for this test repair. The author's follow-up receipt is `harness-control-root-green.log` in the parent evidence directory.

`runner-failure-controls.cjs` also executes the real installed Playwright CLI against owned external negative inputs. Missing fixture configuration, missing service child and an empty browser inventory each exit 1 with their intended named diagnostic, without executing the would-pass sentinel test. Receipts are `runner-failure-results.json` and per-input logs. Missing prerequisites are refused, rather than reported as acceptance.

## Final configuration and reflow controls

The final configuration-only safety delta was independently executed by `config-boundary-controls.cjs`: five checks pass. The exact config is transpiled and evaluated with controlled filesystem observations. Each of `.env`, `.env.local`, `.env.production` and `.env.production.local` causes the intended refusal. In the clean case, the internal server API, browser API and Supabase transport all remain pinned to loopback 8137 despite an inert hostile ambient INTERNAL_API_URL, and both fixture servers refuse reuse. No actual env files were created in the checkout. This verifies the configuration boundary and does not claim that every inherited environment variable is stripped.

`reflow-control.cjs` passes on `/admin`, `/admin/social/new` and `/status` at 864 CSS pixels with DPR 2: no document overflow or blocked header control centers. This represents a 1728-physical-pixel 200% reflow condition; it does not exercise the native browser zoom control. The author separately reports native browser zoom acceptance, outside this reviewer's independent execution.

At the final source bookend, all three product source digests (Navigation, AdminNav and admin.module.css) match the bytes used by the independent browser run. The only subsequent harness change was the config safety delta checked above. The author reports a final full rebuild and 8/8 primary browser cases under that config; that result is attributed to the author rather than counted as independent execution.

## Review artifacts and limits

Screenshots at every tested width are retained externally. The 320px image was visually inspected: the expanded admin navigation, Account and theme controls remain above the real page heading, without the public header or clipped document text.

The first reviewer browser run queried the intentionally collapsed mobile navigation through an accessibility role before expanding it; a second run used case-sensitive `Sign in` while the product label is `Sign In`. Those were reviewer harness mistakes. They were corrected and the original failed receipts remain in `first-*` and `second-*`; neither was classified as a product finding. Negative runner commands briefly wrote the tracked default Playwright last-run metadata; the exact failed metadata was preserved externally and the file was restored byte-for-byte to HEAD. Negative configs now use external output directories. No product files were edited by this reviewer.

The source fix correctly scopes navigation ownership by exact path family and unmounts the entire public Navigation subtree on private entry. That also cleans its menu/modal state and scroll effects. Current private navigation is ordinary document flow, so wrapping increases its height without a fixed-header collision.

This review does not certify all admin routes, public pages, authenticated production states, real external auth, JWT validation, backend authorization, data/financial correctness, OAuth, publishing/uploads/generation, workers, all browsers, or WCAG conformance. Neither a passing local build nor these scoped browser controls establishes that the entire app is correct. Native browser zoom is not claimed by this reviewer; the separately retained reflow control labels its method precisely.

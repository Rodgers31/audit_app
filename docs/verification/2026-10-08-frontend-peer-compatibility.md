# Frontend dependency compatibility — 8 October 2026

Issue: #511. Base: `3dfc7b9e57311fc38f02683b9ce1985fd4365fe3`.

## Supported peer tree

The app keeps React and React DOM 19.2.4. `react-simple-maps` moves from 3.0.0 to pinned 5.0.5, whose [published peer contract](https://github.com/zcreativelabs/react-simple-maps/blob/v5.0.5/package.json) supports React 19 and supplies its own TypeScript declarations. The old v3 `@types/react-simple-maps` package is removed. The checked-in npm policy now uses `legacy-peer-deps=false`.

Direct development dependency `picomatch@4.0.7` satisfies fdir's optional `^3 || ^4` peer and tinyglobby's v4 requirement. Consumers requiring v2, including micromatch and anymatch, resolve their own 2.3.2 copies. There is no global v4 override. The existing framework, native embedding and security overrides are unchanged.

Clean `npm ci --include=dev --include=optional --no-audit --no-fund` succeeds with lifecycle scripts enabled and `ONNXRUNTIME_NODE_INSTALL=skip`, the upstream option for omitting extra GPU downloads. `npm ls --all --json` exits 0 with no reported problems. The same strict installation succeeds in actual Linux arm64 and amd64 Docker dependency stages.

Lockfile changes include the map's D3 v2-to-v3 dependency migration, public type dependencies, removal of the old map types, and relocation of version-specific picomatch copies. Other direct runtime dependencies retain their prior resolved versions.

## Required map migration

The [v5 Geography implementation](https://github.com/zcreativelabs/react-simple-maps/blob/v5.0.5/src/core/components/Geography.ts) forwards plain SVG style properties. It no longer processes the [v3 default/hover/pressed style states](https://github.com/zcreativelabs/react-simple-maps/blob/v3.0.0/src/components/Geography.js). A dependency-only update rendered all 47 home county paths black in the actual browser fixture despite passing click/keyboard checks. That candidate was rejected.

`StyledGeography.tsx` restores those application style states around real v5 Geography. It preserves refs, accessibility props, callbacks, keyboard focus and pressed-state reset on mouse leave/blur. Missing states remain missing rather than being merged with defaults. All three Geography callers now import this wrapper; their data, projections, palettes, county matching and selection logic retain their existing behavior. Marker callers use their existing child styles and need no migration.

The [versioned changelog](https://github.com/zcreativelabs/react-simple-maps/blob/v5.0.5/CHANGELOG.md) and [full source comparison](https://github.com/zcreativelabs/react-simple-maps/compare/v3.0.0...v5.0.5) were checked, including the TypeScript rewrite, responsive SVG fix, public types and projection/zoom changes. This app does not use ZoomableGroup, Graticule or Sphere.

## Verification

- Wrapper regression tests execute actual v5 Geography; only its unused D3 imports are stubbed for Jest's CommonJS loader. The tests failed before the state migration and passed afterward. They check path/ref/aria/tabindex, colors, pointer/focus/pressed state, exact callback counts, and missing styles.
- Twelve real Chromium component runs cover three map containers, desktop 1280px and touch/mobile 390px, baseline v3 and migrated v5. All render 47 paths. Selection, touch, Enter/Space/Escape, focus transfer/restore, markers, missing figures and mobile tooltip fit pass.
- Six baseline comparisons preserve all 47 fixture county colors, including all audit palette keys and the unknown-status fallback. Home hover/pressed/release/leave/focus/blur styles match. SVG viewBox, bounds and path strings match for this TopoJSON/projection fixture; this is not a claim about every D3 projection or dataset.
- TypeScript passes. Lint passes. The full isolated Jest suite passes: 126 suites, 1,602 tests, one existing skip. `verify:dependency-tooling` passes parser, Tailwind, typography and nesting checks. Actual production builds are documented in the separate container verification report.

Jest was run without Supabase configuration or private environment files. An initial run with inert Supabase values enabled the auth client's asynchronous session path and exceeded two retry-test timing assumptions; removing that unnecessary test configuration produced the recorded isolated pass. This is not presented as a production auth verification.

The map browser fixture runs real components and the actual library on localhost, with synthetic county inputs and real map geometry. Its TypeScript loader does not transform styled-jsx; two known `jsx`/`global` attribute warnings are recorded separately. These component runs do not claim to cover every production page, browser, device or map interaction. Container-level browser verification is recorded in the packaging report.

## Security scope

The current audit remains 38 affected entries overall (33 high, five moderate), and five production entries, all in the already tracked braces chain. Development-only sprintf also remains tracked in #494. This peer/packaging fix neither closes those unpatched upstream advisories nor assumes an owner risk exception.

Local raw receipts, rejected-candidate evidence and screenshots:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/DEPENDENCY_511_2026-10-08/`.

## PR #516 review follow-up

Copilot's mixed pointer/keyboard finding was reproduced against the reviewed
head `2014b826d8efb2490eb124bb9233a2f8f73c25ab`. The original compatibility
wrapper used one flag for hover and focus, so pointer leave could clear the
highlight while the SVG path remained the active DOM element. Hover followed
by focus and blur had the reciprocal defect.

The wrapper now tracks hover and focus independently. Either keeps the
existing hover palette visible; leave and blur still cancel pressed styling.
This intentionally improves the inherited v3 mixed-input behavior. The earlier
single-input palette and geometry comparisons remain historical migration
receipts, rather than a claim that the new mixed-input behavior exactly matches
v3.

Three new tests were observed failing before this correction and passing
afterward, including a rerender with current styles, callbacks and the same
forwarded ref. All five wrapper tests pass. Twelve additional real Chromium
component runs cover both mixed-input sequences in all three callers at desktop
1280px and touch/mobile 390px. Each retains its active highlight after the
other input state clears. The home map's coarse-pointer tooltip overlaps the
small fixture county; its two mobile sequences therefore use DOM MouseEvents
with native DOM focus. Those two runs verify component event handling, not
persistent native CSS hover on a touch device. The other ten runs use native
mouse input and DOM focus.

Receipts and before/after screenshots:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/REVIEW_516_2026-10-08/map-focus/`.

The coordinator's follow-up full isolated frontend run passes 126 suites and
1,605 tests, with the same one existing skip. TypeScript, lint and dependency
tooling pass. The final API helper also passes the affected Axios, endpoint,
server retry and county SSR suites (41 tests), the configuration scripts
(24 tests), and 33 independent transport-selection checks.

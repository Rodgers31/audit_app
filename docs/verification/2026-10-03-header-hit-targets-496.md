# Header hit targets — Refs #496

## Reproduced failure

Author baseline: `4326b46c0fe7c7b7e812369766444ba5ae7986e0`.
The first hosted Chromium run `37167981062` had 247 passes, 11 skips and two failures. At 1280px, the primary navigation Learn link intercepted EN/SW language buttons in the unchanged Learn headings and Kiswahili navigation cases. The retained hosted screenshots show the overlapping header.

The desktop navigation was a shrinking `min-w-0` flex item whose six nonwrapping children painted outside its allocated width. Wider fallback text could therefore cover the adjacent language, theme and sign-in controls. A new real-browser fallback/text-spacing control failed against the unchanged baseline: visible language button hit points belonged to a navigation link.

## Scoped correction

Desktop links now retain their intrinsic width and wrap inside the existing 64px navigation column. All six routes remain visible, with no hidden horizontal scrolling and no new breakpoint, label shrinking, branding or color changes. DOM order and the existing mobile drawer remain intact.

The mobile control probe also exposed the icon-only sign-in button's absent accessible name below 640px. Its existing translated label is now explicit as `aria-label`; the visible desktop text is unchanged. The three mobile locale probes failed before this label and passed afterward.

## Executed controls

The new `frontend/e2e/header-hit-targets.spec.ts` blocks Google font acquisition and stresses navigation with Arial fallback, 14px text, 0.12em letter spacing and 0.16em word spacing. It checks actual `elementFromPoint` ownership at three points on each link/control, link containment within the navigation box, and actual language clicks. English, Kiswahili and plain English run at 1280, 1281, 1366, 1439, 1440, 1536, 1920 and 2560px. Mobile checks cover 320, 390, 768 and 1279px, every drawer route, language controls, Escape focus restoration and released body scrolling. A keyboard case exercises the six routes in DOM order, language changes, theme switching and opening/closing the actual authentication modal.

Final production-build Chromium command:

```sh
BROWSER_TEST_PYTHON=/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python \
node scripts/run-legacy-e2e.mjs e2e/header-hit-targets.spec.ts \
  e2e/navigation.spec.ts e2e/learn.spec.ts e2e/responsive.spec.ts
```

Result: **34 passed, 5 existing Learn skips, 39 cases**. Both original failing cases were unchanged and passed. The five pre-existing skips concern unavailable video/story interactions. No force clicks, timeout changes, retries or quarantine were introduced. The harness uses its existing disposable SQLite fixture and local production Next build; this is not a production data assertion.

Scoped ESLint (`components/Navigation.tsx`, new E2E file): passed. `tsc --noEmit --incremental false`: passed. Production Next build: passed. `git diff --check`: passed.

The existing seven Navigation Jest tests could not execute successfully in the author's cached dependency tree: the testing library resolved the primary checkout's React DOM while the component used the author tree's React, causing invalid-hook-call errors. No test/import/dependency edits were made to hide this harness limitation. Root will execute these tests against its fresh `npm ci` dependency tree.

Saved desktop/mobile screenshots were visually inspected. The 1280px stressed headers show all six routes in two rows within 64px with unobstructed controls. The 320px drawer retains its visible route list and accessible controls. Logs/screenshots are retained under `REMAINING_HEADER_496_LOCAL` in the shared verification artifact directory.

## Remaining acceptance

Root owns consolidation and frozen-head Ubuntu hosted Chromium acceptance. Local fallback stress and unchanged original cases passing do not establish that hosted acceptance has already passed. No GitHub, Actions, deployment or production state was changed by this implementation.

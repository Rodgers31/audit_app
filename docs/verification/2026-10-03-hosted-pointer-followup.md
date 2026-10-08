# Second hosted Chromium pointer follow-up

Baseline: `2b04f1518bbc04ed7b99d60373c29b1ef148d443`.
Retained hosted run: `37171600493`, **255 passed, 11 unchanged quarantines, 3 failed**. This author change makes no hosted-green claim; root owns frozen-head hosted acceptance.

## Mobile drawer — confirmed product defect, Refs #496

The EN/plain failed screenshots were inspected alongside the trace and local reproduction. At 320×568, wider Ubuntu fallback labels wrap onto multiple lines and push the language controls below the viewport. The body is intentionally locked while the dialog is open, and the fixed-height drawer had no scroll overflow. `scrollIntoViewIfNeeded` therefore reported completion without bringing those controls into the viewport; all three `elementFromPoint` samples were null. This is a real responsive drawer limitation, not an assertion to bypass.

The first four-case local baseline passed with the author's narrower fallback font. Applying actual Arial fallback plus 0.12em letter spacing and 0.16em word spacing to the mobile route labels reproduced **the same two EN/Aa null-hit failures; SW passed** against unchanged product code. Both local red screenshots were inspected and retained. Font size and route labels were not shrunk or changed.

The drawer now has native vertical scrolling with contained scroll chaining; the route list retains its intrinsic height. No colors, breakpoint, body-lock or focus-trap behavior changed. The strengthened matrix verifies all six routes, actual mouse-wheel reach to the footer, language clicks and all three pointer points on the sign-in control. Escape still restores toggle focus and releases the body lock. Pointer diagnostics now include sample coordinates and viewport bounds; the ownership requirement is unchanged. Post-fix 320px EN/plain screenshots were inspected: language and sign-in controls are reachable within the drawer.

## Chart tooltip — confirmed test action/readiness defect

The hosted chart screenshot and trace were inspected. Immediately after hover (`after@call@443`) the actual tooltip contained **FY 2024/25, Debt service : KES 50.0B, Service / Revenue : 50.0%**. Before the quantity assertion, retained document scroll positions moved **2115 → 2015 → 1824**. The final tooltip was hidden and retained only the year label after the chart moved away from the stationary pointer. The trace therefore confirms correct monetary/ratio payload and a lost pointer position; it does not establish a financial product mapping defect. The original case also passed in the local baseline cohort.

The case now selects the exact accessible debt-cost figure, waits for both actual plotted fiscal-year markers, and observes font/rectangle/document-scroll readiness over six animation frames before hovering the first real marker. The readiness assertion observes geometry only; it does not repeat hover or retry the test. Assertions are stronger: tooltip visibility, exact fiscal year, debt-service **KES 50.0B** and service/revenue **50.0%**. No financial product logic, source data or chart rendering was changed.

## Executed gates

```sh
BROWSER_TEST_PYTHON=/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python \
node scripts/run-legacy-e2e.mjs e2e/charts.spec.ts \
  e2e/header-hit-targets.spec.ts e2e/learn.spec.ts e2e/navigation.spec.ts
```

Result: **50 passed, 9 existing quarantines, 59 cases**. This includes the full original chart file, every header locale/viewport matrix, and unchanged original Learn/navigation cases. The nine subset quarantines are the four existing unsupported chart controls and five existing Learn cases; none was added or expanded. Production Next build, scoped ESLint, TypeScript `tsc --noEmit --incremental false`, and `git diff --check` passed.

The fixture remains the existing disposable synthetic API and local production build. Logs and local red/green screenshots are retained under `REMAINING_HOSTED_POINTER_LOCAL` in the shared artifact directory. No force click, test retry, increased timeout, weakened quantity assertion or new quarantine was introduced. No new issue filing was needed: the drawer belongs to #496; the chart change repairs the existing original-case action. Root owns consolidation and frozen Ubuntu acceptance. No GitHub, Actions, provider, deployment or production state was changed by this author work.

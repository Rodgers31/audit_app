# Your county on County Explorer

The pinned link sits directly below the existing search. A successful county detail visit saves one canonical county slug in this browser, replacing the previous slug. A failed detail request leaves that choice alone. With no saved county or blocked storage, search and navigation remain available. The preference stays in this browser and the pin uses the Explorer dataset already loaded. [Approved County Explorer design](../../../ui-ux-audit-2026-11/index.html#b-counties)

The link uses the canonical county href after any supported alias visit. When that county is in the Explorer's current fiscal-year dataset, the link retains that year. Spending appears only if the selected period has one same-county budget and expenditure pair from the same Controller of Budget publication, both on the actual KES basis. The pin omits a rate when the source is withheld, ambiguous or from a different period. A published audit record grade remains unavailable in the Explorer dataset, which currently carries finding severity and financial-health scores.

## Verification

- The production build, TypeScript and ESLint with zero warnings passed. Three focused Jest suites passed all 22 tests.
- All eight Chromium and WebKit cases passed. They cover opening a county, Back and reload, search focus order and keyboard activation, canonical aliases, failed details, blocked storage, and changing fiscal year.
- Chromium checked light and dark at 360, 390, 430, 768, 1024, 1280 and 1440px. The pin stayed below search with no horizontal document overflow, a target larger than 44×44px, a visible keyboard focus ring, and no animation with reduced motion. Scoped axe WCAG 2.1 A and AA checks had zero violations in all 14 cases.
- The comparison figures use a synthetic Controller of Budget-shaped fixture in the disposable browser environment. The figures are for rendering verification only.

[360px comparison](comparison-360.png) · [768px comparison](comparison-768.png) · [1440px comparison](comparison-1440.png) · [360px dark](dark-360.png)

## Release dependencies

The approved implementation plan requires Explorer storage to be covered by the approved policy. The draft privacy text currently names theme and language only. The policy review must cover the saved county choice, local use and how to clear it before release. [Implementation plan](../../../ui-ux-audit-2026-11/IMPLEMENTATION_PLAN.md#decisions-and-dependencies-for-the-owner) · [Privacy draft](../../../ui-ux-audit-2026-11/index.html#l-privacy) · [Policy issue #936](https://github.com/Rodgers31/audit_app/issues/936)

The pin's spending adapter is separate while the compact rankings PR is queued. After #1024 merges, use its `publishedSpendingRate` selector for the pin and remove the standalone adapter so the two Explorer presentations share one source admission rule. [Compact rankings #1024](https://github.com/Rodgers31/audit_app/pull/1024)

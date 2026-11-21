# W3 debt composition verification

The [E13 owner revision and Debt blueprint](../../../ui-ux-audit-2026-11/index.html#e13) keep the two rings and the full-width instrument bar. The approved historical screenshot establishes the shape and placement. The running captures use synthetic figures from the Debt fixture.

| Approved form | Running Debt section |
| --- | --- |
| [Two rings and stacked bar](../../../ui-ux-audit-2026-11/img/debt_donut.jpg) | [360px](composition-light-360.png) · [768px](composition-light-768.png) · [1440px](composition-light-1440.png) |

[360px dark](composition-dark-360.png) · [360px expanded lender details](composition-lenders-360.png) · [1440px instrument hover](composition-hover-1440.png)

The outer ring groups domestic, external and unclassified amounts. The inner ring and stacked bar use the same proportions, instrument order and numbered key as the rows. Short segments show the number when it fits. Full names and shares are available in the rows. Hovering an instrument shows its full name and share near the donut, with the amount and key at the center. Touch and keyboard users can expand the keyed rows for exact amounts and lender details.

The component uses the positive lender groups already admitted by the national debt adapter. It excludes pending supplier bills. When any group uses original principal, the center reads “Total shown” and the affected rows keep the principal qualification. An absent individual amount stays unavailable, and a reported zero stays zero.

## Verification

- Production build, TypeScript and scoped ESLint passed.
- Jest passed 209 tests across 19 suites, with one existing skipped test. Chromium and WebKit passed all 32 Debt page and acceptance checks.
- Both browsers passed a 360, 390, 430, 768, 1024, 1280 and 1440px run in light and dark mode. All seven fixture categories kept the same distinct fills and order across the two instrument charts and keyed rows. Segment widths matched the admitted data, and the page had no horizontal overflow. At 360px the donut measured 302px, the amount at its center exceeded 27px, and the shortest closed category control was 72px tall.
- Scoped axe reported no WCAG 2.1 AA violations in either theme, with category disclosures open and closed. Main text was at least 14px. Reduced motion, tap, keyboard activation and collapse, hover reset, long names at 360 and 390px, and narrow segment labels passed. Muting another group changes its fill while leaving the text at full contrast.

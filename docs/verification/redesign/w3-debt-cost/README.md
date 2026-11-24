# Debt cost over time verification

The [debt blueprint](../../../ui-ux-audit-2026-11/index.html#b-debt) and [C1 chart mockup](../../../ui-ux-audit-2026-11/index.html#c-gallery) show two small charts with matching fiscal-year positions. They stack below 1024px and sit side by side from 1024px, as described in the [phone](../../../ui-ux-audit-2026-11/index.html#c-phone) and [desktop](../../../ui-ux-audit-2026-11/index.html#c-desk) chart rules. The stacked charts share a single year-label row.

| Viewport or state | Capture |
| --- | --- |
| 360px | [Approved C1 mockup and implementation](comparison-360.webp) |
| 768px | [Approved C1 mockup and implementation](comparison-768.webp) |
| 1440px | [Approved C1 mockup and implementation](comparison-1440.webp) |
| 360px dark | [Charts](dark-360.webp) |
| 360px | [Open source table](table-360.webp) |

The captures use five synthetic fiscal years. The line separates at a year with qualified repayments and revenue from different source documents. It plots a published zero at the baseline. The latest approved values name their budget basis, and the text states when the share exceeds the half-of-revenue reference. The chart window covers up to five fiscal years, and the table keeps every observation the API supplied with its original values, basis, source and printed precision. The default disposable API separately exercised two qualified years with KES 50 billion in repayments and KES 50 per KES 100 in revenue.

The production build, TypeScript and lint passed. Three focused Jest suites passed all 19 tests. Seven focused Chromium cases and seven WebKit cases passed. They cover the chart series and exact evidence table, hover and keyboard readouts, named chart and axis alignment when intermediate labels are hidden.

Chromium checked 360, 390, 430, 768, 1024, 1280 and 1440px in light and dark, with the source table closed and open. All checks passed for document and section overflow, year and target alignment, a 44px minimum target, 14px body text, 12px chart labels, reduced motion and scoped axe WCAG 2.1 A/AA. A real Chromium touch drag moved and selected the fiscal-year readout, and keyboard Escape cleared the selection.

This implements the repayment and revenue-share charts. Debt-to-GDP has a separate blueprint item.

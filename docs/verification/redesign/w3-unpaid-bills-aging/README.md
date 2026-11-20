# Unpaid-bill ages verification

The [Debt blueprint](../../../ui-ux-audit-2026-11/index.html#b-debt) and [C5 chart mockup](../../../ui-ux-audit-2026-11/index.html#c-gallery) show four horizontal age bands with compact amounts and the published oldest band in alarm red. The panel shows the selected reporting scope and date. Reading or selecting a bar exposes exact KES, and the data table and source sheet preserve the source's exact figures and qualifications.

| Viewport or state | Capture |
| --- | --- |
| 360px | [Approved C5 mockup and published executive bands](comparison-360.webp) |
| 768px | [Approved C5 mockup and published executive bands](comparison-768.webp) |
| 1440px | [Approved C5 mockup and published executive bands](comparison-1440.webp) |
| 360px dark | [Executive age chart](dark-360.webp) |
| 360px | [Assembly source table and discrepancy](assembly-360.webp) |
| 360px | [Unpublished age breakdown](unavailable-360.webp) |

The public summary and official report agree on the four executive cells at 30 June 2026. The source reports an executive aging total for 46 of 47 counties and all four bands for 41 of 47. CoB Table 2.11 records KES 70,235,180,000 in the oldest band. The report's SHA-256 matches the source artifact in both public observations. [Public summary](https://www.auditgava.com/api/v1/pending-bills/summary) · [CoB Table 2.11, PDF p.54](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482#page=54)

CoB Table 2.12 publishes the assembly bands separately. They do not add up to the printed total, so the table keeps both as published and the chart stays unavailable. National and combined scope show “Age of these bills not published.” [CoB Table 2.12, PDF p.55](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482#page=55) · [Original assembly source work](https://github.com/Rodgers31/audit_app/issues/800)

The production build, TypeScript, lint, 34 Jest tests, one Chromium case and one WebKit case passed. Chromium checked 360, 390, 430, 768, 1024, 1280 and 1440px in both themes for overflow, 44px controls, at least 14px text, scoped axe WCAG 2.1 A/AA and reduced motion. It exercised scope changes, touch and keyboard readouts, the exact source table and the source sheet's focus return. The captures replay published age observations inside a disposable preview.

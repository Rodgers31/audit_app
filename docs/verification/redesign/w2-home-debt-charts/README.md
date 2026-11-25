# W2 Home debt chart verification

C2 separates nominal debt and debt as a share of GDP into two small charts. The implementation shares the same chronological x positions, gives each measure its own y scale and shows a straight line with a flat fill only on the nominal plot. [Approved C2 and E13](../../../ui-ux-audit-2026-11/index.html#c-gallery)

| Approved form | Home with a qualified synthetic timeline |
| --- | --- |
| [C2 reference](approved-c2.png) | [360px phone](home-debt-light-360.png) · [768px tablet](home-debt-light-768.png) · [1440px desktop](home-debt-light-1440.png) · [1440px dark](home-debt-dark-1440.png) |

[360px legacy response](home-debt-legacy-360.png) demonstrates the deployed response shape with no matched period metadata. Its nominal line remains visible and the ratio panel explains the absence.

The existing Home card keeps its source evidence and its register and sustainability figures. The chart uses the API’s admitted nominal amounts. The ratio comes only from `publishedTimelineRatio`, which requires the independently checked monthly stock and annual GDP pair. The public endpoint returned rows without the explicit stock/GDP period at verification time. Main’s serializer supplies this period when supported by the evidence. [Public timeline endpoint](https://www.auditgava.com/api/v1/debt/timeline)

The synthetic timeline exercises 2022 missing from the response, source-qualified GDP rows for 2023–25 and an available 2026 nominal observation with no verified annual GDP pair. The missing year breaks the nominal line. The absent ratios stay unplotted. The shared year picker works with a keyboard and tap, and either plot can select the year by tap. The yearly readout and expandable table include the existing domestic and external values. Missing values read as unavailable and a verified zero stays zero.

## Verification

- The production build, TypeScript, scoped ESLint and 59 Jest tests passed.
- Seven Home browser tests passed in Chromium. Six Home tests passed in WebKit, including both C2 tests. The unchanged Home hero Tab-order check failed at the same link on an isolated WebKit build of baseline `f4c763b`; it is excluded from that pass.
- The chart passed the seven-width matrix at 360, 390, 430, 768, 1024, 1280 and 1440px in Chromium and WebKit, light and dark. The charts measured identical horizontal plots and year positions. There was no document overflow with the values table open or closed. Controls measured at least 44px, chart tick labels at least 12px and body labels at least 14px. Reduced motion and scoped WCAG 2.1 AA axe checks passed in both table states.

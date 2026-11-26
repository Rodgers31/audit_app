# Debt-to-GDP context verification

The [debt blueprint](../../../ui-ux-audit-2026-11/index.html#b-debt) places Debt-to-GDP after the cost charts. The [signal rule](../../../ui-ux-audit-2026-11/index.html#s-rule) uses neutral ink for a nominal Debt-to-GDP figure. The section gives the reference year, published basis and source. A missing or incompatible figure stays unavailable. The debt distress assessment is separate.

| Viewport or state | Capture |
| --- | --- |
| 360px | [Approved instructions and dated context](comparison-360.webp) |
| 768px | [Approved instructions and dated context](comparison-768.webp) |
| 1440px | [Approved instructions and dated context](comparison-1440.webp) |
| 360px dark | [Dated context](dark-360.webp) |
| 360px | [Unavailable figure](unavailable-360.webp) |

The browser proof uses the existing synthetic debt overview fixture. The production snapshot and broader series were checked read-only. They agree on the 2025 WEO ratio and data acquisition timestamp. The October 2026 IMF workbook confirms the published 2025 value, the actual-year boundary for that release and Kenya's reporting and coverage metadata for the WEO series. The figure uses the WEO series name and labels the API timestamp as the data snapshot. The independently qualified CBK and World Bank fallback retains its own sources and dates. [AuditGava debt snapshot](https://www.auditgava.com/api/v1/debt/national) · [AuditGava WEO series](https://www.auditgava.com/api/v1/debt/broader) · [IMF WEO database and October 2026 workbook](https://data.imf.org/datasets/WEO)

The historical chart is pending [#1035](https://github.com/Rodgers31/audit_app/issues/1035). The public WEO history currently sets forecast flags from the acquisition year. The IMF's actual-year boundary varies by country and series, and needs to travel with the published snapshot. [IMF WEO actual-data methodology](https://data.imf.org/en/Datasets/WEO/Frequently-Asked-Questions)

The production build, TypeScript, lint, 77 focused Jest tests and four Chromium and WebKit cases passed. Chromium checked 360, 390, 430, 768, 1024, 1280 and 1440px in both themes. It found no overflow, with targets of at least 44px, body text of at least 14px, reduced-motion support and no scoped WCAG 2.1 A/AA violations. Keyboard focus returned to the evidence button after Escape.

The merge rehearsal with [#1033](https://github.com/Rodgers31/audit_app/pull/1033) was clean. [#1021](https://github.com/Rodgers31/audit_app/pull/1021) replaces the section immediately after the insertion and produced one conflict in `DebtPageClient.tsx`. The local resolution retained the approved cost charts, then the new Debt-to-GDP section, then the loan register and its existing props.

# W9 guided budget path verification

[Approved Learn directive](../../../ui-ux-audit-2026-11/index.html#b-learn) and [captured written reference](approved-guided-path.png). The directive specifies the title, short cards, one sourced figure and a Next control. The four-step budget path is the first of the three paths described there.

| Evidence | Capture |
| --- | --- |
| Learn entry at 390px | [Guided paths](learn-entry-390.webp) |
| Qualified synthetic spending card | [360px](qualified-light-360.webp), [768px](qualified-light-768.webp), [1440px](qualified-light-1440.webp), [360px dark](qualified-dark-360.webp) |
| Qualified synthetic final card at 390px | [County transfers](qualified-last-390.webp) |
| Recorded and qualified Treasury fixture at 390px | [Official spending receipt](recorded-treasury-390.webp) |
| Legacy public response at 360px | [Figure unavailable](legacy-unavailable-360.webp) |

## Data and destinations

The synthetic screenshots use clearly labelled fixture amounts. The recorded screenshot replays the published-data fixture in [frontend/test/fixtures/deploymentFiscalFiveYears20261105.json](../../../../frontend/test/fixtures/deploymentFiscalFiveYears20261105.json). All four replayed figures match the FY 2026/27 Budget column in Annex Table 2a, PDF page 63. A fresh download of the primary document matched the fixture’s SHA-256 digest. [Treasury Budget Summary, PDF page 63](https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget%20Summary%20for%20the%20FY%202026_27%20Budget.pdf#page=63)

On 19 November 2026, the public summary returned FY 2026/27 and a legacy framework with an Approved column and a source page. The framework omitted its own fiscal year, qualification version, precision, cell witnesses and a valid source digest. All four guide cards showed the verified-source unavailable state during replay. The guide requires the current Nairobi fiscal year and the existing independently qualified, reconciled Approved framework. [Read-only public summary](https://www.auditgava.com/api/v1/fiscal/summary) · [Fiscal source health #945](https://github.com/Rodgers31/audit_app/issues/945)

| Step | Live context | Evidence |
| --- | --- | --- |
| Spending | [Budget](https://www.auditgava.com/budget) | HTTP 200. The Budget page presents the national plan. |
| Revenue | [Revenue in the glossary](https://www.auditgava.com/learn/glossary#term-revenue) | HTTP 200. Browser navigation opened the Revenue definition. |
| Financing | [National debt](https://www.auditgava.com/debt) | HTTP 200. The Debt page puts the outstanding balance in context. |
| County transfers | [Follow county spending](https://www.auditgava.com/transparency) | HTTP 200. Follow the Money tracks allocation through county spending. |

## Checks

- Chromium ran at 360, 390, 430, 768, 1024, 1280 and 1440px in light and dark. The document width matched the viewport. The sampled step controls measured at least 82px wide and 44px tall. The largest CSS duration under reduced motion was 1ms.
- Scoped axe-core WCAG 2.1 AA found zero violations and zero incomplete results on the spending card at all 14 viewport and theme combinations. The Learn entry and legacy card also had zero violations.
- In Chromium, keyboard activation opened all four cards, moved focus to the new heading, and reached the Revenue anchor. Browser Back and reload retained the current card. Previous worked over keyboard. Swahili and plain English also fit at 360px.
- In WebKit with touch input, a direct financing link opened step three, Next advanced to step four, and the final control returned to the Learn guided paths anchor.
- Node v24.22.1 ran three Jest suites with 25 tests passing. The suites cover the new guide data adapter, Glossary and the retained fiscal consumers.
- TypeScript, repository lint and production build passed. Browser verification used that production build and a loopback fiscal API. There were no uncaught browser errors.

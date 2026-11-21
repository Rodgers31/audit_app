# W8 desktop findings verification

The Audits blueprint calls for a filterable desktop table that opens a detail pane on the right. The desktop browse reference places the table and pane in a 40/60 split, with filters above both. The E11 finding cards continue below 1024px. [Audits blueprint](../../../ui-ux-audit-2026-11/index.html#b-audits) · [Desktop browse layout](../../../ui-ux-audit-2026-11/index.html#i-desktop) · [E11 finding cards](../../../ui-ux-audit-2026-11/index.html#e11)

| Approved reference | Running findings section |
| --- | --- |
| [Desktop table and pane requirements](approved-audits-blueprint.png) · [40/60 browse diagram](approved-desktop-browse.png) | [1440px desktop, pane open](findings-pane-light-1440.png) · [1440px desktop, dark](findings-pane-dark-1440.png) |
| [E11 finding cards](../../../ui-ux-audit-2026-11/index.html#e11) | [360px cards](finding-cards-light-360.png) · [768px cards](finding-cards-light-768.png) |

The table and pane read the current page of published findings. The right pane reads the finding text, metadata and existing page-linked report URL from that row. Row citation links open the source independently. With the pane open, keyboard focus moves to its heading. Close and Escape return focus to the original row, and pagination returns focus to the findings heading.

The backend continues to order the results before pagination. The desktop sorting controls explicitly apply to the current page and keep unreported years at the end. Filters and pagination clear the selected finding. Missing figures and sources are explicit. The exact amount in the pane is labelled “Amount mentioned” to preserve the source’s scope. A recorded zero is still shown.

## Verification

- The previous Severity request values did not match the stored enum. The existing endpoint now receives `CRITICAL`, `WARNING` or `INFO` from the Audits filter. The isolated SQLite-backed test returned 48 Warning rows and zero Critical rows.
- Production build, TypeScript, scoped ESLint and 97 Jest tests passed.
- Chromium and WebKit passed 28 Reports and four Audits smoke and empty-state checks. The browser tests covered the real severity filter response, sorting, server pagination, the sparse pane, row click, keyboard opening and closing, focus return, the independent exact-page link, and the mobile card breakpoint.
- Chromium and WebKit passed light and dark runs at 360, 390, 430, 768, 1024, 1280 and 1440px. The page had no horizontal overflow, and visible controls measured at least 44px. Desktop table and pane text measured at least 14px. The selected desktop layout measured 40/60. Scoped axe reported zero WCAG 2.1 AA violations, including with the pane open. Touch operation and reduced motion passed.

The screenshots use a loopback-only synthetic set with a stated amount, a stated zero, a missing amount and a missing citation. The existing national severity chart continues to use its own collection grouping. The county ranking follow-up remains tracked in [#997](https://github.com/Rodgers31/audit_app/issues/997).

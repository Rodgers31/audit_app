# What the Auditor-General does

The second guided path has four short cards with one figure per card. It opens from Learn’s Keep learning section. Named URLs preserve a card across reload and browser history. Moving between cards focuses the new heading. Each card links to Article 229 in the Constitution reader and a related AuditGava page. [Approved guide directive](../../../ui-ux-audit-2026-11/index.html#b-learn)

## Figure sources

| Card | Figure and scope | Primary source |
| --- | --- | --- |
| Who does the auditing? | 8-year term of office, subject to Article 251, with one appointment | [Constitution of Kenya, Article 229(1) and (3), p. 135](https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf#page=135) |
| When must the Auditor-General report? | 6 months from the end of each financial year, for auditing and reporting on the accounts and public debt listed in the article | [Constitution of Kenya, Article 229(4), pp. 135–136](https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf#page=135) |
| What does an audit report tell us? | 44 of 47 county executive financial statements with a qualified opinion, year ended 30 June 2025 | [Office of the Auditor-General, Summary Report on County Governments, table 8, printed p. 21, PDF p. 35](https://libraryir.parliament.go.ke/server/api/core/bitstreams/e13a8fad-5b91-4ca2-bfa5-4d1d767be980/content#page=35) |
| Who acts on the report? | 3 months from receipt, for Parliament or the relevant county assembly to debate and consider the report and take appropriate action | [Constitution of Kenya, Article 229(7) and (8), p. 136](https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf#page=136) |

The opinion card uses the County Executives column of Table 8. The guide explains financial-statement problems and audit evidence gaps as possible grounds for a qualified opinion. It identifies allegations about individual conduct as separate claims. [OAG report archive](https://libraryir.parliament.go.ke/items/e5ddd9fd-1cb5-4784-aa21-330f2cb0eb2b) · [IAASB, ISA 705 (Revised)](https://www.iaasb.org/publications/international-standard-auditing-isa-705-revised-modifications-opinion-independent-auditor-s-report-3)

The Parliament downloads were checked on 20 November 2026. The Constitution PDF SHA-256 was `8fa672222d016913bd60b19c9794cb50b0457a0fae9af2aacb262d32545cb789`. The archived OAG PDF SHA-256 was `718966092e684cec3700752030c6092f8947954fdd529e674d29d40b22db3102`.

## Verification

- The production build, TypeScript, lint with zero warnings, and 13 tests across two focused Jest suites passed.
- Eight Chromium and WebKit tests passed. They opened the guide from Learn and checked keyboard navigation and heading focus, browser Back and reload, touch, Kiswahili and plain English, and the published reader and destination routes.
- All four cards passed at 360, 390, 430, 768, 1024, 1280, and 1440px in light and dark. All 56 scoped axe WCAG 2.1 A/AA checks had zero findings. Card controls met 44×44px, body text measured at least 14px, document width matched the viewport, and no animation ran with reduced motion.
- Both the loopback preview and the public site returned HTTP 200 for the Article 229 reader, government audit glossary anchor, Sources method, Audit Findings and Nairobi audit tab. The browser tests checked the actual article, anchors and tab selection.

[Approved directive](approved-guided-path.png) · [Term at 360px](office-light-360.png) · [Reporting at 360px](reporting-light-360.png) · [Opinion at 360px](opinion-light-360.png) · [Opinion at 768px](opinion-light-768.png) · [Opinion at 1440px](opinion-light-1440.png) · [Opinion at 360px dark](opinion-dark-360.png) · [Action at 360px](action-light-360.png)

## Integration

The entry sits in the existing Keep learning section while the first guide’s hub section is queued. After #1039 merges, move the entry into that section, retain the `#auditor-general-path` anchor and share the guide card navigation if it can preserve both query contracts. The local merge rehearsal with #1039 was clean. [Budget guide #1039](https://github.com/Rodgers31/audit_app/pull/1039)

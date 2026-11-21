# W10 public sitemap verification

The Next.js production build served `/sitemap.xml` as XML with the standard sitemap namespace and 64 unique absolute URLs. The sitemap retains the 12 previously indexed pages and adds `/audits`, `/sources`, `/counties/compare`, `/accountability/unaccounted-funds`, `/learn/why-it-matters` and 47 county pages. All 64 destinations returned HTTP 200 HTML directly from the build. `/robots.txt` points to the same sitemap on the public origin.

The XML’s county paths match all 47 choices in the Home county search and the 47 names in the published county index. Browser replays of the public comprehensive responses rendered the right county on `/counties/Murang%27a`, `/counties/nairobi` and `/counties/elgeyo-marakwet`. The existing county registry preserves the encoded apostrophe and the hyphenated names. [Public county index](https://www.auditgava.com/api/v1/counties)

The current sitemap used the same generation timestamp across all entries. The new XML omits `lastmod`. The repository has no shared, stable date source that represents when each indexed page changed. [Sitemap protocol](https://www.sitemaps.org/protocol.html#xmlTagDefinitions)

With Node 24.22.1, three focused Jest tests, TypeScript, ESLint and the Next.js production build passed. The loopback build used isolated route fixtures for the three county rendering checks.

## Related metadata in #942

Read-only check of `29ac932` and the isolated sitemap build.

| Route | Observed result |
| --- | --- |
| County details | Generic `County Detail — AuditGava` server title and no county `rel=canonical` on three sampled routes. |
| Sources, Unaccounted funds and newsletter unsubscribe | Inherit the site title. |
| Government and Why This Matters | Inherit `Learn \| AuditGava`. |
| Figure evidence | Server fallback is `Figure evidence \| AuditGava`. The client uses the fetched figure for the title and disables breadcrumbs on this route. |
| Glossary, quiz, reset password and 404 | Distinct titles already appear. |
| Breadcrumbs | The sampled Government, Why This Matters and Unaccounted funds crumbs use readable labels on desktop. |

The remaining route-specific metadata and figure breadcrumb work stay in [#942](https://github.com/Rodgers31/audit_app/issues/942).

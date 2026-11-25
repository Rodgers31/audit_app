# County search and link previews

The county detail route now renders its name, description, and canonical link in the server response. Open Graph and Twitter use the same title and description and keep the site's preview image. Alias links point to the same href the County Explorer uses. [Issue #942](https://github.com/Rodgers31/audit_app/issues/942) · [Implementation plan](../../../ui-ux-audit-2026-11/IMPLEMENTATION_PLAN.md)

| Request path | Server title begins with | Canonical path |
| --- | --- | --- |
| `/counties/Murang%27a`, `/counties/Murang%E2%80%99a`, `/counties/021` | Murang'a County | `/counties/Murang%27a` |
| `/counties/Taita%20Taveta`, `/counties/taita-taveta` | Taita Taveta County | `/counties/taita-taveta` |
| `/counties/001`, `/counties/code%3A047` | Nairobi County | `/counties/nairobi` |
| `/counties/047`, `/counties/code%3A001` | Mombasa County | `/counties/mombasa` |
| `/counties/unknown-county`, `/counties/4`, `/counties/muranga` | County detail | No county canonical |

The app accepts historical three-digit route IDs and explicit official codes. Nairobi and Mombasa have different numbers in the two systems. Unpadded database IDs can vary between environments and get a generic title with no canonical county or `og:url`. The canonical uses the configured public origin or `https://www.auditgava.com`, matching the sitemap's origin setting. [Official county order, First Schedule](https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf)

## Verification

- Production Next.js build, TypeScript, and ESLint with zero warnings.
- Jest checks all 47 canonical links, both complete backend code lists, encoded aliases and generic fallbacks. The metadata unit test verifies generation leaves the existing county data query to the page. The two focused suites passed all 55 tests.
- All 26 Chromium and WebKit cases passed with a disposable loopback API and a crawler user agent with JavaScript disabled. The browser regression checks the original document head, exact title and description, canonical URI, and matching social tags. The route has no layout, controls, or motion changes, so the evidence is the server-rendered document head.

# Kiswahili banner verification

The first-visit banner now sits between the fixed navigation and the page content. Its own height leaves room for the heading, and it scrolls away with the page. The copy, dark strip, and button hierarchy follow the [approved E21 mockup](../../../ui-ux-audit-2026-11/index.html#e21).

| Viewport | Capture |
| --- | --- |
| 360px | [Approved mobile mockup and before and after screenshots](comparison-360.webp) |
| 768px | [Before and after screenshots](comparison-768.webp) |
| 1440px | [Before and after screenshots](comparison-1440.webp) |

The screenshots use a fresh browser context with `sw-KE`. On the homepage, the previous banner covered 81px of the heading area at 360px and 29px at 1440px. In the updated preview the heading starts 16px below the banner on mobile and 40px below it on desktop.

- Chromium, Firefox, and WebKit passed nine automated cases for the first-visit layout, fixed navigation, and language choice persistence. Chromium passed all 20 navigation and header tests.
- The preview passed 210 layout checks across seven widths from 320px to 1440px, two color schemes, three engines, and five routes. The heading stayed clear, the page fit its viewport, and both buttons stayed at least 44px tall.
- All six scoped axe scans passed. The production build and all 284 Jest suites passed, with 3,689 tests passing and one existing skip.

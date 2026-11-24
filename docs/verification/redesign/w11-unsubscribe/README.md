# Newsletter unsubscribe verification

The approved [system-page mockup](../../../ui-ux-audit-2026-11/index.html#f-system) shows an email field, a full-width Send unsubscribe link button and a Home link beneath it. The implementation uses the normal application shell and the same form styles as the reset page. A rejected or malformed link opens the request form. A valid signed link keeps its confirmation step.

| Viewport or state | Capture |
| --- | --- |
| 360px | [Approved mock and implementation](comparison-360.webp) |
| 768px | [Approved mock and implementation](comparison-768.webp) |
| 1440px | [Approved mock and implementation](comparison-1440.webp) |
| 360px dark | [Direct entry](dark-360.webp) |
| 360px | [Unusable signed link](expired-360.webp) |
| 360px | [Generic request receipt](receipt-360.webp) |

Chromium checked 360, 390, 430, 768, 1024, 1280 and 1440px in light and dark. The form and receipt had no horizontal overflow, their smallest target measured 44px and their smallest text measured 14px. The form and receipt passed scoped axe WCAG 2.1 A/AA checks. Keyboard focus advanced from Email to Send to Home, and the receipt received focus after a successful request. Reduced-motion checks allowed the shared 1ms transition.

The production build, TypeScript and lint passed. Two related Jest suites passed all 15 tests. Chromium and WebKit passed four flow cases each covering anonymous submission, signed confirmation and invalid-link recovery, retry after an unavailable response, and retry after a client timeout. Forty-five backend newsletter and route-authentication tests passed against disposable SQLite. They cover the same receipt for active, absent, opted-out and throttled addresses, timeout, signed-link compatibility, idempotent confirmation and dispatch capacity.

The disposable preview overrode SMTP with a local recording stub and blocked the real transport. It returned the same `202` and `Cache-Control: no-store` for a synthetic active address, a synthetic absent address and a second request within the cooldown. The stub recorded one delivery.

The resend limits apply per process in the configured single-worker service. An address can reserve one attempt every 15 minutes, the worker can reserve 12 attempts per minute, and up to three deliveries can run concurrently. The counters reset when the worker restarts. Unavailable delivery configuration or a failed lookup returns a generic retry response. A failed or suppressed background delivery yields the same conditional receipt as an accepted request.

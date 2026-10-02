import { Page } from '@playwright/test';
import nationalObservation from '../fixtures/debt_overview.json';

/** All counties, fiscal figures, budget and audits come from the same seeded
 * synthetic API for SSR and browser fetches. Only national debt is intentionally
 * absent at prefetch time so tests can supply hostile browser observations. */
export async function registerApiMocks(page: Page) {
  await page.route('**/api/v1/debt/national', route => route.fulfill({ json: nationalObservation }));
}

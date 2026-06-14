import { Page, Request, Route } from '@playwright/test';
import counties from '../fixtures/counties.json';
import debtBreakdown from '../fixtures/debt_breakdown.json';
import debtOverview from '../fixtures/debt_overview.json';
import debtTimeline from '../fixtures/debt_timeline.json';
import topLoans from '../fixtures/top_loans.json';

function jsonResponse(body: any, status: number = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  };
}

export async function registerApiMocks(page: Page) {
  await page.route('**/api/**', async (route: Route, request: Request) => {
    const url = request.url();

    // Counties endpoints
    if (url.includes('/api/v1/counties/paginated')) {
      return route.fulfill(
        jsonResponse({
          data: {
            items: counties,
            pagination: { page: 1, totalPages: 1, totalItems: counties.length },
          },
        })
      );
    }
    if (url.endsWith('/api/v1/counties') || url.includes('/api/v1/counties?')) {
      return route.fulfill(jsonResponse(counties));
    }
    if (/\/api\/v1\/counties\/[\w-]+$/.test(url)) {
      const id = url.split('/').pop() as string;
      const item = counties.find((c: any) => c.id === id) || counties[0];
      return route.fulfill(jsonResponse(item));
    }

    // Fiscal summary — used by the debt page's "Where every KES 100" card.
    // Values mirror backend/seeding/real_data/fiscal_summary.json
    // (FY 2025/26: 1900 / 2910 × 100 ≈ 65.3).
    if (url.endsWith('/api/v1/fiscal/summary')) {
      const fyCurrent = {
        fiscal_year: 'FY 2025/26',
        appropriated_budget: 4190,
        total_revenue: 2910,
        tax_revenue: 2560,
        non_tax_revenue: 350,
        total_borrowing: 910,
        borrowing_pct_of_budget: 21.7,
        debt_service_cost: 1900,
        debt_service_per_shilling: 65.3,
        debt_ceiling: 10000,
        actual_debt: 12500,
        debt_ceiling_usage_pct: 125.0,
        development_spending: 672,
        recurrent_spending: 2850,
        county_allocation: 415,
      };
      return route.fulfill(
        jsonResponse({
          status: 'ok',
          data_source: 'mock',
          last_updated: '2026-04-19',
          source: 'FY 2025/26 fiscal summary (mock fixture)',
          current: fyCurrent,
          history: [fyCurrent],
          total_fiscal_years: 1,
        }),
      );
    }

    // Debt endpoints
    if (url.endsWith('/api/v1/debt/national')) {
      return route.fulfill(jsonResponse(debtOverview));
    }
    if (
      url.endsWith('/api/v1/debt/timeline') ||
      /\/api\/v1\/counties\/.+\/debt\/timeline/.test(url)
    ) {
      return route.fulfill(jsonResponse({ data: debtTimeline }));
    }
    if (url.endsWith('/api/v1/debt/breakdown') || /\/api\/v1\/debt\/breakdown\/.+/.test(url)) {
      return route.fulfill(jsonResponse({ data: debtBreakdown }));
    }
    if (url.endsWith('/api/v1/debt/top-loans')) {
      return route.fulfill(jsonResponse({ data: topLoans }));
    }

    // Default passthrough
    return route.continue();
  });
}

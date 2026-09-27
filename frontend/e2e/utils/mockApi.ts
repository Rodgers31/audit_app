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
    // Values are production's FY 2026/27 row (bare billions, no `unit`),
    // with the fiscal_framework object read from the Budget Summary's Annex
    // Table 2a, PDF p.63 (issue #237). Headline: 2315.9 / 2985.7 x 100 = 77.6.
    if (url.endsWith('/api/v1/fiscal/summary')) {
      const fyCurrent = {
        fiscal_year: 'FY 2026/27',
        appropriated_budget: 5485.7,
        total_revenue: 2985.7,
        tax_revenue: 2858.7,
        non_tax_revenue: 127.1,
        total_borrowing: 1111.8,
        borrowing_pct_of_budget: 23.2,
        debt_service_cost: 2315.9,
        debt_service_per_shilling: 77.6,
        debt_ceiling: null,
        actual_debt: null,
        debt_ceiling_usage_pct: null,
        development_spending: 749.0,
        recurrent_spending: 3538.7,
        county_allocation: 495.5,
        split_basis: 'treasury_fiscal_framework',
        fiscal_framework: {
          basis: 'treasury_fiscal_framework',
          identified_by: 'approved_budget',
          total_expenditure_billion: 4785.2,
          recurrent_billion: 3538.7,
          interest_payments_billion: 1254.2,
          development_billion: 749.0,
          county_transfers_billion: 495.5,
          county_equitable_share_billion: 420.0,
          contingency_billion: 2.0,
          total_revenue_incl_aia_billion: 3629.7,
          ordinary_revenue_billion: 2985.7,
          ministerial_aia_billion: 644.0,
          grants_billion: 43.6,
          fiscal_deficit_incl_grants_billion: 1111.8,
          total_financing_billion: 1111.8,
          net_foreign_financing_billion: 116.2,
          net_domestic_financing_billion: 995.7,
          adjustment_to_cash_basis_billion: 0.0,
          statistical_discrepancy_billion: 0.0,
          tax_revenue_billion: 2858.7,
          non_tax_revenue_billion: 127.1,
          source: {
            title: 'Budget Summary',
            publisher: 'The National Treasury',
            page: 'Annex Table 2a, PDF p.63',
            edition: 'Budget Summary for the FY 2026/27 Budget',
          },
        },
      };
      return route.fulfill(
        jsonResponse({
          status: 'ok',
          data_source: 'mock',
          last_updated: '2026-04-19',
          source: 'FY 2026/27 fiscal summary (mock fixture)',
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

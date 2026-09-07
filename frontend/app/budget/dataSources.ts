/**
 * Standing source credits for the budget page's "Sources" modal.
 *
 * Lifted out of BudgetPageClient so the claims themselves can be pinned by a
 * test without dragging the page's Supabase-backed provider tree into jsdom.
 * These strings are the page's only *standing* provenance claim — everything
 * else is captioned from the data — so what they say has to stay true as the
 * data underneath moves.
 */
export interface DataSourceCredit {
  section: string;
  authority: string;
  description: string;
  methodology?: string;
  url: string;
  urlLabel: string;
}

export const DATA_SOURCES: DataSourceCredit[] = [
  {
    section: 'Budget Execution by Sector',
    authority: 'Office of the Controller of Budget (OCOB)',
    description:
      'Sector-level expenditure vs. approved estimates from the Annual National Government Budget Implementation Review Reports (NG-BIRR).',
    methodology:
      'Approved Estimates from the Appropriation Act; Actual Expenditure from CoB exchequer-release reports to Parliament per Article 228(6) of the Constitution of Kenya.',
    url: 'https://cob.go.ke/publications/annual-national-government-budget-implementation-review-reports/',
    urlLabel: 'CoB Annual NG-BIRR Reports',
  },
  {
    section: 'Revenue by Source',
    authority: 'Kenya Revenue Authority (KRA)',
    description:
      'Five tax heads — PAYE, VAT, Corporation Tax, Excise Duty and Customs — are taken from KRA annual performance press releases for the year each release reports. The sixth card, Other Tax Revenue, is not a line in any release: it is a residual, the exchequer total less those five heads, and it absorbs withholding tax, capital gains, stamp duty, betting and digital-economy taxes.',
    methodology:
      'FY 2022/23 has no per-head release of its own. Its five heads are derived — back-computed from the growth rates the FY 2023/24 release states — so the earliest bar in each sparkline is an implied level, not a KRA figure. It is shown marked rather than withheld because the trend it carries is real. Figures on the cards are labelled individually wherever they are not published lines.',
    url: 'https://www.kra.go.ke/news-center/press-release',
    urlLabel: 'KRA Press Releases',
  },
  {
    section: 'County Budget Allocations',
    authority: 'Commission on Revenue Allocation (CRA)',
    description:
      'County-level budget allocations per the Division of Revenue Act and County Allocation of Revenue Act.',
    url: 'https://www.crakenya.org/county-allocations/',
    urlLabel: 'CRA County Allocations',
  },
  {
    section: 'Fiscal Summary & Borrowing',
    authority: 'National Treasury & Central Bank of Kenya',
    description:
      'High-level fiscal aggregates (revenue, expenditure, borrowing, debt service) from the Budget Policy Statement and Controller of Budget quarterly reports.',
    url: 'https://www.treasury.go.ke/budget-policy-statement/',
    urlLabel: 'National Treasury BPS',
  },
];

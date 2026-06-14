/**
 * Plain-English glossary of government-finance terms.
 *
 * Each entry pairs a short headline definition with a longer explanation
 * written for a curious citizen (not an accountant), real examples that
 * ground the concept in Kenyan life, and an optional pointer into the
 * Constitution of Kenya so readers can jump straight to the source.
 *
 * Edit this file directly to add, update, or remove terms.
 */

import type { CivicFigureKey } from '@/lib/api/civic';
import {
  AlertTriangle,
  BookOpen,
  Building,
  Calculator,
  DollarSign,
  Landmark,
  type LucideIcon,
  ScrollText,
  Scale,
  TrendingUp,
  Users,
} from 'lucide-react';

export type GlossaryCategoryId =
  | 'finance'
  | 'planning'
  | 'spending'
  | 'accountability'
  | 'economy'
  | 'devolution';

export interface RelatedArticleLink {
  chapter: number;
  article: number;
  label: string;
}

/**
 * An example whose magnitude is pulled live from the API (`/learn/civic-figures`)
 * so it never goes stale, instead of being a hardcoded literal.
 *
 * The glossary renders `template` with the live figure substituted in:
 *   `{value}`  → formatted magnitude, e.g. "KES 4.19 trillion"
 *   `{period}` → the fiscal year or data year it refers to, e.g. "FY2025/26"
 *
 * If the figure was never seeded or the API is unavailable, `fallback` is
 * shown instead — which MUST be an honest, dated historical fact, never a
 * fabricated current number (DESIGN §1: last-known-good, dated).
 */
export interface LiveExample {
  figure: CivicFigureKey;
  template: string;
  fallback: string;
}

/** A glossary example is either static prose or a live, self-updating figure. */
export type GlossaryExample = string | LiveExample;

export interface GlossaryTerm {
  id: string;
  term: string;
  /** Optional shorthand (e.g. "GDP", "CoB"). */
  abbreviation?: string;
  category: GlossaryCategoryId;
  icon: LucideIcon;
  shortDef: string;
  longDef: string;
  examples: GlossaryExample[];
  /** Point readers to the constitutional article that anchors this term. */
  relatedArticle?: RelatedArticleLink;
}

export interface GlossaryCategoryMeta {
  id: GlossaryCategoryId | 'all';
  label: string;
  blurb: string;
}

export const GLOSSARY_CATEGORIES: GlossaryCategoryMeta[] = [
  {
    id: 'all',
    label: 'All terms',
    blurb: 'Every term on this site, one page.',
  },
  {
    id: 'finance',
    label: 'Finance',
    blurb: 'How government collects, borrows, and keeps track of the money.',
  },
  {
    id: 'planning',
    label: 'Planning',
    blurb: 'The documents that decide where shillings go before they are spent.',
  },
  {
    id: 'spending',
    label: 'Spending',
    blurb: 'What the money actually pays for once it leaves the Treasury.',
  },
  {
    id: 'accountability',
    label: 'Accountability',
    blurb: 'The checks that prove public money was spent as promised.',
  },
  {
    id: 'economy',
    label: 'Economy',
    blurb: 'The bigger picture numbers that budgets sit inside.',
  },
  {
    id: 'devolution',
    label: 'Devolution',
    blurb: 'Language specific to the 47 counties.',
  },
];

export const glossaryTerms: GlossaryTerm[] = [
  {
    id: 'budget',
    term: 'Budget',
    category: 'planning',
    icon: Calculator,
    shortDef: 'A plan for how government will spend money over a year.',
    longDef:
      "A budget is the country's spending plan for the year ahead. It lists how much government expects to collect (from taxes, fees, and loans) and how it plans to spend it on schools, hospitals, roads, security, and everything else.",
    examples: [
      {
        figure: 'national_budget',
        template: "Kenya's {period} national budget was set at about KES {value}.",
        fallback:
          "Kenya's FY2024/25 national budget was printed at approximately KES 3.9 trillion.",
      },
      'Your county budget funds local hospitals, markets, and Early Childhood schools.',
      'Budgets must be tabled in Parliament at least two months before the financial year begins.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 221,
      label: 'Article 221 — Budget estimates and the Appropriation Bill',
    },
  },
  {
    id: 'revenue',
    term: 'Government Revenue',
    category: 'finance',
    icon: DollarSign,
    shortDef: 'Every shilling government takes in — taxes, fees, and grants.',
    longDef:
      'Revenue is the income side of the budget. Most of it comes from taxes you already pay (PAYE, VAT, excise, fuel levy), but it also includes licences, fines, court fees, dividends from state-owned enterprises, and development aid.',
    examples: [
      'Income tax deducted from your payslip each month.',
      'The 16% VAT added to your shopping receipt.',
      'Licence fees from matatu SACCOs and boda riders.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 209,
      label: 'Article 209 — Power to impose taxes and charges',
    },
  },
  {
    id: 'taxation',
    term: 'Taxation',
    category: 'finance',
    icon: Users,
    shortDef: 'The legal system by which citizens and firms fund the state.',
    longDef:
      'Taxes are the main way government raises money to pay for shared services. Kenya uses a mix of taxes — on income, spending, business profits, and specific goods — and the rules sit in the Income Tax Act, VAT Act, and the Finance Act passed each year.',
    examples: [
      'PAYE: Pay-As-You-Earn deducted from your salary.',
      'VAT added to the price of most goods and services.',
      'Corporate tax charged on business profits at 30% (15% for listed firms in year one).',
    ],
    relatedArticle: {
      chapter: 12,
      article: 210,
      label: 'Article 210 — Imposition of tax',
    },
  },
  {
    id: 'expenditure',
    term: 'Government Expenditure',
    category: 'spending',
    icon: Building,
    shortDef: 'Money the government actually pays out.',
    longDef:
      'Expenditure is the outgoing side of the budget — salaries, medicines, textbooks, road works, debt interest, and every other payment government makes. It splits into recurrent (running costs) and development (projects that create new assets).',
    examples: [
      'Teacher, nurse, and police-officer payrolls.',
      'Equipment and drugs for public hospitals and dispensaries.',
      'Road, water, and ICT infrastructure projects under the development budget.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 225,
      label: 'Article 225 — Financial control',
    },
  },
  {
    id: 'deficit',
    term: 'Budget Deficit',
    category: 'finance',
    icon: AlertTriangle,
    shortDef: 'When spending overshoots revenue and the gap is covered by borrowing.',
    longDef:
      'A deficit is the shortfall between what government collects and what it spends. The difference has to come from somewhere — usually loans at home (Treasury bills and bonds) or abroad (multilateral lenders, Eurobonds), which all add to public debt.',
    examples: [
      'Collecting KES 2.0T in taxes but spending KES 2.5T leaves a KES 500B deficit.',
      'The deficit is published in the annual Budget Policy Statement as a percentage of GDP.',
      'Persistently large deficits push up the debt-service bill in future budgets.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 211,
      label: 'Article 211 — Borrowing by national government',
    },
  },
  {
    id: 'debt',
    term: 'National Debt',
    category: 'finance',
    icon: TrendingUp,
    shortDef: 'Money the state has borrowed and must pay back with interest.',
    longDef:
      'National (or public) debt is the running total of money government owes — to domestic lenders (holders of T-bills and bonds) and foreign lenders (World Bank, IMF, China Exim, Eurobond investors). Parliament sets the ceiling and the Auditor-General confirms the figure.',
    examples: [
      {
        figure: 'public_debt',
        template: "Kenya's public debt stood at about KES {value} (as of {period}).",
        fallback: "By mid-2024, Kenya's public debt had surpassed KES 10 trillion.",
      },
      'Loans borrowed to build the Standard Gauge Railway sit inside this total.',
      'Debt-service payments are the first legal charge on the Consolidated Fund.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 214,
      label: 'Article 214 — Public debt',
    },
  },
  {
    id: 'audit',
    term: 'Government Audit',
    category: 'accountability',
    icon: ScrollText,
    shortDef: 'An independent check that public money was spent lawfully.',
    longDef:
      'An audit is a formal review of how a public entity raised and used its money. The Auditor-General audits every national and county entity every year and reports to Parliament — so MPs (and you) can see whether funds were spent as authorised.',
    examples: [
      'The Auditor-General verifies that education funds actually built schools.',
      'Each county receives its own audit opinion — unqualified, qualified, adverse, or disclaimer.',
      'Reports are tabled in Parliament and published on the OAG website.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 229,
      label: 'Article 229 — Auditor-General',
    },
  },
  {
    id: 'controller-of-budget',
    term: 'Controller of Budget',
    abbreviation: 'CoB',
    category: 'accountability',
    icon: Scale,
    shortDef: 'The officer who approves every withdrawal from public funds.',
    longDef:
      "No shilling leaves the Consolidated Fund or a County Revenue Fund without the Controller of Budget authorising it. The CoB publishes quarterly implementation reports showing how much of the approved budget has actually been spent — line by line, ministry by ministry.",
    examples: [
      'Quarterly Budget Implementation Review Reports for national and county governments.',
      'Flags withdrawals that breach authorised limits before the money moves.',
      'Publicly posts a dashboard of revenue vs. expenditure each quarter.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 228,
      label: 'Article 228 — Controller of Budget',
    },
  },
  {
    id: 'consolidated-fund',
    term: 'Consolidated Fund',
    category: 'finance',
    icon: Landmark,
    shortDef: 'The single national bank account every shilling of revenue flows into.',
    longDef:
      'All money raised or received by national government — taxes, loans, grants — must first enter the Consolidated Fund at the Central Bank. Payments leave only with parliamentary authority and the Controller of Budget\u2019s signature.',
    examples: [
      'PAYE deducted this month lands in the Consolidated Fund tomorrow.',
      'Debt-service payments and judges\u2019 salaries are permanent charges on the Fund.',
      'County equitable shares are transferred out of the Fund to County Revenue Funds.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 206,
      label: 'Article 206 — Consolidated Fund and other public funds',
    },
  },
  {
    id: 'equitable-share',
    term: 'Equitable Share',
    category: 'devolution',
    icon: Scale,
    shortDef: 'The slice of national revenue that is automatically sent to counties.',
    longDef:
      'The Constitution guarantees counties at least 15% of the most recently audited national revenue. The exact split between counties is decided by a formula from the Commission on Revenue Allocation and enacted through the annual Division of Revenue Act.',
    examples: [
      {
        figure: 'equitable_share',
        template:
          'For {period}, counties were allocated about KES {value} as their equitable share.',
        fallback:
          'For FY2024/25, counties were allocated around KES 400B as their equitable share.',
      },
      'The formula weights population, poverty, health, land area, and fiscal effort.',
      'Equitable-share transfers must reach a county within five days of release.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 202,
      label: 'Article 202 — Equitable sharing of national revenue',
    },
  },
  {
    id: 'gdp',
    term: 'Gross Domestic Product',
    abbreviation: 'GDP',
    category: 'economy',
    icon: TrendingUp,
    shortDef: 'The total value of everything produced in the country in a year.',
    longDef:
      "GDP adds up the market value of all final goods and services made in Kenya over a year — from tea at Kericho to code in Nairobi. It's the baseline most budget ratios (debt, deficit, tax) are measured against.",
    examples: [
      {
        figure: 'nominal_gdp',
        template:
          "Kenya's nominal GDP was about KES {value} in {period} (World Bank / KNBS).",
        fallback:
          "Kenya's nominal GDP was approximately KES 15.0 trillion in 2023 (World Bank / KNBS).",
      },
      'Agriculture still contributes roughly a fifth of GDP.',
      'A debt-to-GDP ratio of 70% means debt is 70% the size of annual output.',
    ],
  },
  {
    id: 'procurement',
    term: 'Public Procurement',
    category: 'accountability',
    icon: BookOpen,
    shortDef: 'The rules government must follow when buying goods or services.',
    longDef:
      'When a ministry, agency, or county buys anything — pencils, ambulances, bridges — it has to follow the Public Procurement and Asset Disposal Act: open tendering, transparent evaluation, published awards. These rules are what make audits possible later.',
    examples: [
      'Tenders above KES 5M must be advertised publicly.',
      'Contract awards and signed contracts are uploaded to the PPIP portal.',
      'Breaches trigger investigations by EACC and sanctions by PPRA.',
    ],
    relatedArticle: {
      chapter: 12,
      article: 227,
      label: 'Article 227 — Procurement of public goods and services',
    },
  },
];

/** Counts per category id, computed once. */
export function getCategoryCounts(): Record<GlossaryCategoryId | 'all', number> {
  const counts = { all: glossaryTerms.length } as Record<GlossaryCategoryId | 'all', number>;
  for (const cat of GLOSSARY_CATEGORIES) {
    if (cat.id === 'all') continue;
    counts[cat.id] = glossaryTerms.filter((t) => t.category === cat.id).length;
  }
  return counts;
}

/** Searchable/plain text for an example (the dated fallback for live ones). */
export function exampleText(ex: GlossaryExample): string {
  return typeof ex === 'string' ? ex : ex.fallback;
}

/** Case-insensitive search across term, abbreviation, short, and long definitions. */
export function filterTerms(
  terms: GlossaryTerm[],
  search: string,
  category: GlossaryCategoryId | 'all'
): GlossaryTerm[] {
  const q = search.trim().toLowerCase();
  return terms.filter((t) => {
    if (category !== 'all' && t.category !== category) return false;
    if (!q) return true;
    const haystack = [
      t.term,
      t.abbreviation ?? '',
      t.shortDef,
      t.longDef,
      t.examples.map(exampleText).join(' '),
    ]
      .join(' ')
      .toLowerCase();
    return haystack.includes(q);
  });
}

/** Bucket filtered terms back into their categories for grouped rendering. */
export function groupByCategory(
  terms: GlossaryTerm[]
): { category: GlossaryCategoryMeta; terms: GlossaryTerm[] }[] {
  return GLOSSARY_CATEGORIES.filter((c) => c.id !== 'all')
    .map((category) => ({
      category,
      terms: terms.filter((t) => t.category === category.id),
    }))
    .filter((g) => g.terms.length > 0);
}

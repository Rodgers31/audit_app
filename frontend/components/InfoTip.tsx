'use client';

import { Info } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

/**
 * InfoTip — a small (i) icon that shows a plain-language explanation on hover/tap.
 *
 * Usage:
 *   <h3>Debt-to-GDP Ratio <InfoTip term="debt-to-gdp" /></h3>
 *   <th>Eligible <InfoTip term="eligible-bills" size={12} /></th>
 *
 * All explanations are co-located in GLOSSARY below so they stay consistent
 * across the app and are easy to update in one place.
 */

const GLOSSARY: Record<string, { title: string; body: string }> = {
  // ── Debt terms ────────────────────────────────────────
  'debt-to-gdp': {
    title: 'Debt-to-GDP Ratio',
    body: 'This shows the country\'s total debt as a percentage of its annual economic output (GDP). A higher ratio means the country owes more relative to what it earns. The IMF considers 55% a warning threshold for countries like Kenya.',
  },
  'debt-service': {
    title: 'Debt Service Cost',
    body: 'The amount the government pays each year just to service its debts — this includes interest payments and loan repayments. It does not include the original loan amount (principal). Higher debt service means less money available for public services.',
  },
  'debt-service-to-revenue': {
    title: 'Debt Service to Revenue',
    body: 'For every shilling the government collects in revenue, this shows how much goes to paying off debts. For example, 45% means 45 cents of every shilling goes to debt payments. Above 30% is considered concerning.',
  },
  'external-debt': {
    title: 'External Debt',
    body: 'Money the government owes to foreign lenders — including international organizations (like the World Bank and IMF), other countries (bilateral loans), and foreign banks or bondholders. This debt is usually in foreign currencies like USD, EUR, or JPY.',
  },
  'domestic-debt': {
    title: 'Domestic Debt',
    body: 'Money the government owes to lenders within Kenya — mainly through Treasury Bonds (long-term) and Treasury Bills (short-term) bought by local banks, pension funds, and investors. This debt is in Kenyan Shillings.',
  },
  'external-debt-share': {
    title: 'External Debt Share',
    body: 'What percentage of total debt is owed to foreign lenders. A high external share (above 50%) exposes the country to currency risk — if the shilling weakens, these debts become more expensive to repay.',
  },
  'debt-sustainability': {
    title: 'Debt Sustainability',
    body: 'An assessment of whether the government can continue to pay its debts without defaulting or needing extreme measures. It looks at debt growth, revenue collection, and economic output to determine if the debt burden is manageable.',
  },
  'principal': {
    title: 'Principal',
    body: 'The original amount borrowed, before any interest is added. For example, if the government borrows KES 100 billion, the principal is KES 100 billion.',
  },
  'outstanding': {
    title: 'Outstanding Balance',
    body: 'How much of a loan is still unpaid. This includes the remaining principal that hasn\'t been repaid yet. It decreases as the government makes payments.',
  },
  'multilateral': {
    title: 'Multilateral Lender',
    body: 'International organizations funded by multiple countries, like the World Bank, IMF, or African Development Bank. They typically offer lower interest rates and longer repayment periods than commercial lenders.',
  },
  'bilateral': {
    title: 'Bilateral Lender',
    body: 'Loans from one country to another — for example, China, Japan, or France lending directly to Kenya. Terms vary by country, and these loans often come with conditions or are tied to specific projects.',
  },
  'commercial': {
    title: 'Commercial Lender',
    body: 'Loans from private banks and financial markets, including Eurobonds (bonds sold to international investors). These carry higher interest rates but give the government more flexibility in how the money is used.',
  },
  'treasury-bonds': {
    title: 'Treasury Bonds',
    body: 'Long-term government IOUs (2–30 years) sold to investors. The government pays interest twice a year and returns the full amount at maturity. They\'re the main way Kenya borrows domestically.',
  },
  'treasury-bills': {
    title: 'Treasury Bills',
    body: 'Short-term government IOUs (91, 182, or 364 days). Sold at a discount — for example, you pay KES 95,000 for a bill that pays KES 100,000 at maturity. The government uses these for short-term cash management.',
  },
  'cbk-advance': {
    title: 'CBK Advance',
    body: 'Short-term borrowing directly from the Central Bank of Kenya. This is essentially the government\'s overdraft facility — used when cash flow is tight before tax revenues come in.',
  },

  // ── Pending bills terms ───────────────────────────────
  'eligible-bills': {
    title: 'Eligible Pending Bills',
    body: 'Bills that have been verified and approved for payment — the goods or services were delivered, the documentation is complete, and the procurement process was followed correctly. The government is legally obligated to pay these.',
  },
  'ineligible-bills': {
    title: 'Ineligible Pending Bills',
    body: 'Bills that failed verification checks. They may have incomplete paperwork, disputed amounts, expired contracts, or procurement irregularities. These cannot be paid until the issues are resolved.',
  },
  'pending-bills': {
    title: 'Pending Bills',
    body: 'Unpaid invoices that the government owes to suppliers, contractors, and staff. These are real obligations — the work was done or goods delivered, but the government hasn\'t paid yet. They carry no interest but damage supplier trust and economic activity.',
  },
  'aging-analysis': {
    title: 'Aging Analysis',
    body: 'Shows how long pending bills have been waiting for payment. Bills in the "180d+" bucket have been unpaid for over 6 months. Older bills indicate worse cash flow management and greater supplier hardship.',
  },

  // ── Budget & fiscal terms ─────────────────────────────
  'budget-execution': {
    title: 'Budget Execution Rate',
    body: 'The percentage of an approved budget that was actually spent. For example, if a county was allocated KES 10 billion but only spent KES 7 billion, its execution rate is 70%. Low rates may indicate poor planning or corruption.',
  },
  'development-spending': {
    title: 'Development Spending',
    body: 'Money spent on building things that last — roads, hospitals, schools, water systems, etc. Under Kenya\'s PFM Act, borrowed money should only fund development, not day-to-day operations like salaries.',
  },
  'recurrent-spending': {
    title: 'Recurrent Spending',
    body: 'Day-to-day government running costs — salaries, office rent, fuel, supplies, and other operational expenses. These expenses repeat every year, unlike development projects which are one-time investments.',
  },
  'appropriated-budget': {
    title: 'Appropriated Budget',
    body: 'The total amount of money that Parliament has approved for the government to spend in a fiscal year. This is the legal spending limit — the government cannot spend more than this without additional approval.',
  },
  'equitable-share': {
    title: 'Equitable Share',
    body: 'The portion of national revenue that the Constitution requires to be shared with county governments — at least 15% of the last audited national revenue. This is each county\'s main source of funding from the national government.',
  },
  'own-source-revenue': {
    title: 'Own-Source Revenue',
    body: 'Money that a county raises on its own through local taxes, fees, charges, and permits — like property rates, parking fees, market levies, and business permits. This supplements the equitable share from the national government.',
  },
  'fiscal-year': {
    title: 'Fiscal Year (FY)',
    body: 'Kenya\'s government financial year runs from July 1 to June 30. So "FY2024/25" means the period from July 2024 to June 2025. This is different from the calendar year.',
  },
  'borrowing-vs-budget': {
    title: 'Borrowing as % of Budget',
    body: 'Shows how much of the government\'s total spending is funded by loans rather than revenue. A high percentage means the government is heavily reliant on borrowing to fund its operations.',
  },

  // ── Audit terms ───────────────────────────────────────
  'audit-clean': {
    title: 'Clean Audit Opinion',
    body: 'The best possible result — the Auditor General found that the financial statements are accurate and money was spent according to the law. Think of it as a clean bill of health for public finances.',
  },
  'audit-qualified': {
    title: 'Qualified Audit Opinion',
    body: 'The Auditor General found some problems — certain expenses couldn\'t be verified or some rules weren\'t followed — but the issues aren\'t severe enough to reject the entire financial report.',
  },
  'audit-adverse': {
    title: 'Adverse Audit Opinion',
    body: 'Serious problems found — the financial statements are materially misstated or unreliable. This means there are significant irregularities in how public money was managed.',
  },
  'audit-disclaimer': {
    title: 'Disclaimer of Opinion',
    body: 'The worst outcome — the Auditor General couldn\'t even form an opinion because records were so poor or access was restricted. This is a major red flag for accountability.',
  },
  'financial-health': {
    title: 'Financial Health Score',
    body: 'A composite score (0–100) that combines budget execution, audit results, debt levels, and revenue collection into a single grade (A through D-). Higher scores mean better financial management.',
  },

  // ── Government structure ──────────────────────────────
  'mda': {
    title: 'MDA',
    body: 'Stands for Ministry, Department, and Agency — the organizational units of the national government. Examples include the Ministry of Health, Kenya Revenue Authority, or the National Police Service.',
  },
  'cob': {
    title: 'Controller of Budget (COB)',
    body: 'An independent office that oversees government spending. The COB must approve every withdrawal from public funds and publishes quarterly reports on how budgets are being implemented.',
  },
  'oag': {
    title: 'Office of the Auditor General (OAG)',
    body: 'The independent office that audits all national and county government accounts. The Auditor General checks whether public money was spent legally and efficiently, and reports to Parliament.',
  },
  'exchequer': {
    title: 'Exchequer',
    body: 'The government\'s main bank account at the Central Bank of Kenya, where tax revenues are deposited and from which government payments are made. When money is "released from the Exchequer," it means funds have been disbursed.',
  },
  'pfm-act': {
    title: 'PFM Act',
    body: 'The Public Finance Management Act (2012) — Kenya\'s main law governing how public money is raised, spent, and accounted for. It sets rules for budgeting, borrowing, and financial reporting at both national and county levels.',
  },

  // ── Sustainability benchmarks ─────────────────────────
  'imf-threshold': {
    title: 'IMF Debt Threshold',
    body: 'The International Monetary Fund recommends that low-income countries like Kenya keep their debt-to-GDP ratio below 55%. Beyond this, a country faces elevated risk of debt distress — difficulty meeting its debt obligations.',
  },
  'eac-benchmark': {
    title: 'EAC Convergence Criteria',
    body: 'The East African Community (Kenya, Uganda, Tanzania, Rwanda, Burundi, DRC, South Sudan) agreed that member states should keep debt-to-GDP below 50% as part of their economic integration targets.',
  },
};

interface InfoTipProps {
  /** Key from the GLOSSARY above */
  term: string;
  /** Icon size in pixels (default 14) */
  size?: number;
  /** Extra CSS classes for the icon wrapper */
  className?: string;
}

export default function InfoTip({ term, size = 14, className = '' }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const entry = GLOSSARY[term];

  const clearClose = () => {
    if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null; }
  };
  const scheduleClose = () => {
    clearClose();
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  const show = useCallback(() => {
    clearClose();
    if (btnRef.current) {
      setRect(btnRef.current.getBoundingClientRect());
    }
    setOpen(true);
  }, []);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        btnRef.current?.contains(e.target as Node) ||
        tooltipRef.current?.contains(e.target as Node)
      ) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  if (!entry) return null;

  // Compute tooltip position: above the button, centered horizontally.
  // If too close to top of viewport, show below instead.
  const getStyle = (): React.CSSProperties => {
    if (!rect) return { display: 'none' };
    const pad = 8;
    const above = rect.top > 200; // enough room above?
    return {
      position: 'fixed',
      left: Math.max(pad, Math.min(rect.left + rect.width / 2 - 144, window.innerWidth - 288 - pad)),
      ...(above
        ? { top: rect.top - pad }
        : { top: rect.bottom + pad }),
      transform: above ? 'translateY(-100%)' : 'translateY(0)',
      zIndex: 9999,
      opacity: 1,
      pointerEvents: 'auto' as const,
    };
  };

  return (
    <span className={`inline-flex items-center ${className}`}>
      <button
        ref={btnRef}
        type='button'
        aria-label={`What is ${entry.title}?`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (open) {
            setOpen(false);
          } else {
            show();
          }
        }}
        onMouseEnter={() => { if (!open) show(); }}
        onMouseLeave={scheduleClose}
        onFocus={show}
        onBlur={scheduleClose}
        className='ml-1 p-0.5 text-gray-400 hover:text-blue-500 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-300 rounded-full cursor-pointer'
      >
        <Info size={size} />
      </button>
      {open && rect && typeof document !== 'undefined' && createPortal(
        <div
          ref={tooltipRef}
          role='tooltip'
          onMouseEnter={clearClose}
          onMouseLeave={scheduleClose}
          style={getStyle()}
          className='w-72 bg-white border border-gray-200 rounded-xl shadow-xl p-3.5 text-left pointer-events-auto animate-fade-in'
        >
          <div className='text-xs font-semibold text-gray-800 mb-1.5'>{entry.title}</div>
          <div className='text-[11px] text-gray-600 leading-relaxed'>{entry.body}</div>
        </div>,
        document.body
      )}
    </span>
  );
}

/** Re-export glossary keys for discoverability */
export type GlossaryTerm = keyof typeof GLOSSARY;

'use client';

import { Info } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';

/**
 * InfoTip — a small (i) icon that shows a plain-language explanation on hover/tap.
 *
 * Usage:
 *   <h3>Debt-to-GDP Ratio <InfoTip term="debt-to-gdp" /></h3>
 *   <th>Eligible <InfoTip term="eligible-bills" size={12} /></th>
 *
 * Unused English fallback explanations live in GLOSSARY. Active explanations use
 * keys from the shared language catalog.
 */

const GLOSSARY: Record<string, { title: string; body: string }> = {
  // ── Debt terms ────────────────────────────────────────
  'debt-service': {
    title: 'Debt Service Cost',
    body: 'The amount the government pays each year just to service its debts — this includes interest payments and loan repayments. It does not include the original loan amount (principal). Higher debt service means less money available for public services.',
  },
  'debt-service-to-revenue': {
    title: 'Debt Service to Revenue',
    body: 'For every shilling the government collects in revenue, this shows how much goes to paying off debts. For example, 45% means 45 cents of every shilling goes to debt payments. Above 30% is considered concerning.',
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
  'aging-analysis': {
    title: 'Aging Analysis',
    body: 'Shows how long pending bills have been waiting for payment. Bills in the "180d+" bucket have been unpaid for over 6 months. Older bills indicate worse cash flow management and greater supplier hardship.',
  },

  // ── Budget & fiscal terms ─────────────────────────────
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
};

const TRANSLATED_GLOSSARY: Record<string, { title: TranslationKey; body: TranslationKey }> = {
  'debt-to-gdp': { title: 'glossary.debt_to_gdp.title', body: 'glossary.debt_to_gdp.body' },
  'external-debt': { title: 'glossary.external_debt.title', body: 'glossary.external_debt.body' },
  'domestic-debt': { title: 'glossary.domestic_debt.title', body: 'glossary.domestic_debt.body' },
  'pending-bills': { title: 'glossary.pending_bills.title', body: 'glossary.pending_bills.body' },
  'budget-execution': { title: 'glossary.budget_execution.title', body: 'glossary.budget_execution.body' },
  'audit-clean': { title: 'glossary.audit_clean.title', body: 'glossary.audit_clean.body' },
  'outstanding': { title: 'glossary.outstanding.title', body: 'glossary.outstanding.body' },
  'multilateral': { title: 'glossary.multilateral.title', body: 'glossary.multilateral.body' },
  'bilateral': { title: 'glossary.bilateral.title', body: 'glossary.bilateral.body' },
  'commercial': { title: 'glossary.commercial.title', body: 'glossary.commercial.body' },
  'development-spending': { title: 'glossary.development_spending.title', body: 'glossary.development_spending.body' },
  'recurrent-spending': { title: 'glossary.recurrent_spending.title', body: 'glossary.recurrent_spending.body' },

  'financial-health': {
    title: 'county.healthmodal.title',
    body: 'glossary.financial_health.body',
  },
};

interface InfoTipProps {
  /** Key from the English or translated glossary above */
  term: string;
  /** Icon size in pixels (default 14) */
  size?: number;
  /** Extra CSS classes for the icon wrapper */
  className?: string;
}

export default function InfoTip({ term, size = 14, className = '' }: InfoTipProps) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const translatedKeys = Object.prototype.hasOwnProperty.call(TRANSLATED_GLOSSARY, term)
    ? TRANSLATED_GLOSSARY[term]
    : undefined;
  const entry = translatedKeys
    ? { title: t(translatedKeys.title), body: t(translatedKeys.body) }
    : Object.prototype.hasOwnProperty.call(GLOSSARY, term) ? GLOSSARY[term] : undefined;

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

  // Unknown terms have no explanation to offer; omit the optional help control.
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
        aria-label={translatedKeys
          ? t('glossary.info_label').replace('{title}', entry.title)
          : `What is ${entry.title}?`}
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
        className='tap-24 ml-1 p-0.5 text-gray-400 dark:text-neutral-muted/80 hover:text-blue-500 transition-colors rounded-full cursor-pointer'
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
          className='w-[min(18rem,calc(100vw-1rem))] bg-white dark:bg-surface-base border border-gray-200 dark:border-neutral-border rounded-xl shadow-xl p-3.5 text-left pointer-events-auto animate-fade-in'
        >
          <div className='text-xs font-semibold text-gray-800 dark:text-neutral-text mb-1.5'>{entry.title}</div>
          <div className='text-[11px] text-gray-600 dark:text-neutral-muted leading-relaxed'>{entry.body}</div>
        </div>,
        document.body
      )}
    </span>
  );
}

/** Re-export glossary keys for discoverability */
export type GlossaryTerm = keyof typeof GLOSSARY | keyof typeof TRANSLATED_GLOSSARY;

'use client';

/**
 * Budget & Spending — redesigned page
 *
 * The page is composed from domain-specific components under
 * `/components/budget`, each of which owns one clear chapter of the story:
 *
 *   1. BudgetFlowHero              — "where money comes from / where it goes"
 *   2. FiscalTrendStrip            — multi-year sparklines (is the gap widening?)
 *   3. SpendDonut                  — concentric donut: macro × sectors
 *   4. RevenueMix                  — KRA revenue streams with YoY deltas
 *   5. ExecutionAuditLens          — sectors ranked by unspent (the audit lens)
 *   6. CountyUtilizationStrip      — best / worst absorbers + link to /counties
 *   7. EconomicContextStrip        — GDP ratios, inflation, per-capita
 *   8. BudgetSourceReconciliation  — sources and known caveats
 *
 * The previous version of this file was ~1,620 lines of inline chart JSX.
 * Breaking it into chapters makes each section independently auditable
 * and mirrors the narrative arc we adopted on the National Debt page.
 */

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import DataIntegrityBanner from '@/components/DataIntegrityBanner';
import PageShell from '@/components/layout/PageShell';
import { PageSkeleton } from '@/components/ui/Skeleton';
import PDFExportButton from '@/components/PDFExportButton';
import BudgetFlowHero, {
  type FlowHeroInput,
} from '@/components/budget/BudgetFlowHero';
import BudgetSourceReconciliation, {
  type BudgetMeta,
} from '@/components/budget/BudgetSourceReconciliation';
import CountyUtilizationStrip from '@/components/budget/CountyUtilizationStrip';
import EconomicContextStrip from '@/components/budget/EconomicContextStrip';
import ExecutionAuditLens from '@/components/budget/ExecutionAuditLens';
import FiscalTrendStrip from '@/components/budget/FiscalTrendStrip';
import FiscalYearPicker from '@/components/budget/FiscalYearPicker';
import RevenueMix from '@/components/budget/RevenueMix';
import SpendDonut from '@/components/budget/SpendDonut';
import { useBudgetEnhanced, useBudgetOverview } from '@/lib/react-query';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import { AlertTriangle, ExternalLink, Info, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/* ═══════════════════════════════════════════════════════
   Data sources panel (explanation modal)
   ═══════════════════════════════════════════════════════ */

const DATA_SOURCES = [
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
      'Tax revenue breakdown (PAYE, VAT, Corporation Tax, Excise Duty, Customs) from KRA annual performance press releases.',
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

function DataSourcesModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className='fixed inset-0 z-[200] flex items-center justify-center p-4'
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/40 backdrop-blur-sm'
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', duration: 0.4 }}
        className='relative z-10 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-2xl bg-white dark:bg-surface-base shadow-2xl border border-gray-100 dark:border-neutral-border'>
        <div className='sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-neutral-border bg-white/95 backdrop-blur-sm rounded-t-2xl'>
          <div>
            <h3 className='text-lg font-bold text-gray-900 dark:text-neutral-text'>Data Sources</h3>
            <p className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
              Official resources used on this page
            </p>
          </div>
          <button
            onClick={onClose}
            className='p-1.5 rounded-lg hover:bg-gray-100 dark:bg-surface-elevated transition-colors text-gray-400 dark:text-neutral-muted/80 hover:text-gray-600 dark:text-neutral-muted'
            aria-label='Close'>
            <X size={18} />
          </button>
        </div>
        <div className='px-6 py-4 space-y-5'>
          {DATA_SOURCES.map((src) => (
            <div key={src.section} className='group'>
              <h4 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-1'>{src.section}</h4>
              <p className='text-xs text-gray-500 dark:text-neutral-muted/80 leading-relaxed mb-1.5'>
                {src.description}
              </p>
              {src.methodology && (
                <p className='text-[11px] text-gray-400 dark:text-neutral-muted/80 italic mb-1.5'>
                  Methodology: {src.methodology}
                </p>
              )}
              <div className='flex items-center gap-2 text-xs'>
                <span className='inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gov-forest/10 text-gov-forest dark:text-emerald-100 font-medium'>
                  {src.authority}
                </span>
                <a
                  href={src.url}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='inline-flex items-center gap-1 text-gov-forest dark:text-emerald-100 hover:underline'>
                  {src.urlLabel}
                  <ExternalLink size={11} />
                </a>
              </div>
              <div className='mt-3 border-b border-gray-100 dark:border-neutral-border group-last:border-0' />
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   Main page
   ═══════════════════════════════════════════════════════ */

export default function BudgetSpendingPage() {
  const {
    data: overview,
    isLoading: loadingOverview,
    isError: errorOverview,
    refetch: refetchOverview,
  } = useBudgetOverview();
  const {
    data: fiscal,
    isLoading: loadingFiscal,
    isError: errorFiscal,
    refetch: refetchFiscal,
  } = useFiscalSummary();
  const { data: enhanced } = useBudgetEnhanced();

  const [sourcesOpen, setSourcesOpen] = useState(false);
  const closeSourcesModal = useCallback(() => setSourcesOpen(false), []);

  const isLoading = loadingOverview || loadingFiscal;
  const isError = errorOverview || errorFiscal;

  /* ── Derived data ── */
  // Prefer the fiscal endpoint's history — it carries debt_service_per_shilling
  // (the Treasury APDMR ratio) which the budget/overview endpoint doesn't surface.
  const fiscalHistoryRaw = fiscal?.history ?? overview?.fiscal_history ?? [];
  const fiscalHistory = useMemo(
    () =>
      fiscalHistoryRaw.filter((f: any) =>
        [
          f.appropriated_budget,
          f.total_revenue,
          f.total_borrowing,
          f.debt_service_cost,
          f.county_allocation,
        ].some((v) => v != null && v > 0)
      ),
    [fiscalHistoryRaw]
  );

  // Row for the current fiscal year — comes from fiscal.current.
  const currentFiscal: FlowHeroInput | null = useMemo(() => {
    const cur = fiscal?.current as Record<string, any> | undefined;
    if (cur && cur.fiscal_year) return cur as FlowHeroInput;
    return fiscalHistory[fiscalHistory.length - 1] ?? null;
  }, [fiscal, fiscalHistory]);

  // Unique list of fiscal years available for the picker — most recent first.
  const availableYears = useMemo(() => {
    const byYear = new Map<string, { fiscal_year: string; is_current: boolean }>();
    for (const row of fiscalHistory) {
      if (!row?.fiscal_year) continue;
      byYear.set(row.fiscal_year, {
        fiscal_year: row.fiscal_year,
        is_current: row.fiscal_year === currentFiscal?.fiscal_year,
      });
    }
    if (currentFiscal?.fiscal_year && !byYear.has(currentFiscal.fiscal_year)) {
      byYear.set(currentFiscal.fiscal_year, {
        fiscal_year: currentFiscal.fiscal_year,
        is_current: true,
      });
    }
    return Array.from(byYear.values()).sort((a, b) =>
      a.fiscal_year < b.fiscal_year ? 1 : -1
    );
  }, [fiscalHistory, currentFiscal]);

  // User-selected fiscal year — defaults to the current FY once data arrives.
  const [selectedFY, setSelectedFY] = useState<string | null>(null);
  useEffect(() => {
    if (!selectedFY && currentFiscal?.fiscal_year) {
      setSelectedFY(currentFiscal.fiscal_year);
    }
  }, [selectedFY, currentFiscal]);

  // Row matching the user's selection — falls back to current.
  const selectedFiscal: FlowHeroInput | null = useMemo(() => {
    if (!selectedFY) return currentFiscal;
    const match = fiscalHistory.find((r: any) => r.fiscal_year === selectedFY);
    if (match) return match as FlowHeroInput;
    if (currentFiscal?.fiscal_year === selectedFY) return currentFiscal;
    return currentFiscal;
  }, [selectedFY, fiscalHistory, currentFiscal]);

  // The selected year controls hero + donut. Sector-level execution +
  // county utilisation come from the overview endpoint which is pinned to
  // the current fiscal period, so those chapters always reflect the most
  // recent available data.
  const viewingCurrentFY =
    !selectedFY || selectedFY === currentFiscal?.fiscal_year;

  const sectors = overview?.sectors ?? [];
  const countyUtil = overview?.county_utilization ?? {};
  const executionBySector = enhanced?.execution_by_sector ?? [];
  const revenueBySource = enhanced?.revenue_by_source ?? [];
  const economicContext = enhanced?.economic_context ?? null;

  const meta: BudgetMeta | undefined = (overview as any)?._meta;
  const fiscalPeriod: string | undefined = (overview as any)?.fiscal_period;

  /* ─────────────── render ─────────────── */

  if (isLoading) {
    return (
      <PageShell
        title="Kenya's Budget &amp; Spending"
        subtitle='Understanding how public funds are allocated and spent'>
        <PageSkeleton />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Kenya's Budget &amp; Spending" subtitle='Something went wrong'>
        <div className='max-w-md mx-auto py-20 text-center'>
          <AlertTriangle size={40} className='mx-auto text-red-400 mb-3' />
          <p className='text-red-600 mb-4'>Failed to load budget data. Please try again.</p>
          <button
            onClick={() => {
              refetchOverview();
              refetchFiscal();
            }}
            className='px-4 py-2 bg-gov-dark text-white rounded-lg text-sm hover:bg-gov-dark/90 transition-colors'>
            Retry
          </button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Kenya's Budget & Spending"
      subtitle='How public funds are raised, allocated, and spent — with the audit lens on what actually reached citizens.'>
      {/* Freshness + toolbar */}
      <DataFreshnessBadge sources='COB/Treasury' variant='banner' />

      {!overview && !fiscal && (
        <DataIntegrityBanner
          message='Budget data returned empty from the backend. Figures below may show zeros or dashes instead of real values.'
          severity='warning'
        />
      )}

      <DataSourcesModal open={sourcesOpen} onClose={closeSourcesModal} />

      <div className='flex justify-end items-center gap-2 -mb-2'>
        <PDFExportButton compact documentTitle='Kenya Budget & Spending Report' />
        <button
          onClick={() => setSourcesOpen(true)}
          className='inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 dark:text-neutral-muted/80 hover:text-gov-forest dark:text-emerald-100 hover:bg-gov-forest/5 rounded-lg transition-colors'
          title='View data sources'>
          <Info size={14} />
          <span>Sources</span>
        </button>
      </div>

      {/* ─── Fiscal-year picker ─── */}
      <FiscalYearPicker
        years={availableYears}
        selected={selectedFY}
        onSelect={setSelectedFY}
      />

      {/* ─── 1. Hero flow ─── */}
      <BudgetFlowHero data={selectedFiscal} />

      {/* ─── 2. Multi-year trend strip ─── */}
      <FiscalTrendStrip history={fiscalHistory} />

      {/* ─── 3. Where the money goes (donut) ─── */}
      <SpendDonut
        data={{
          fiscal_year: selectedFiscal?.fiscal_year ?? undefined,
          appropriated_budget: selectedFiscal?.appropriated_budget ?? null,
          recurrent_spending: selectedFiscal?.recurrent_spending ?? null,
          debt_service_cost: selectedFiscal?.debt_service_cost ?? null,
          development_spending: selectedFiscal?.development_spending ?? null,
          county_allocation: selectedFiscal?.county_allocation ?? null,
          sectors: (viewingCurrentFY ? sectors : []) as any,
        }}
      />

      {/* ─── 4. Where revenue comes from ─── */}
      <RevenueMix revenueBySource={revenueBySource as any} />

      {/* ─── 5. The audit lens: execution by sector ─── */}
      {viewingCurrentFY && (
        <ExecutionAuditLens
          rows={executionBySector as any}
          fiscalYear={(enhanced as any)?.execution_fiscal_year ?? undefined}
        />
      )}

      {/* ─── 6. County best/worst absorbers ─── */}
      {viewingCurrentFY && (
        <CountyUtilizationStrip
          top={countyUtil?.top_5 ?? []}
          bottom={countyUtil?.bottom_5 ?? []}
          average={countyUtil?.average}
        />
      )}

      {/* Notice if viewing a historical year without sector-level detail */}
      {!viewingCurrentFY && (
        <div className='rounded-xl border border-neutral-border/40 bg-gov-sand/30 px-5 py-4 flex items-start gap-3 text-[12px] text-neutral-muted'>
          <Info size={15} className='mt-0.5 text-gov-forest/70 dark:text-emerald-100/70 flex-shrink-0' />
          <span>
            Sector-level execution and county utilisation are only published for
            the current fiscal period by the Controller of Budget. Switch back
            to{' '}
            <button
              onClick={() => currentFiscal?.fiscal_year && setSelectedFY(currentFiscal.fiscal_year)}
              className='font-semibold text-gov-forest dark:text-emerald-100 hover:underline'>
              {currentFiscal?.fiscal_year ?? 'the current FY'}
            </button>{' '}
            to see those panels.
          </span>
        </div>
      )}

      {/* ─── 7. Economic context ─── */}
      <EconomicContextStrip ctx={economicContext} />

      {/* ─── 8. Sources & reconciliation ─── */}
      <BudgetSourceReconciliation
        meta={meta}
        lastUpdated={overview?.last_updated}
        fiscalPeriod={fiscalPeriod}
      />

      {/* Attribution footer */}
      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        className='text-center text-xs text-gray-400 dark:text-neutral-muted/80 pt-2'>
        Data: National Treasury Budget Policy Statement · Controller of Budget · CRA ·
        Kenya Revenue Authority
        {overview?.last_updated && (
          <span> · Updated {new Date(overview.last_updated).toLocaleDateString()}</span>
        )}
      </motion.div>
    </PageShell>
  );
}

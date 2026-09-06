/**
 * Side-by-side county comparison
 *
 * Pick two or three counties and see their budgets, execution, debt, and
 * sector mix lined up column-for-column. The goal is to let citizens ask
 * "how does my county compare to a similar-sized neighbor?" without having
 * to click through two detail pages and hold numbers in their head.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import ModelledDataNote from '@/components/ModelledDataNote';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import type { BudgetSource } from '@/types';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Plus, X } from 'lucide-react';
import Link from 'next/link';
import { useSearchParams, useRouter } from 'next/navigation';
import { useMemo, useState, Suspense } from 'react';
import ResponsiveTable from '@/components/ui/ResponsiveTable';

/**
 * Raw backend sector label → translation key. Some counties publish
 * variant spellings ("Roads and Public Works", "Water and Sanitation")
 * so we match on substring, not exact equality.
 */
const SECTOR_LABEL_TO_KEY: Array<[string, TranslationKey]> = [
  ['health', 'sectors.health'],
  ['education', 'sectors.education'],
  ['road', 'sectors.roads'],
  ['infrastructure', 'sectors.roads'],
  ['water', 'sectors.water'],
  ['sanitation', 'sectors.water'],
  ['agricultur', 'sectors.agriculture'],
  ['environment', 'sectors.environment'],
  ['trade', 'sectors.trade'],
  ['industry', 'sectors.trade'],
  ['social', 'sectors.social'],
  ['admin', 'sectors.admin'],
  ['governance', 'sectors.admin'],
];


interface CountySummary {
  id: string;
  name: string;
  code: string;
  population: number | null;
  total_budget: number;
  total_spent: number;
  budget_utilization: number | null;
  development_budget: number;
  recurrent_budget: number;
  pending_bills: number | null;
  debt: number | null;
  financial_health_score: number | null;
  audit_rating: string;
  audit_status: string;
  sector_breakdown?: Record<string, { allocated: number; spent: number }>;
  /** Which rows the API summed for total_budget — drives the provenance note. */
  budget_source?: BudgetSource;
}

function fmtKES(n: number | null | undefined): string {
  if (!n) return '—';
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

function fmtNum(n: number | null | undefined): string {
  if (!n) return '—';
  return n.toLocaleString();
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${n.toFixed(1)}%`;
}

function fmtPerCap(budget: number, pop: number | null | undefined): string {
  if (!pop || pop < 1) return '—';
  return fmtKES(budget / pop);
}

function scoreColor(score: number | null | undefined): string {
  if (score == null) return 'bg-gray-200 dark:bg-surface-sunken text-gray-700 dark:text-neutral-muted';
  if (score >= 70) return 'bg-emerald-100 text-emerald-800 border-emerald-200';
  if (score >= 55) return 'bg-amber-100 text-amber-800 border-amber-200';
  return 'bg-rose-100 text-rose-800 border-rose-200';
}

/** Compare a set of numbers; return a rank class for the best/worst. */
function rankStyle(
  value: number | null | undefined,
  all: Array<number | null | undefined>,
  higherIsBetter: boolean
): string {
  const valid = all.filter((v): v is number => v != null && !isNaN(v));
  if (valid.length < 2 || value == null) return '';
  const best = higherIsBetter ? Math.max(...valid) : Math.min(...valid);
  const worst = higherIsBetter ? Math.min(...valid) : Math.max(...valid);
  if (value === best && best !== worst) return 'text-emerald-700 font-bold';
  if (value === worst && best !== worst) return 'text-rose-700 font-semibold';
  return 'text-gray-900 dark:text-neutral-text';
}

function ComparePicker({
  all,
  selected,
  onChange,
  onAdd,
  onRemove,
}: {
  all: CountySummary[];
  selected: string[];
  onChange: (index: number, countyId: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}) {
  const { t } = useLang();
  return (
    <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 flex flex-wrap items-end gap-3'>
      {selected.map((sel, i) => (
        <div key={`${sel}-${i}`} className='flex-1 min-w-[200px] relative'>
          <label className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold block mb-1'>
            {t('compare.county_label')} {i + 1}
          </label>
          <div className='flex items-center gap-2'>
            <select
              value={sel}
              onChange={(e) => onChange(i, e.target.value)}
              className='flex-1 text-sm border border-gray-200 dark:border-neutral-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-gov-forest/30 bg-white dark:bg-surface-base'>
              <option value=''>{t('compare.pick_prompt')}</option>
              {all.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {selected.length > 2 && (
              <button
                type='button'
                onClick={() => onRemove(i)}
                className='text-gray-400 dark:text-neutral-muted/80 hover:text-rose-600 p-1'
                aria-label={t('compare.remove_county').replace('{n}', String(i + 1))}>
                <X size={16} />
              </button>
            )}
          </div>
        </div>
      ))}
      {selected.length < 3 && (
        <button
          type='button'
          onClick={onAdd}
          className='text-sm font-semibold text-gov-forest dark:text-emerald-100 hover:text-gov-forest/80 dark:text-emerald-100/80 inline-flex items-center gap-1 px-3 py-2'>
          <Plus size={14} />
          {t('compare.add_county')}
        </button>
      )}
    </div>
  );
}

interface RowProps {
  label: string;
  values: Array<string>;
  highlight?: Array<string>;
  sublabel?: string;
}

function CompareRow({ label, values, highlight, sublabel }: RowProps) {
  return (
    <tr className='border-b border-gray-100 dark:border-neutral-border last:border-b-0'>
      <td className='py-3 pr-4 align-top'>
        <div className='text-sm font-semibold text-gray-700 dark:text-neutral-muted'>{label}</div>
        {sublabel && <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{sublabel}</div>}
      </td>
      {values.map((v, i) => (
        <td
          key={i}
          className={`py-3 px-4 text-right tabular-nums text-sm ${
            highlight?.[i] || 'text-gray-900 dark:text-neutral-text'
          }`}>
          {v}
        </td>
      ))}
    </tr>
  );
}

function CompareContent() {
  const { t } = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const urlIds = useMemo(() => (params.get('ids') || '').split(',').filter(Boolean), [params]);

  // Keep at least 2 picker slots; seed from URL if present.
  const [selected, setSelected] = useState<string[]>(() => {
    if (urlIds.length >= 2) return urlIds.slice(0, 3);
    return ['', ''];
  });

  const { data: all, isLoading } = useQuery<CountySummary[]>({
    queryKey: ['counties', 'all-for-compare'],
    queryFn: async () => (await api.get<CountySummary[]>('/counties?limit=50')).data,
    staleTime: 15 * 60 * 1000,
  });

  const byId = useMemo(() => {
    const m: Record<string, CountySummary> = {};
    (all || []).forEach((c) => {
      m[c.id] = c;
    });
    return m;
  }, [all]);

  const picked: CountySummary[] = selected
    .map((id) => byId[id])
    .filter((c): c is CountySummary => !!c);

  const updateSelected = (next: string[]) => {
    setSelected(next);
    const filled = next.filter(Boolean);
    if (filled.length > 0) {
      router.replace(`/counties/compare?ids=${filled.join(',')}`, { scroll: false });
    } else {
      router.replace('/counties/compare', { scroll: false });
    }
  };

  const onChange = (i: number, v: string) => {
    const next = [...selected];
    next[i] = v;
    updateSelected(next);
  };
  const onAdd = () => updateSelected([...selected, '']);
  const onRemove = (i: number) =>
    updateSelected(selected.filter((_, idx) => idx !== i));

  return (
    <div className='space-y-6'>
      {/* The counties being compared; before any are picked, the pool they
          are picked from. */}
      <ModelledDataNote
        budgetSource={(picked.length ? picked : all || []).map((c) => c.budget_source)}
      />
      {isLoading && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
          <Loader2 className='animate-spin' size={18} />
          <span>{t('compare.loading')}</span>
        </div>
      )}

      {!isLoading && all && (
        <>
          <ComparePicker
            all={all}
            selected={selected}
            onChange={onChange}
            onAdd={onAdd}
            onRemove={onRemove}
          />

          {picked.length < 2 ? (
            <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-12 text-center'>
              <div className='text-base font-semibold text-gray-700 dark:text-neutral-muted mb-1'>
                {t('compare.empty.title')}
              </div>
              <p className='text-sm text-gray-500 dark:text-neutral-muted/80 max-w-md mx-auto'>
                {t('compare.empty.body')}
              </p>
            </div>
          ) : (
            <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border overflow-hidden'>
              <ResponsiveTable>
                <table className='w-full'>
                  <thead>
                    <tr className='bg-gray-50 dark:bg-surface-elevated border-b border-gray-200 dark:border-neutral-border'>
                      <th className='text-left py-3 pr-4 pl-5 text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                        {t('common.metric')}
                      </th>
                      {picked.map((c) => (
                        <th
                          key={c.id}
                          className='text-right py-3 px-4 min-w-[140px]'>
                          <Link
                            href={`/counties/${c.id}`}
                            className='text-sm font-bold text-gray-900 dark:text-neutral-text hover:text-gov-forest dark:text-emerald-100 hover:underline'>
                            {c.name}
                          </Link>
                          <div className='text-[11px] text-gray-400 dark:text-neutral-muted/80 font-mono mt-0.5'>
                            #{c.code}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className='px-5'>
                    {/* Section: Population & budget */}
                    <tr>
                      <td
                        colSpan={picked.length + 1}
                        className='bg-gray-50/50 dark:bg-surface-elevated/70 px-5 py-2 text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-bold border-b border-gray-100 dark:border-neutral-border'>
                        {t('compare.section.pop_budget')}
                      </td>
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.population')}
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                            c.population,
                            picked.map((p) => p.population),
                            true
                          )}`}>
                          {fmtNum(c.population)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.total_budget')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{t('compare.row.total_budget_sub')}</div>
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                            c.total_budget,
                            picked.map((p) => p.total_budget),
                            true
                          )}`}>
                          {fmtKES(c.total_budget)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.per_capita')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                          {t('compare.row.per_capita_sub')}
                        </div>
                      </td>
                      {picked.map((c) => {
                        const perCap =
                          c.population && c.population > 0
                            ? c.total_budget / c.population
                            : null;
                        return (
                          <td
                            key={c.id}
                            className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                              perCap,
                              picked.map((p) =>
                                p.population && p.population > 0
                                  ? p.total_budget / p.population
                                  : null
                              ),
                              true
                            )}`}>
                            {fmtPerCap(c.total_budget, c.population)}
                          </td>
                        );
                      })}
                    </tr>

                    {/* Section: Execution */}
                    <tr>
                      <td
                        colSpan={picked.length + 1}
                        className='bg-gray-50/50 dark:bg-surface-elevated/70 px-5 py-2 text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-bold border-t border-b border-gray-100 dark:border-neutral-border'>
                        {t('compare.section.execution')}
                      </td>
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.spent')}
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className='py-3 px-4 text-right tabular-nums text-sm text-gray-900 dark:text-neutral-text'>
                          {fmtKES(c.total_spent)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.utilization')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                          {t('compare.row.utilization_sub')}
                        </div>
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                            c.budget_utilization,
                            picked.map((p) => p.budget_utilization),
                            true
                          )}`}>
                          {fmtPct(c.budget_utilization)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.dev_share')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                          {t('compare.row.dev_share_sub')}
                        </div>
                      </td>
                      {picked.map((c) => {
                        const share =
                          c.total_budget > 0
                            ? (c.development_budget / c.total_budget) * 100
                            : null;
                        return (
                          <td
                            key={c.id}
                            className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                              share,
                              picked.map((p) =>
                                p.total_budget > 0
                                  ? (p.development_budget / p.total_budget) * 100
                                  : null
                              ),
                              true
                            )}`}>
                            {fmtPct(share)}
                          </td>
                        );
                      })}
                    </tr>

                    {/* Section: Financial health */}
                    <tr>
                      <td
                        colSpan={picked.length + 1}
                        className='bg-gray-50/50 dark:bg-surface-elevated/70 px-5 py-2 text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-bold border-t border-b border-gray-100 dark:border-neutral-border'>
                        {t('compare.section.health')}
                      </td>
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.pending_bills')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                          {t('compare.row.pending_bills_sub')}
                        </div>
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                            c.pending_bills,
                            picked.map((p) => p.pending_bills),
                            false
                          )}`}>
                          {fmtKES(c.pending_bills)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.debt')}
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className={`py-3 px-4 text-right tabular-nums text-sm ${rankStyle(
                            c.debt,
                            picked.map((p) => p.debt),
                            false
                          )}`}>
                          {fmtKES(c.debt)}
                        </td>
                      ))}
                    </tr>
                    <tr className='border-b border-gray-100 dark:border-neutral-border'>
                      <td className='py-3 pr-4 pl-5 text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                        {t('compare.row.health_score')}
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                          {t('compare.row.health_score_sub')}
                        </div>
                      </td>
                      {picked.map((c) => (
                        <td
                          key={c.id}
                          className='py-3 px-4 text-right'>
                          <span
                            className={`inline-flex items-center justify-center min-w-[60px] text-sm font-bold tabular-nums px-2 py-1 rounded-full border ${scoreColor(c.financial_health_score)}`}>
                            {c.financial_health_score != null
                              ? c.financial_health_score.toFixed(0)
                              : '—'}
                          </span>
                        </td>
                      ))}
                    </tr>

                    {/* The "Sector spending (actual)" rows were withdrawn
                        (credibility audit F11) — `sector_breakdown` is one
                        fixed template (25/20/15/10/8/7/5/4/3/3) applied to
                        every county's headline budget, so comparing two
                        counties' sector rows compared the same percentages
                        twice. */}
                  </tbody>
                </table>
              </ResponsiveTable>
            </div>
          )}

          <div className='bg-gov-forest/5 border border-gov-forest/20 rounded-xl p-5 text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>
            <p className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>{t('compare.footer.title')}</p>
            <p>{t('compare.footer.body')}</p>
          </div>
        </>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
          <Loader2 className='animate-spin' size={18} />
        </div>
      }>
      <ComparePageInner />
    </Suspense>
  );
}

function ComparePageInner() {
  const { t } = useLang();
  return (
    <PageShell
      title={t('compare.title')}
      subtitle={t('compare.subtitle')}
      back={{ href: '/counties', label: t('common.all_counties') }}>
      <CompareContent />
    </PageShell>
  );
}

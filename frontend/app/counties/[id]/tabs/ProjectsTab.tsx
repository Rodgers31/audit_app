'use client';

/**
 * ProjectsTab — list of stalled / delayed county projects flagged by OAG.
 * Shows contracted vs. paid, completion % progress bars, and the
 * auditor's stated reason. Separate chunk so zero JS is paid if the
 * county has no stalled projects.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import { CountyComprehensive } from '@/types';
import { CheckCircle2, Clock } from 'lucide-react';
import { fmtKES, pct } from '../shared';
import KPI from './KPI';

export default function ProjectsTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { stalled_projects } = data;

  if (stalled_projects.count === 0) {
    return (
      <div className='bg-emerald-50 border border-emerald-200 rounded-xl p-6 text-center'>
        <CheckCircle2 size={32} className='mx-auto text-emerald-500 mb-2' />
        <p className='text-sm text-emerald-800 font-medium'>{t('county.projects.none_title')}</p>
        <p className='text-xs text-emerald-600 mt-1'>{t('county.projects.none_body')}</p>
      </div>
    );
  }

  return (
    <div className='space-y-4'>
      {/* Summary */}
      <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
        <div className='grid grid-cols-3 gap-4'>
          <KPI
            label={t('county.projects.kpi_stalled')}
            value={String(stalled_projects.count)}
            accent='text-red-700'
          />
          <KPI
            label={t('county.projects.kpi_contracted')}
            value={fmtKES(stalled_projects.total_contracted_value)}
            accent='text-blue-700'
          />
          <KPI
            label={t('county.projects.kpi_paid')}
            value={fmtKES(stalled_projects.total_amount_paid)}
            sub={`${pct((stalled_projects.total_amount_paid / (stalled_projects.total_contracted_value || 1)) * 100)} ${t('county.projects.disbursed_suffix')}`}
            accent='text-amber-700'
          />
        </div>
      </div>

      {/* Project cards */}
      {stalled_projects.projects.map((p, i) => (
        <div key={i} className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
          <div className='flex items-start justify-between gap-3 mb-3'>
            <div className='min-w-0'>
              <h4 className='text-sm font-semibold text-gray-900 dark:text-neutral-text'>{p.project_name}</h4>
              <div className='flex items-center gap-2 mt-0.5 flex-wrap'>
                <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>{p.sector}</span>
                {p.oag_reference && (
                  <span className='text-[10px] text-gray-400 dark:text-neutral-muted/80 border border-gray-200 dark:border-neutral-border rounded px-1.5 py-0.5'>
                    {p.oag_reference}
                  </span>
                )}
              </div>
            </div>
            <span
              className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border flex-shrink-0 ${
                p.status === 'stalled'
                  ? 'bg-red-50 border-red-200 text-red-700'
                  : 'bg-amber-50 border-amber-200 text-amber-700'
              }`}>
              {p.status === 'stalled'
                ? t('county.projects.status_stalled')
                : t('county.projects.status_delayed')}
            </span>
          </div>

          {/* Progress */}
          <div className='mb-3'>
            <div className='flex items-center justify-between mb-1'>
              <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                {p.completion_pct}% {t('county.projects.complete_suffix')}
              </span>
              <span className='text-xs text-gray-500 dark:text-neutral-muted/80 tabular-nums'>
                {fmtKES(p.amount_paid)} / {fmtKES(p.contracted_amount)}
              </span>
            </div>
            <div className='h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
              <div
                className={`h-full rounded-full transition-all ${
                  p.status === 'stalled' ? 'bg-red-500' : 'bg-amber-500'
                }`}
                style={{ width: `${p.completion_pct}%` }}
              />
            </div>
          </div>

          {/* Meta */}
          <div className='flex items-center gap-4 text-xs text-gray-500 dark:text-neutral-muted/80 flex-wrap'>
            <span className='flex items-center gap-1'>
              <Clock size={11} />
              {t('county.projects.started')} {p.start_year}
            </span>
            <span className='flex items-center gap-1'>
              <Clock size={11} />
              {t('county.projects.expected')} {p.expected_completion}
            </span>
          </div>
          {p.reason && (
            <p className='text-xs text-gray-600 dark:text-neutral-muted mt-2 bg-gray-50 dark:bg-surface-elevated rounded-lg p-2.5 border border-gray-100 dark:border-neutral-border italic'>
              {p.reason}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

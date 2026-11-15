'use client';

import type { ReactNode } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';

type GradeRow = {
  label: string;
  word: string;
  grade: string;
  score: number | null;
  /** Band in presentation order, starting with the lowest. */
  band: 0 | 1 | 2 | 3 | 4;
};

export function roundedCountyScore(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value) : null;
}

export default function CountyReportCard({ county, money, audit, findings, method }: {
  county: string;
  money?: GradeRow;
  audit?: GradeRow;
  findings?: ReactNode;
  method: ReactNode;
}) {
  const { t } = useLang();
  return (
    <section className='audit-panel space-y-2 p-4'>
      <h3 className='text-sm font-semibold'>{t('foundation.county_report_card')}</h3>
      <p className='font-display text-audit-stat font-semibold'>{county}</p>
      {[money, audit].map((row, index) => {
        if (!row) return null;
        const score = roundedCountyScore(row.score);
        return (
          <div key={index} className='grid grid-cols-[3rem_minmax(0,1fr)] items-center gap-3 border-t border-neutral-border py-3'>
            <span className='audit-figure text-audit-stat'>{row.grade}</span>
            <div>
              <p className='text-sm font-semibold'>{row.label} · {row.word}</p>
              <p className='text-xs text-neutral-muted'>{score === null ? t('foundation.not_published') : `${score} / 100`}</p>
              {score !== null && <div aria-hidden='true' className='mt-2 grid grid-cols-5 gap-1'>
                {['#c9dad2', '#a1bfb0', '#769e88', '#4b7b63', '#174a34'].map((color, band) => (
                  <span key={color} style={{ backgroundColor: color }} className={`h-2 ${band === row.band ? 'outline outline-2 outline-offset-1 outline-current' : ''}`} />
                ))}
              </div>}
            </div>
          </div>
        );
      })}
      {findings}
      {method}
      <p className='text-xs text-neutral-muted'>{t('foundation.grade_basis')}</p>
    </section>
  );
}

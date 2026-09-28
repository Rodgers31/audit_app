'use client';

import type { FiscalYearOption } from '@/components/budget/FiscalYearPicker';
import { CalendarRange, ChevronDown } from 'lucide-react';
import { useLang } from '@/lib/i18n/LangProvider';
import styles from './MoneyFlowPresentation.module.css';

export default function MoneyFlowPeriodPicker({
  years,
  selected,
  onSelect,
}: {
  years: FiscalYearOption[];
  selected: string;
  onSelect: (year: string) => void;
}) {
  const { t } = useLang();
  if (years.length === 0) return null;
  return (
    <div className={`${styles.presentation} ${styles.period}`}>
      <label className={styles.periodLabel} htmlFor='money-flow-period'>
        <CalendarRange size={20} aria-hidden='true' />
        {t('transparency.period.label')}
      </label>
      <div className={styles.periodChoice}>
        <select
          id='money-flow-period'
          value={selected}
          onChange={(event) => onSelect(event.target.value)}
          aria-describedby='money-flow-period-help'>
          {years.map((year) => (
            <option key={year.fiscal_year} value={year.fiscal_year}>
              FY {year.fiscal_year.replace(/^FY\s*/i, '')}
              {year.is_current ? ` · ${t('transparency.period.current')}` : ''}
            </option>
          ))}
        </select>
        <ChevronDown size={16} aria-hidden='true' />
      </div>
      <p id='money-flow-period-help' className={styles.periodHelp}>
        {t('transparency.period.help')}
      </p>
    </div>
  );
}

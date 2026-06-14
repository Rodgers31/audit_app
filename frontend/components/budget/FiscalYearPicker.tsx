'use client';

/**
 * FiscalYearPicker
 *
 * A compact segmented control for switching between fiscal years. Sits above
 * the BudgetFlowHero so the entire narrative re-renders against whichever
 * year the user picks.
 *
 * The "current" year (from fiscal.current) gets a subtle live badge; past
 * years are neutral pills. Everything animates with framer-motion.
 */

import { motion } from 'framer-motion';
import { CalendarRange, Radio } from 'lucide-react';

export interface FiscalYearOption {
  fiscal_year: string;
  is_current?: boolean;
}

interface Props {
  years: FiscalYearOption[];
  selected: string | null;
  onSelect: (fy: string) => void;
}

export default function FiscalYearPicker({ years, selected, onSelect }: Props) {
  if (!years || years.length < 2) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className='rounded-xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-3 sm:p-4 flex flex-wrap items-center gap-2'>
      <div className='flex items-center gap-2 pr-2 sm:border-r border-neutral-border/40'>
        <div className='w-8 h-8 rounded-lg bg-gov-forest/10 text-gov-forest dark:text-emerald-100 flex items-center justify-center'>
          <CalendarRange size={16} />
        </div>
        <div className='hidden sm:block'>
          <div className='text-[10px] uppercase tracking-wider font-semibold text-gov-forest/80 dark:text-emerald-100/80'>
            Fiscal year
          </div>
          <div className='text-[11px] text-neutral-muted leading-tight'>
            Pick a year to drive the whole page
          </div>
        </div>
      </div>

      <div className='flex flex-wrap gap-1.5'>
        {years.map((y) => {
          const isActive = y.fiscal_year === selected;
          const isCurrent = Boolean(y.is_current);
          return (
            <button
              key={y.fiscal_year}
              type='button'
              onClick={() => onSelect(y.fiscal_year)}
              aria-pressed={isActive}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition-all tabular-nums ${
                isActive
                  ? 'bg-gov-forest text-white border-gov-forest shadow-sm'
                  : 'bg-white dark:bg-surface-base text-gov-dark dark:text-white border-neutral-border/50 hover:border-gov-forest/40 hover:bg-gov-forest/5'
              }`}>
              {isCurrent && (
                <span
                  className={`relative flex h-1.5 w-1.5 ${isActive ? '' : 'text-gov-forest dark:text-emerald-100'}`}
                  aria-hidden='true'>
                  <span
                    className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${
                      isActive ? 'bg-white dark:bg-surface-base' : 'bg-gov-forest'
                    }`}
                  />
                  <span
                    className={`relative inline-flex rounded-full h-1.5 w-1.5 ${
                      isActive ? 'bg-white dark:bg-surface-base' : 'bg-gov-forest'
                    }`}
                  />
                </span>
              )}
              FY{y.fiscal_year.replace(/^FY\s*/i, '')}
              {isCurrent && (
                <span
                  className={`hidden sm:inline text-[9.5px] uppercase tracking-wider font-medium ${
                    isActive ? 'text-white/80' : 'text-gov-forest/80 dark:text-emerald-100/80'
                  }`}>
                  current
                </span>
              )}
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}

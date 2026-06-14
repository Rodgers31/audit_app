'use client';

import InfoTip from '@/components/InfoTip';
import { SkeletonTable } from '@/components/ui/Skeleton';
import { NationalLoan } from '@/lib/api/debt';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useNationalLoans } from '@/lib/react-query/useDebt';
import { fmtKES } from '@/lib/utils';
import { motion } from 'framer-motion';
import { ExternalLink, Landmark, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import DebtExplainerModal from './DebtExplainerModal';

// fmtKES imported from @/lib/utils — expects raw KES input (Loan table data)

function shortLender(name: string): string {
  return name
    .replace(/\s*\(.*?\)\s*/g, ' ')
    .replace('Treasury Bonds ', 'T-Bonds ')
    .replace('Treasury Bills ', 'T-Bills ')
    .replace('Central Bank of Kenya Advance', 'CBK Advance')
    .replace('Pre-1997 Government Debt', 'Legacy Debt')
    .replace('Standard Chartered Syndicated Loan', 'StanChart Syndicated')
    .trim();
}

const FLAG_EMOJI: Record<string, string> = {
  'World Bank': '🏦',
  'International Monetary Fund': '🏦',
  'African Development Bank': '🏦',
  'European Investment Bank': '🏦',
  IFAD: '🏦',
  China: '🇨🇳',
  Japan: '🇯🇵',
  France: '🇫🇷',
  Germany: '🇩🇪',
  'United States': '🇺🇸',
  'South Korea': '🇰🇷',
  India: '🇮🇳',
  Belgium: '🇧🇪',
  Eurobond: '📜',
  'Standard Chartered': '🏛️',
  Treasury: '🇰🇪',
  Central: '🇰🇪',
  'Pre-1997': '📋',
};

function lenderEmoji(name: string): string {
  for (const [key, emoji] of Object.entries(FLAG_EMOJI)) {
    if (name.includes(key)) return emoji;
  }
  return '🏛️';
}

const TYPE_LABEL: Record<string, { key: TranslationKey; color: string }> = {
  external_multilateral: { key: 'home.loans.type.multilateral', color: 'text-blue-600 bg-blue-50' },
  external_bilateral: { key: 'home.loans.type.bilateral', color: 'text-purple-600 bg-purple-50' },
  external_commercial: { key: 'home.loans.type.commercial', color: 'text-gov-copper bg-gov-copper/10' },
  domestic_bond: { key: 'home.loans.type.domestic', color: 'text-gov-forest dark:text-emerald-100 bg-gov-sage/10' },
  domestic_tbill: { key: 'home.loans.type.tbill', color: 'text-gov-gold bg-gov-gold/10' },
  domestic_cbk: { key: 'home.loans.type.cbk', color: 'text-gov-dark dark:text-white bg-gov-sand' },
  domestic_legacy: { key: 'home.loans.type.legacy', color: 'text-neutral-muted bg-neutral-border/20' },
};

export default function NationalLoansCard() {
  const { t } = useLang();
  const { data, isLoading, error } = useNationalLoans();

  if (isLoading) {
    return <SkeletonTable rows={8} cols={4} />;
  }

  if (error || !data) {
    return (
      <div className='glass-card p-8 flex flex-col items-center justify-center min-h-[340px] gap-2'>
        <Landmark className='w-6 h-6 text-neutral-muted/25' />
        <p className='text-xs text-neutral-muted'>{t('home.loans.unavailable')}</p>
      </div>
    );
  }

  // Sort ascending (smallest first) and match budget sector count for alignment
  const sorted = [...data.loans].sort((a, b) => a.outstanding_numeric - b.outstanding_numeric);
  /** Max visible rows — tuned so card height ≈ BudgetSnapshotCard */
  const VISIBLE = 14;
  const topLoans = sorted.slice(0, VISIBLE);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className='glass-card overflow-hidden flex flex-col'>
      {/* Header */}
      <div className='bg-gradient-to-r from-gov-copper/[0.06] via-gov-sand/40 to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <div className='flex items-start justify-between'>
          <div>
            <h3 className='font-display text-lg text-gov-dark dark:text-white mb-0.5'>{t('home.loans.header_title')}</h3>
            <p className='text-xs text-neutral-muted'>
              {t('home.loans.header_sub')
                .replace('{n}', String(data.total_loans))
                .replace('{src}', data.source || '')}
            </p>
          </div>
          {data.source_url && (
            <a
              href={data.source_url}
              target='_blank'
              rel='noopener noreferrer'
              className='flex items-center gap-1 text-[10px] text-neutral-muted hover:text-gov-forest dark:text-emerald-100 transition-colors mt-1'>
              Treasury <ExternalLink className='w-3 h-3' />
            </a>
          )}
        </div>
      </div>

      <div className='px-6 sm:px-8 py-5 flex flex-col flex-1'>
        {/* Headline stats */}
        <div className='grid grid-cols-2 gap-3 mb-5'>
          <div className='rounded-xl bg-gov-copper/[0.05] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-center gap-1.5 mb-1'>
              <Landmark className='w-3.5 h-3.5 text-gov-copper opacity-70' />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                {t('home.loans.outstanding')}
              </span>
              <InfoTip term='outstanding' size={11} />
              <DebtExplainerModal context='loans' />
            </div>
            <span className='text-lg font-bold text-gov-copper tabular-nums leading-none'>
              {fmtKES(data.total_outstanding)}
            </span>
          </div>
          <div className='rounded-xl bg-gov-gold/[0.06] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-center gap-1.5 mb-1'>
              <TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                {t('home.loans.annual_service')}
              </span>
            </div>
            <span className='text-lg font-bold text-gov-gold tabular-nums leading-none'>
              {fmtKES(data.total_annual_service_cost)}
            </span>
          </div>
        </div>

        {/* Loan table */}
        <div className='space-y-1.5'>
          {topLoans.map((loan: NationalLoan, i: number) => {
            const typeInfo = TYPE_LABEL[loan.lender_type] || TYPE_LABEL.domestic_legacy;
            return (
              <motion.div
                key={loan.lender + i}
                initial={{ opacity: 0, x: -8 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: 0.05 * i }}
                className='flex items-center gap-2 rounded-lg border border-neutral-border/25 bg-white/40 dark:bg-surface-elevated hover:bg-gov-sand/30 transition-colors px-3 py-2'>
                <span className='text-sm leading-none flex-shrink-0' suppressHydrationWarning>
                  {lenderEmoji(loan.lender)}
                </span>
                <span className='text-xs font-semibold text-gov-dark dark:text-white truncate min-w-0 flex-1'>
                  {shortLender(loan.lender)}
                </span>
                <div className='flex items-center gap-1 flex-shrink-0'>
                  <span
                    className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${typeInfo.color}`}>
                    {t(typeInfo.key)}
                  </span>
                  {(typeInfo.key === 'home.loans.type.multilateral' ||
                    typeInfo.key === 'home.loans.type.bilateral' ||
                    typeInfo.key === 'home.loans.type.commercial') && (
                    <InfoTip
                      term={
                        typeInfo.key === 'home.loans.type.multilateral'
                          ? 'multilateral'
                          : typeInfo.key === 'home.loans.type.bilateral'
                            ? 'bilateral'
                            : 'commercial'
                      }
                      size={10}
                    />
                  )}
                </div>
                <span className='text-xs font-bold text-gov-dark dark:text-white tabular-nums flex-shrink-0'>
                  {fmtKES(loan.outstanding_numeric)}
                </span>
                <span className='text-[10px] text-neutral-muted tabular-nums flex-shrink-0'>
                  {loan.interest_rate}
                </span>
                <span className='text-[11px] font-semibold text-gov-copper tabular-nums flex-shrink-0 w-12 text-right'>
                  {fmtKES(loan.annual_service_cost)}
                </span>
              </motion.div>
            );
          })}
        </div>

        {data.loans.length > VISIBLE && (
          <Link
            href='/debt'
            className='group mt-auto pt-4 flex items-center justify-center gap-1.5 w-full rounded-lg bg-white/60 dark:bg-surface-elevated border border-neutral-border/40 hover:border-gov-copper/30 hover:bg-gov-copper/[0.03] px-4 py-2.5 transition-all text-xs font-medium text-gov-dark dark:text-white'>
            {t('home.loans.see_all_n').replace('{n}', String(data.loans.length))}
          </Link>
        )}
      </div>
    </motion.div>
  );
}

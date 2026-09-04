/**
 * FinancialSummary - Financial summary section with key metrics
 * Displays revenue, expenditure, balance, and per capita debt
 */
'use client';

import { getBalanceColor } from './countyUtils';

interface FinancialSummaryProps {
  // Nullable: a county that reported nothing is not a county with KES 0.
  revenue: number | null;
  expenditure: number | null;
  balance: number | null;
  perCapitaDebt: number | null;
}

export default function FinancialSummary({
  revenue,
  expenditure,
  balance,
  perCapitaDebt,
}: FinancialSummaryProps) {
  return (
    <div className='bg-gray-50 dark:bg-surface-elevated border border-gray-200 dark:border-neutral-border rounded-2xl p-4'>
      <h3 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-4'>Financial Summary</h3>

      <div className='grid grid-cols-2 md:grid-cols-4 gap-4'>
        {/* Revenue */}
        <div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1 font-medium'>Revenue</div>
          <div className='text-lg font-bold text-green-600'>
            {revenue != null ? `KES ${(revenue / 1e9).toFixed(1)}B` : '—'}
          </div>
        </div>

        {/* Expenditure */}
        <div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1 font-medium'>Expenditure</div>
          <div className='text-lg font-bold text-blue-600'>
            {expenditure != null ? `KES ${(expenditure / 1e9).toFixed(1)}B` : '—'}
          </div>
        </div>

        {/* Balance */}
        <div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1 font-medium'>Balance</div>
          <div
            className={`text-lg font-bold ${
              balance != null ? getBalanceColor(balance) : 'text-gray-400'
            }`}>
            {balance != null ? `KES ${(Math.abs(balance) / 1e6).toFixed(0)}M` : '—'}
          </div>
        </div>

        {/* Per Capita Debt */}
        <div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1 font-medium'>Per Capita Debt</div>
          <div className='text-lg font-bold text-orange-600'>
            {perCapitaDebt != null
              ? `KES ${Math.round(perCapitaDebt).toLocaleString()}`
              : '—'}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * MetricsCards - Grid of main county metric cards
 * Contains budget, debt, and audit cards in a responsive layout
 */
'use client';

import { County } from '@/types';
import AuditCard from './AuditCard';
import BudgetCard from './BudgetCard';
import DebtCard from './DebtCard';

interface MetricsCardsProps {
  county: County;
  budgetUtilization: number | null;
  debtRatio: number;
}

export default function MetricsCards({ county, budgetUtilization, debtRatio }: MetricsCardsProps) {
  return (
    <div className='grid grid-cols-1 md:grid-cols-3 gap-5 mb-6'>
      <BudgetCard
        budget={county.budget ?? county.totalBudget ?? 0}
        budgetUtilization={budgetUtilization}
      />
      <DebtCard debt={county.debt ?? county.totalDebt ?? 0} debtRatio={debtRatio} />
      <AuditCard county={county} />
    </div>
  );
}

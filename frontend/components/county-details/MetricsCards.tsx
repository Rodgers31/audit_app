/**
 * MetricsCards - Grid of main county metric cards
 * Contains budget, debt, and audit cards in a responsive layout
 */
'use client';

import { countyBudget, countyDebt } from '@/lib/countyFigures';
import { County } from '@/types';
import AuditCard from './AuditCard';
import BudgetCard from './BudgetCard';
import DebtCard from './DebtCard';

interface MetricsCardsProps {
  county: County;
  budgetUtilization: number | null;
  /** null when the API published no debt or no budget to divide it by. */
  debtRatio: number | null;
}

export default function MetricsCards({ county, budgetUtilization, debtRatio }: MetricsCardsProps) {
  return (
    <div className='grid grid-cols-1 md:grid-cols-3 gap-5 mb-6'>
      <BudgetCard budget={countyBudget(county) ?? null} budgetUtilization={budgetUtilization} />
      <DebtCard debt={countyDebt(county) ?? null} debtRatio={debtRatio} />
      <AuditCard county={county} />
    </div>
  );
}

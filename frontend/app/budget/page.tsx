import { Metadata } from 'next';
import BudgetSpendingPage from './BudgetPageClient';

export const metadata: Metadata = {
  title: 'Budget & Spending — AuditGava',
  description:
    "How Kenya spends its national budget. Sector allocations, execution rates, revenue sources, and fiscal trends from official government reports.",
};

export default function BudgetPage() {
  return <BudgetSpendingPage />;
}

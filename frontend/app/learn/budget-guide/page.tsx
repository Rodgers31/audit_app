import type { Metadata } from 'next';
import { BUDGET_GUIDE_MESSAGES } from '@/lib/i18n/messages/budgetGuide';
import BudgetGuide from './BudgetGuide';
import { findBudgetGuideStep } from './budgetGuideData';

export const metadata: Metadata = {
  title: `${BUDGET_GUIDE_MESSAGES.title.en} — AuditGava`,
  description: BUDGET_GUIDE_MESSAGES.metadataDescription.en,
};

export default async function BudgetGuidePage({ searchParams }: {
  searchParams: Promise<{ step?: string | string[] }>;
}) {
  const { step } = await searchParams;
  return <BudgetGuide step={findBudgetGuideStep(step)} />;
}

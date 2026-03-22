import { Metadata } from 'next';
import NationalDebtPage from './DebtPageClient';

export const metadata: Metadata = {
  title: 'National Debt — AuditGava',
  description:
    "Kenya's public debt stands at KES 12.5 trillion. Track external vs domestic debt, debt-to-GDP ratio, loan details, and sustainability indicators.",
};

export default function DebtPage() {
  return <NationalDebtPage />;
}

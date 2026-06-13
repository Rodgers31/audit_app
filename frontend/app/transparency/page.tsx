import { Metadata } from 'next';
import TransparencyPage from './TransparencyPageClient';

export const metadata: Metadata = {
  title: 'Follow the Money — AuditGava',
  description:
    'Trace how public funds flow from treasury allocation to county expenditure, and what the Auditor-General has questioned.',
};

export default function FollowTheMoneyPage() {
  return <TransparencyPage />;
}

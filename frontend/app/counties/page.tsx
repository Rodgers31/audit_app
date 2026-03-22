import { Metadata } from 'next';
import CountyExplorerPage from './CountiesPageClient';

export const metadata: Metadata = {
  title: 'County Explorer — AuditGava',
  description:
    'Compare all 47 Kenyan counties by budget, spending efficiency, audit findings, and financial health. Data from Controller of Budget and OAG.',
};

export default function CountiesPage() {
  return <CountyExplorerPage />;
}

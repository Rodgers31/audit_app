/**
 * /learn/government — Interactive government structure explorer.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import GovernmentExplorer from '@/components/learn/GovernmentExplorer';

export default function GovernmentPage() {
  return (
    <PageShell
      title='How Kenya Is Governed'
      subtitle='Explore the three arms of government and how power is shared between national and county level under the 2010 Constitution'
      back={{ href: '/learn', label: 'Back to Learning Hub' }}>
      <GovernmentExplorer />
    </PageShell>
  );
}

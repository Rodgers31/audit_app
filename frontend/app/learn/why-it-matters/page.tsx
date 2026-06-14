/**
 * /learn/why-it-matters — Real-world impact stories.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import WhyThisMatters from '@/components/WhyThisMatters';

export default function WhyItMattersPage() {
  return (
    <PageShell
      title='Why This Matters'
      subtitle='Real stories showing how government finances affect healthcare, education, roads, and everyday life for Kenyans'
      back={{ href: '/learn', label: 'Back to Learning Hub' }}>
      <WhyThisMatters searchTerm='' />
    </PageShell>
  );
}

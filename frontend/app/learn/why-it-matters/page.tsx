/**
 * /learn/why-it-matters — how to read the public finance figures on
 * this site and what they do and don't tell you.
 *
 * The illustrative "real stories" this page used to carry were withdrawn:
 * none of them traced to a named document, publisher and period.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import WhyThisMatters from '@/components/WhyThisMatters';

export default function WhyItMattersPage() {
  return (
    <PageShell
      title='Why This Matters'
      subtitle='How to read these figures — what public spending on healthcare, education and roads is reported to be, where the numbers come from, and what they leave out'
      back={{ href: '/learn', label: 'Back to Learning Hub' }}>
      <WhyThisMatters />
    </PageShell>
  );
}

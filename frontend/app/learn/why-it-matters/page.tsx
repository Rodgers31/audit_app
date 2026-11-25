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
import { whyMoneyMatters } from '@/components/why-this-matters/messages';
import { useLang } from '@/lib/i18n/LangProvider';

export default function WhyItMattersPage() {
  const { lang, t } = useLang();
  return (
    <PageShell
      title={whyMoneyMatters.title[lang]}
      subtitle={whyMoneyMatters.intro[lang]}
      back={{ href: '/learn', label: t('shell.learn') }}>
      {/* The reported county service series is tracked in #1017. */}
      <WhyThisMatters />
    </PageShell>
  );
}

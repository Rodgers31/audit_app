'use client';

import PageShell from '@/components/layout/PageShell';
import GovernmentExplorer from '@/components/learn/GovernmentExplorer';
import { useLang } from '@/lib/i18n/LangProvider';
import { GOVERNMENT_MESSAGES } from '@/lib/i18n/messages/government';

export default function GovernmentPage() {
  const { lang } = useLang();

  return (
    <PageShell
      title={GOVERNMENT_MESSAGES.title[lang]}
      subtitle={GOVERNMENT_MESSAGES.subtitle[lang]}
      back={{ href: '/learn', label: GOVERNMENT_MESSAGES.back[lang] }}>
      <GovernmentExplorer />
    </PageShell>
  );
}

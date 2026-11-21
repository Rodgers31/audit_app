'use client';

import AccountDashboard from '@/components/account/AccountDashboard';
import PageShell from '@/components/layout/PageShell';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import { ACCOUNT_MESSAGES as copy } from '@/lib/i18n/messages/account';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo } from 'react';

export default function AccountPage() {
  const { authUser, isLoading } = useAuth();
  const { lang } = useLang();
  const router = useRouter();
  const sections = useMemo(() => [
    { id: 'account-details', label: copy.details[lang] },
    { id: 'account-watchlist', label: copy.watchlist[lang] },
    { id: 'account-alerts', label: copy.alerts[lang] },
  ], [lang]);

  // Redirect unauthenticated users to home
  useEffect(() => {
    if (!isLoading && !authUser) {
      router.replace('/');
    }
  }, [isLoading, authUser, router]);

  if (isLoading) {
    return (
      <PageShell title={copy.title[lang]} breadcrumbs={false}>
        <p role='status' className='py-8 text-sm'>{copy.loading[lang]}</p>
      </PageShell>
    );
  }

  if (!authUser) return null;

  return (
    <PageShell title={copy.title[lang]} breadcrumbs={false} sections={sections}>
      <AccountDashboard key={authUser.id} accountId={authUser.id} />
    </PageShell>
  );
}

'use client';

import AccountDashboard from '@/components/account/AccountDashboard';
import SectionNavigation from '@/components/layout/SectionNavigation';
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

  if (!isLoading && !authUser) return null;

  return (
    <div className='min-h-screen bg-gov-sand pt-[var(--public-header-height)] text-neutral-text dark:bg-surface-sunken'>
      <div className='mx-auto max-w-screen-xl px-4 pb-8 pt-5 sm:px-6 md:pt-8'>
        <h1 className='audit-figure mb-4 text-[26px] uppercase leading-tight sm:text-audit-title'>
          {copy.title[lang]}
        </h1>
        {isLoading ? (
          <p role='status' className='py-8 text-sm'>{copy.loading[lang]}</p>
        ) : authUser && (
          <SectionNavigation sections={sections}>
            <div className='page-shell-content min-w-0'>
              <AccountDashboard key={authUser.id} accountId={authUser.id} />
            </div>
          </SectionNavigation>
        )}
      </div>
    </div>
  );
}

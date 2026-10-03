'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { AlertTriangle } from 'lucide-react';
import { Component, type ReactNode } from 'react';
import type { Tab } from '../shared';

/** Keep a rejected tab chunk from replacing the county shell with an app error. */
export default class TabErrorBoundary extends Component<
  { tab: Tab; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <TabLoadError tab={this.props.tab} /> : this.props.children;
  }
}

function TabLoadError({ tab }: { tab: Tab }) {
  const { t } = useLang();
  const reload = () => {
    // next/dynamic retains a rejected lazy Promise for this document. A
    // boundary reset or router.refresh cannot reliably retry that chunk.
    // Use the actual selection even if its router.replace has not committed.
    const url = new URL(window.location.href);
    if ((url.searchParams.get('tab') || 'overview') === tab) {
      // Replacing an identical URL with a hash can be a same-document
      // navigation, which would retain the rejected lazy payload.
      window.location.reload();
      return;
    }
    if (tab === 'overview') url.searchParams.delete('tab');
    else url.searchParams.set('tab', tab);
    window.location.replace(url.href);
  };

  return (
    <div role='alert' className='py-12 text-center text-gray-700 dark:text-neutral-text'>
      <AlertTriangle aria-hidden='true' size={28} className='mx-auto mb-2 text-amber-600 dark:text-amber-400' />
      <p className='text-sm'>{t('county.tab.load_error')}</p>
      <button type='button' onClick={reload}
        className='mt-3 min-h-11 rounded-lg border border-gray-300 dark:border-white/20 px-4 py-2 text-sm font-medium hover:bg-gray-50 dark:hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest'>
        {t('county.tab.reload')}
      </button>
    </div>
  );
}

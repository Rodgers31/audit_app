import type { Metadata } from 'next';
import { Suspense } from 'react';
import UnsubscribeFlow, { LoadingUnsubscribe } from './UnsubscribeFlow';
import { unsubscribeMessages } from './messages';

export const metadata: Metadata = {
  title: unsubscribeMessages.title.en,
  referrer: 'no-referrer',
};

export default function NewsletterUnsubscribePage() {
  return <Suspense fallback={<LoadingUnsubscribe />}><UnsubscribeFlow /></Suspense>;
}

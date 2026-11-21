import type { Metadata } from 'next';
import { SOURCES_MESSAGES } from '@/lib/i18n/messages/sources';
import SourcesPageClient from './SourcesPageClient';

export const metadata: Metadata = {
  title: SOURCES_MESSAGES.title.en,
  description: SOURCES_MESSAGES.intro.en,
};

export default function SourcesPage() {
  return <SourcesPageClient />;
}

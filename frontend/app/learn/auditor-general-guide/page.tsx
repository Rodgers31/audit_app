import type { Metadata } from 'next';
import { AUDITOR_GUIDE_MESSAGES } from '@/lib/i18n/messages/auditorGuide';
import AuditorGuide from './AuditorGuide';
import { findAuditorGuideStep } from './auditorGuideData';

export const metadata: Metadata = {
  title: { absolute: `${AUDITOR_GUIDE_MESSAGES.title.en} — AuditGava` },
  description: AUDITOR_GUIDE_MESSAGES.metadataDescription.en,
};

export default async function AuditorGuidePage({ searchParams }: {
  searchParams: Promise<{ step?: string | string[] }>;
}) {
  const { step } = await searchParams;
  return <AuditorGuide step={findAuditorGuideStep(step)} />;
}

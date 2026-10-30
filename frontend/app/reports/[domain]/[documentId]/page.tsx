import { Suspense } from 'react';
import ReportView, { ReportViewFallback } from './ReportView';

export default async function Page({ params }: { params: Promise<{ domain: string; documentId: string }> }) {
  const { domain, documentId } = await params;
  return <Suspense fallback={<ReportViewFallback />}><ReportView domain={domain} documentId={documentId} /></Suspense>;
}

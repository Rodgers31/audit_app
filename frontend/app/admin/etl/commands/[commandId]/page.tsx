'use client';
import { Suspense, use } from 'react';
import PageShell from '@/components/layout/PageShell';
import { CommandDetail } from './CommandDetail';

export default function CommandDetailPage({params}:{params:Promise<{commandId:string}>}) {
  const {commandId}=use(params);
  return <Suspense fallback={<PageShell title='Command receipt'><p>Loading receipt…</p></PageShell>}><CommandDetail commandId={commandId} /></Suspense>;
}

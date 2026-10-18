'use client';
/** Owned inert browser fixture, never routed by the product application. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
import GeneratedEvidence from '@/components/admin/social/GeneratedEvidence';
import styles from '@/components/admin/social/social.module.css';
export default function Harness() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  const path = usePathname();
  return <QueryClientProvider client={client}><main style={{ maxWidth: 1100, margin: 'auto', padding: 20, fontFamily: 'Arial, sans-serif' }}><p>OWNED INERT CONTRACT FIXTURE · NO LIVE CONNECTION</p>{path.endsWith('/review') ? <div className={styles.workspace}><GeneratedEvidence postId='00000000-0000-4000-8000-000000000010' revisionId='00000000-0000-4000-8000-000000000011' expectedVersion={1} /></div> : <SocialAutomation />}</main></QueryClientProvider>;
}

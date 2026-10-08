'use client';
/** Rendered production components/hooks/decoders with explicit inert auth/API fixtures. */
import SocialWorkspace, { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';
import { AdminGuard } from '@/lib/auth/admin';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

export default function SocialRuntimeHarness() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  const pathname = usePathname();
  const id = pathname.split('/')[3];
  return <QueryClientProvider client={client}><AdminGuard><main style={{ maxWidth: 1500, margin: 'auto', padding: 12 }}>
    <p>CONTRACT FIXTURES · INERT AUTH · NO PROVIDER OR STORAGE CONNECTION</p>
    {id === 'accounts' ? <MetaAccounts /> : id ? <SocialEditorPage postId={id === 'new' ? undefined : id} /> : <SocialWorkspace />}
  </main></AdminGuard></QueryClientProvider>;
}

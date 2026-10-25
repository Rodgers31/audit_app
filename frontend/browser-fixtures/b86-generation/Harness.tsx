'use client';
/** Launch with ./serve.mjs for inert auth and the owned local API transport. */
import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
export default function Harness() {
  const [client] = useState(() => new QueryClient({defaultOptions:{queries:{retry:false}}}));
  return <QueryClientProvider client={client}><main style={{maxWidth:1000,margin:'auto',padding:20,fontFamily:'Arial,sans-serif'}}><h1>Owned local native report fixture</h1><p>Retained official source replay; local transport, job and auth fixture. Actual native authority, PostgreSQL and API. Publishing and uploads off.</p><SocialAutomation /></main></QueryClientProvider>;
}

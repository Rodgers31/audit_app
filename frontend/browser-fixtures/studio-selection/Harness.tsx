'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import SocialStudio from '@/components/admin/social/SocialStudio';
export default function Harness() {
 const [client] = useState(() => new QueryClient({defaultOptions:{queries:{retry:false}}}));
 return <QueryClientProvider client={client}><main style={{maxWidth:1100,margin:'auto',padding:20,fontFamily:'Arial,sans-serif'}}><p>OWNED INERT FIXTURE · 21 SOURCES / 21 ASSETS · NO PROVIDER CONNECTION</p><SocialStudio/></main></QueryClientProvider>;
}

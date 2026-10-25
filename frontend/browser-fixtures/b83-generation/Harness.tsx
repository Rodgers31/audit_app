'use client';
/** Owned inert browser contract fixture; never routed by the application. */
import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GenerationPreview from '@/components/admin/social/GenerationPreview';
import GenerationOutcomes from '@/components/admin/social/GenerationOutcomes';
import { parseGenerationOutcome } from '@/lib/admin/ingestion';
import styles from '@/components/admin/social/social.module.css';
const metadata = {
  post_commit_generation: parseGenerationOutcome({state:'unavailable',execution_unverified:false,processed:3,drafts_created:0,baselines:1,unchanged:1,refused:1,reason:'source_evidence_ineligible',refusal_reasons:{publisher_date_receipt_unavailable:1}}),
  post_commit_report_generation: parseGenerationOutcome({state:'failed',reason:'generation_database_unavailable',execution_unverified:true,processed:null,drafts_created:null,baselines:null,unchanged:null,refused:null,confirmed:{processed:2,drafts_created:1,baselines:0,unchanged:0,refused:1},refusal_reasons:{publisher_date_receipt_unavailable:1}}),
};
export default function Harness() {
  const [client] = useState(() => new QueryClient({defaultOptions:{queries:{retry:false}}}));
  return <QueryClientProvider client={client}><main style={{maxWidth:1000,margin:'auto',padding:20,fontFamily:'Arial,sans-serif'}}><h1>OWNED INERT B83 FIXTURE</h1><p>No live source, provider, credentials, publishing or upload connection.</p><div className={styles.workspace}><GenerationPreview /><GenerationOutcomes metadata={metadata} /></div></main></QueryClientProvider>;
}

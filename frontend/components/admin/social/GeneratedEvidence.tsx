'use client';
import { useState } from 'react';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { decodeDecision, describeShadowReason, ShadowDecision } from '@/lib/api/socialGeneration';
import { useQuery } from '@tanstack/react-query';
import { generationApi, EvidenceReport } from '@/lib/api/socialGeneration';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useAdmin } from '@/lib/auth/admin';
import { httpsUrl } from './socialDocument';
import { SocialErrorBanner } from './SocialNotice';
import styles from './social.module.css';

function ReportSource({ report }: { report: EvidenceReport }) {
  return <article className={styles.fields} aria-label='Neutral report evidence'>
    <strong>{report.publisher} report · {report.entity}</strong>
    <p>Reporting period: {report.period} ({report.period_start} to {report.period_end})</p>
    {report.evidence_kind === 'publisher_catalogue' ? <>
      <p>Official KRA catalogue entry date: {report.catalogued_on}. Report publication date is not stated.</p>
      <p>Catalogue evidence only. Human review required; automatic approval is unavailable.</p>
      {httpsUrl(report.catalogue_url) && <a href={httpsUrl(report.catalogue_url)} target='_blank' rel='noopener noreferrer'>Open official catalogue entry</a>}
    </> : <p>Published {report.published_on}</p>}
    <p>{report.locator}</p>
    <p>This announcement describes the source report. Financial claims require separate evidence and review.</p>
    {httpsUrl(report.document_url) && <a href={httpsUrl(report.document_url)} target='_blank' rel='noopener noreferrer'>Open publisher report</a>}
    <details><summary>Report verification details</summary><div>
      <p>Retrieved {report.retrieved_at} · Verified {report.verified_at}</p>
      <p>Document {report.source_document_id} · {report.evidence_kind === 'publisher_catalogue' ? 'Catalogue availability evidence' : 'Publication evidence'} {report.publication_extraction_id} · Qualified scope evidence {report.qualification_extraction_id}</p>
      <p className={styles.diagnostic}>Checksum: {report.document_checksum}</p>
    </div></details>
  </article>;
}

export default function GeneratedEvidence({ postId, revisionId, expectedVersion }: { postId: string; revisionId: string; expectedVersion: number }) {
  const { user } = useAuth(); const { isAdmin } = useAdmin();
  const [diagnostics, setDiagnostics] = useState(false);
  const result = useQuery({ queryKey: ['admin', 'social', user?.id, 'evidence', postId, revisionId], queryFn: ({ signal }) => generationApi.evidence(postId, revisionId, signal), enabled: isAdmin, staleTime: 60_000, retry: false, refetchOnWindowFocus: false });
  const rules = useQuery({ queryKey: ['admin', 'social', user?.id, 'generation', 'rules', 1], queryFn: ({ signal }) => generationApi.rules(1, signal), enabled: isAdmin && diagnostics, retry: false, refetchOnWindowFocus: false });
  const [selected, setSelected] = useState(''); const [decision, setDecision] = useState<ShadowDecision>(); const mutation = useSocialMutation();
  async function evaluate() { const r = rules.data?.items.find(r => `${r.id}:${r.version}` === selected); if (!r) return; try { setDecision(await mutation.run(`/posts/${postId}/shadow`, { expected_version: expectedVersion, revision_id: revisionId, rule_id: r.id, rule_version: r.version }, decodeDecision, { postId })); } catch { /* Keep the typed command error. */ } }
  return <details className={styles.evidence}>
    <summary>Review source evidence</summary>
    <section className={styles.fields} aria-label='Generated factual evidence'>
      <h3>Generated factual evidence</h3><p>Check these facts against the post and the original source. Evidence belongs to this saved revision; edits require a new review. Human approval remains required.</p>
      {result.isPending && <p role='status'>Loading immutable evidence…</p>}
      {result.error && <SocialErrorBanner error={result.error} onRetry={() => result.refetch()} />}
      {result.data && <>
        {result.data.evidence.source?.report && <ReportSource report={result.data.evidence.source.report} />}
        {result.data.evidence.source?.facts.map(f => <article key={f.fact_id} className={styles.fact}>
          <strong>{f.entity}: {f.metric}</strong>
          <p className={styles.factValue}>{f.value} {f.unit}{f.scale !== 'units' ? ` (${f.scale})` : ''}</p>
          <p>{f.period} · {f.classification}</p><p>Basis: {f.comparison_basis}</p>
          <p>{f.publisher} · Published {f.published_on} · {f.locator}</p>
          {httpsUrl(f.document_url) && <a href={httpsUrl(f.document_url)} target='_blank' rel='noopener noreferrer'>Open supporting source</a>}
          <details><summary>Figure verification details</summary><div><p>Retrieved {f.retrieved_at} · Verified {f.verified_at}</p><p className={styles.diagnostic}>Checksum: {f.document_checksum}</p></div></details>
        </article>)}
        <details onToggle={e => setDiagnostics(e.currentTarget.open)}><summary>Advanced evidence & policy diagnostics</summary><div className={styles.fields}>
          <p>Evidence version {result.data.evidence.evidence_version} · Template {result.data.generator_metadata?.template_version} · Event {result.data.source_event_id}</p>
          <p className={styles.diagnostic}>Source {result.data.evidence.source?.source_type} · {result.data.evidence.source?.source_key} · Ingestion {result.data.evidence.source?.ingestion_id}</p>
          {result.data.evidence.source?.financial && <article aria-label='Financial source authority' className={styles.fields}>
            <strong>Financial source authority · {result.data.evidence.source.financial.native_domain}</strong>
            <p>Source record {result.data.evidence.source.financial.record_id} · Publisher report evidence {result.data.evidence.source.financial.report_record_id}</p>
            <p>Reporting scope {result.data.evidence.source.financial.period_start} to {result.data.evidence.source.financial.period_end} · Published {result.data.evidence.source.financial.published_on}</p>
            <p className={styles.diagnostic}>Authority: {result.data.evidence.source.financial.authority_fingerprint}</p>
          </article>}
          <label>Shadow rule version<select value={selected} onChange={e => { setSelected(e.target.value); setDecision(undefined); }}><option value=''>Choose a rule version</option>{rules.data?.items.map(r => <option key={`${r.id}:${r.version}`} value={`${r.id}:${r.version}`}>{r.definition.name} v{r.version} · {r.definition.mode}</option>)}</select></label>
          <button type='button' className={styles.button} disabled={!selected || mutation.isPending} onClick={evaluate}>Inspect shadow decision</button>
          {rules.error && <SocialErrorBanner error={rules.error} onRetry={() => rules.refetch()} />}{mutation.error && <SocialErrorBanner error={mutation.error} />}
          {decision && <div role='status'><p>{decision.outcome === 'would_allow' ? 'Would allow — human approval still required' : 'Human review required'}</p><p>{decision.reasons.map(describeShadowReason).join(' ')}</p><p className={styles.diagnostic}>Evaluated {decision.created_at}. Rule hash: {decision.rule_hash}</p></div>}
        </div></details>
      </>}
    </section>
  </details>;
}

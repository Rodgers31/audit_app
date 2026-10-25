import Link from 'next/link';
import { describeGenerationReason } from '@/lib/socialGenerationReasons';

export default function GenerationOutcomes({ metadata }: { metadata: Record<string, unknown> }) {
  return <section aria-label='Generation outcomes' className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-5 shadow-surface'>
    <h2 className='font-display text-lg text-neutral-text'>Draft generation outcomes</h2>
    <p>Ingestion completion and draft creation are separate. Publishing and uploads require their own authorization.</p>
    {(['post_commit_generation', 'post_commit_report_generation'] as const).map(key => {
      const value = metadata[key] as Record<string, unknown> | undefined;
      return <article key={key} className='mt-4'>
        <h3>{key === 'post_commit_generation' ? 'Financial drafts' : 'Neutral report drafts'}</h3>
        {!value ? <p>No generation receipt recorded for this job. Its outcome is unknown.</p> : <>
          <p>{describeGenerationReason(value.reason)}</p>
          {value.execution_unverified ? <p>Execution is unverified. Counters are unknown; inspect existing drafts before retrying.</p> :
            <p>Processed {String(value.processed)} · Drafts created {String(value.drafts_created)} · Baselines {String(value.baselines)} · Unchanged {String(value.unchanged)} · Refused {String(value.refused)}</p>}
          {value.confirmed && typeof value.confirmed === 'object' ? <p>Confirmed before uncertainty: {String((value.confirmed as Record<string, unknown>).processed)} processed · {String((value.confirmed as Record<string, unknown>).drafts_created)} drafts. The current record may also have committed.</p> : null}
          {value.refusal_reasons && typeof value.refusal_reasons === 'object' ? <ul aria-label={value.execution_unverified ? 'Confirmed refusals before uncertainty' : 'Evidence refusals'}>{Object.entries(value.refusal_reasons).map(([reason, count]) => <li key={reason}>{describeGenerationReason(reason)} ({String(count)})</li>)}</ul> : null}
        </>}
      </article>;
    })}
    <Link href='/admin/social/automation'>Preview committed evidence and inspect draft controls</Link>
  </section>;
}

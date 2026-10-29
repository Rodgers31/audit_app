'use client';
import PageShell from '@/components/admin/AdminPageShell';
import styles from '@/components/admin/admin.module.css';
import api from '@/lib/api/axios';
import { useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { decodeAudit, timeAgo } from '@/lib/admin/audit';
import { decodeFailures, decodeHealth, decodeIngestion, decodeSchedule, decodeSocial, decodeUsers, socialWorkerEvidence } from '@/lib/admin/overview';
import { sourceLabel } from '@/lib/admin/sourceLabels';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
export default function AdminOverviewPage() {
  const { isAdmin } = useAdmin();
  const { user } = useAuth();
  const actorId = isAdmin ? user?.id ?? null : null;
  const enabled = isAdmin && !!actorId;
  const ingestion = useQuery<ReturnType<typeof decodeIngestion>>({
    queryKey: ['admin', 'ingestion-stats', actorId, 7],
    queryFn: async ({ signal }) =>
      decodeIngestion((await api.get('/admin/ingestion-jobs/stats/summary', { params: { days: 7 }, signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 30_000,
  });

  const schedule = useQuery<ReturnType<typeof decodeSchedule>>({
    queryKey: ['admin', 'etl-schedule-summary', actorId],
    queryFn: async ({ signal }) => decodeSchedule((await api.get('/admin/etl/schedule/summary', { signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 60_000,
  });

  const health = useQuery<ReturnType<typeof decodeHealth>>({
    queryKey: ['admin', 'etl-health', actorId],
    queryFn: async ({ signal }) => decodeHealth((await api.get('/admin/etl/health', { signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 60_000,
  });

  const userStats = useQuery<ReturnType<typeof decodeUsers>>({
    queryKey: ['admin', 'user-stats', actorId],
    queryFn: async ({ signal }) => decodeUsers((await api.get('/admin/users/stats', { signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 60_000,
  });

  const recentActions = useQuery<ReturnType<typeof decodeAudit>>({
    queryKey: ['admin', 'audit-log', actorId, { recent: true }],
    queryFn: async ({ signal }) =>
      decodeAudit((await api.get('/admin/audit-log', { params: { page_size: 5, days: 30 }, signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 30_000,
  });

  const failedJobs = useQuery<ReturnType<typeof decodeFailures>>({
    queryKey: ['admin', 'ingestion-jobs', actorId, 'failed'],
    queryFn: async ({ signal }) =>
      decodeFailures((
        await api.get('/admin/ingestion-jobs', {
          params: { status: 'failed', days: 7, page_size: 5 }, signal, headers: { 'Cache-Control': 'no-store' }
        })
      ).data),
    enabled, retry: false, gcTime: 0,
    staleTime: 30_000,
    // Refetch every 60s so the alerts banner reflects new failures without
    // a full page reload.
    refetchInterval: 60_000,
  });

  const social = useQuery({
    queryKey: ['admin', 'overview-social-status', actorId],
    queryFn: async ({ signal }) => decodeSocial((await api.get('/admin/social/system/status', { signal, headers: { 'Cache-Control': 'no-store' } })).data),
    enabled, retry: false, gcTime: 0, staleTime: 30_000, refetchInterval: 60_000,
  });
  const queries = [ingestion, schedule, health, userStats, recentActions, failedJobs, social];
  if (!enabled) return <PageShell title='Overview'><p>{isAdmin ? 'Verifying your session…' : 'Admin access required.'}</p></PageShell>;
  const taskStatus = <T,>(q: {error: unknown; data: T | undefined}, describe: (data: T) => string) => q.error ? 'Evidence unavailable. Open this task to retry.' : q.data ? describe(q.data) : 'Checking current evidence…';
  return <PageShell title='What needs doing?' subtitle='Review posts, check data updates, and follow work through to its recorded outcome.'>
    <div className={styles.workspace}>
      <section className={styles.panel} aria-labelledby='work-heading'>
        <div className={styles.sectionHeading}><div><h2 id='work-heading'>Your work</h2><p>Choose a task to see its evidence and available actions.</p></div><button className={styles.button} disabled={queries.some(q => q.isFetching)} onClick={() => queries.forEach(q => void q.refetch())}>Refresh overview</button></div>
        <div className={styles.taskList}>
          <Link href='/admin/social' className={styles.task}><div><strong>Review social drafts</strong><p>{taskStatus(social, d => `${d.publishing_enabled ? 'Publishing enabled' : 'Publishing paused'}. Worker evidence: ${socialWorkerEvidence(d.worker)}. Open the queue for posts needing review.`)}</p></div><span className={styles.taskAction}>Open queue →</span></Link>
          <Link href='/admin/ingestion' className={styles.task}><div><strong>Check data updates</strong><p>{taskStatus(ingestion, d => `${d.total_jobs} jobs in the last 7 days · ${d.failed} failed · ${d.completed_with_errors} completed with errors. Data completion and draft creation are separate.`)}</p></div><span className={styles.taskAction}>Check updates →</span></Link>
          <Link href='/admin/etl' className={styles.task}><div><strong>Run or recover a data check</strong><p>Verify the dedicated worker, inspect accepted commands, or recover an uncertain request.</p></div><span className={styles.taskAction}>Run & recover →</span></Link>
          <Link href='/admin/users' className={styles.task}><div><strong>Manage people and access</strong><p>{taskStatus(userStats, d => `${d.total_users} ${d.total_users===1?'account':'accounts'} · ${d.admin_users} ${d.admin_users===1?'administrator':'administrators'}. Find a person before changing access.`)}</p></div><span className={styles.taskAction}>Find a person →</span></Link>
          <Link href='/admin/audit-log' className={styles.task}><div><strong>Look up a recorded action</strong><p>Inspect who changed what and when. Social posts have their own delivery history.</p></div><span className={styles.taskAction}>Open activity →</span></Link>
        </div>
      </section>
      {!health.error&&health.data?.plan_status==='unavailable'&&<div role='alert' className={styles.notice}><strong>Calendar calculation unavailable</strong><p>Check the current worker and command evidence before requesting a data check.</p><Link className={styles.button} href='/admin/etl'>Open Run & recover</Link></div>}
      {failedJobs.error ? <div role='status' className={styles.notice}>Recent failures could not be checked. <Link href='/admin/ingestion?status=failed'>Review data updates</Link></div> : !!failedJobs.data?.total && <section className={styles.panel}><div className={styles.sectionHeading}><div><h2>Updates needing attention</h2><p>{failedJobs.data.total} failed {failedJobs.data.total===1?'job':'jobs'} in the last 7 days. Full diagnostics remain in dedicated runner logs.</p></div><Link className={styles.button} href='/admin/ingestion?status=failed'>View failures</Link></div><div className={styles.taskList}>{failedJobs.data.jobs.map(job => <Link key={job.id} className={styles.task} href={`/admin/ingestion/${job.id}`}><div><strong>{sourceLabel(job.domain)}</strong><p>Job #{job.id} · {timeAgo(job.created_at)}</p></div><span className={styles.taskAction}>Inspect outcome →</span></Link>)}</div></section>}
      <div className={styles.split}>
        <section className={styles.panel}><div className={styles.sectionHeading}><div><h2>Recent recorded actions</h2><p>Missing records do not establish that nothing happened.</p></div><Link className={styles.button} href='/admin/audit-log'>All activity</Link></div>{recentActions.error ? <p role='status'>Audit evidence unavailable.</p> : !recentActions.data ? <p>Loading recorded actions…</p> : recentActions.data.entries.length === 0 ? <p>No actions recorded in this view.</p> : <ul>{recentActions.data.entries.map(entry => <li key={entry.id} className='py-3 border-b border-neutral-border'><strong>{entry.action.replaceAll('_', ' ')}</strong><p className={styles.quiet}>{entry.actor_email ?? entry.actor_id} · {timeAgo(entry.created_at)}</p></li>)}</ul>}</section>
        <details className={styles.disclosure}><summary>Calendar and system evidence</summary><div><p>{taskStatus(schedule, d => `${d.running_today} of ${d.total_sources} sources due by calendar.`)}</p><p>{taskStatus(health, d => `Calendar calculation: ${d.plan_status}.`)}</p><p className={styles.quiet}>Calendar planning does not prove worker execution or current financial data.</p><Link className={styles.button} href='/status'>Inspect system status</Link></div></details>
      </div>
    </div>
  </PageShell>;
}

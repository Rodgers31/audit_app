/** No network implementation is present: unlisted paths and all writes refuse. */
const sources = ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'];
export default {
  async get(path: string, config?: { signal?: AbortSignal }) {
    const mode = new URLSearchParams(location.search).get('data');
    await new Promise<void>((resolve, reject) => {
      const cancel = () => { clearTimeout(timer); reject(new Error('Inert request cancelled')); };
      const timer = setTimeout(() => { config?.signal?.removeEventListener('abort', cancel); resolve(); }, mode === 'slow' ? 1400 : 40);
      config?.signal?.addEventListener('abort', cancel, { once: true });
      if (config?.signal?.aborted || mode === 'cancelled') cancel();
    });
    if (mode === 'failed') throw new Error('Inert unavailable evidence');
    const timestamp = new Date().toISOString();
    const responses: Record<string, unknown> = {
      '/admin/ingestion-jobs/stats/summary': { total_jobs: 0, completed: 0, failed: 0, running: 0, pending: 0, completed_with_errors: 0, total_items_processed: 0, total_items_created: 0, total_items_updated: 0, domains: {} },
      '/admin/etl/schedule/summary': { timestamp, running_today: 0, skipping_today: 6, total_sources: 6, efficiency: { vs_fixed_schedule: 'Inert fixture' }, sources_to_run: [] },
      '/admin/etl/health': { timestamp, scheduler_status: 'unverified', plan_status: 'available', worker_status: 'unverified', data_freshness: 'unverified', manual_trigger: { available: false, reason: 'Inert fixture' } },
      '/admin/users/stats': { total_users: 2, admin_users: 1, new_last_7_days: 0, new_last_30_days: 1 },
      '/admin/audit-log': { entries: [], total: 0, page: 1, page_size: 5, has_more: false, snapshot_id: 0, as_of: timestamp },
      '/admin/ingestion-jobs': { jobs: [], total: 0, page: 1, page_size: 5, has_more: false },
      '/admin/social/system/status': { publishing_enabled: false, worker: { state: 'unavailable', heartbeat_at: null, last_scan_at: null }, queue_counts: {} },
      '/admin/etl/schedule': { timestamp, evidence: 'calendar_plan', manual_trigger: { available: false, reason: 'Inert fixture' }, summary: {
        sources_running_today: 0, sources_skipping_today: 6, total_sources: 6, skip_percentage: 100,
        efficiency_vs_fixed_schedule: 'Inert fixture', sources_to_run: [], sources_not_running: sources,
      }, sources: Object.fromEntries(sources.map(source => [source, { should_run: false, reason: 'Inert fixture', next_run: null, next_reason: 'Inert fixture', current_period: 'fixture' }])) },
      '/admin/etl/dispatch': { timestamp, evidence: 'worker_dispatch', available: false, reason: 'Inert fixture', generation: null,
        worker: { status: 'unavailable', last_seen_at: null, expires_at: null },
        sources: Object.fromEntries(sources.map(source => [source, { available: false, reason: 'Inert fixture' }])) },
      '/admin/etl/commands': { entries: [], total: 0, page: 1, page_size: 20, has_more: false },
    };
    if (!Object.hasOwn(responses, path)) throw new Error('Unlisted inert read refused');
    return { data: responses[path] };
  },
  async post() { throw new Error('All fixture writes refused'); },
};

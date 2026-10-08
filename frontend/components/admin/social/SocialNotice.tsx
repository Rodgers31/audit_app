import { SocialApiError, toSocialError } from '@/lib/api/social';
import styles from './social.module.css';

export function SocialErrorBanner({ error, onRetry, id, context = 'post' }: { error: unknown; onRetry?: () => void; id?: string; context?: 'post' | 'controls' | 'schedule' }) {
  const e: SocialApiError = toSocialError(error);
  return <div className={`${styles.notice} ${styles.error}`} role='alert' id={id}>
    <p><strong>{e.code.replaceAll('_', ' ')}</strong> · {e.message}</p>
    {!!(e.fieldErrors.length + e.targetErrors.length) && <ul>{[...e.fieldErrors, ...e.targetErrors].map((issue, index) => <li key={index}>{issue.field ? `${issue.field}: ` : ''}{issue.message}</li>)}</ul>}
    {e.code === 'VERSION_CONFLICT' && <p>{context === 'controls' ? 'Publishing controls changed. Refresh system status before submitting the control change again.' : context === 'schedule' ? 'The post or authorization changed. Refresh the revision and results, then load the current revision before adjusting its schedule.' : 'Another admin changed this post. Your edits remain here. Load the current revision before applying them again.'}</p>}
    {e.code === 'TARGET_VALIDATION_FAILED' && <p>{context === 'schedule' ? 'The affected unsent destinations need attention. Changes to content or account selection require a new reviewed revision.' : 'All selected destinations must pass. Fix the affected version or explicitly deselect its account; no destination has been silently removed.'}</p>}
    {e.code === 'PUBLISHING_PAUSED' && <p>The draft is preserved. Publishing must be enabled before another publication command.</p>}
    {e.requestId && <p className={styles.muted}>Support request: {e.requestId}</p>}
    {onRetry && <button type='button' className={styles.button} onClick={onRetry}>Retry request</button>}
  </div>;
}

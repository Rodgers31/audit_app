import { DocumentTarget, SocialAccount, SocialContent, TargetValidation } from '@/lib/api/social';
import { httpsUrl, platformLabels, resolveContent } from './socialDocument';
import styles from './social.module.css';

export default function SocialPreview({ master, target, account, validation }: { master: SocialContent; target?: DocumentTarget; account?: SocialAccount; validation?: TargetValidation }) {
  const content = resolveContent(master, target);
  const resolved = validation?.resolved_preview;
  const text = typeof resolved?.text === 'string' ? resolved.text : content.text;
  const link = resolved && ('link' in resolved) ? (typeof resolved.link === 'string' ? resolved.link : null) : content.link;
  const inspected = resolved?.assets ?? [];
  return <section className={styles.preview} aria-label='Resolved post preview'>
    <div className={styles.previewAccount}><span className={styles.avatar} aria-hidden='true'>AG</span><div><strong>{account?.display_name ?? 'Master content'}</strong><p className={styles.muted}>{account ? `${account.handle ?? 'Handle unavailable'} · ${platformLabels[account.platform]}` : 'Select a connected account to preview its version'}</p></div></div>
    {content.media.length > 0 && <ul className={styles.mediaList} aria-label='Preview media references'>{content.media.map((asset, index) => {
      const metadata = inspected.find(item => item.asset_id === asset.asset_id);
      return <li className={styles.mediaItem} key={`${asset.asset_id}-${index}`}><strong>Media {index + 1}</strong><span className={styles.mediaId}>Asset {asset.asset_id}</span><p>{asset.alt_text || 'No alt text supplied'}</p>{asset.caption_asset_id && <p className={styles.muted}>Caption asset: {asset.caption_asset_id}</p>}{metadata && <p className={styles.muted}>Server-inspected {typeof metadata.mime_type === 'string' ? metadata.mime_type : 'media'}{typeof metadata.width === 'number' && typeof metadata.height === 'number' ? ` · ${metadata.width} × ${metadata.height}` : ''}{typeof metadata.byte_size === 'number' ? ` · ${metadata.byte_size} bytes` : ''}</p>}<p className={styles.muted}>Asset reference only. The server verifies readiness; image/video retrieval is unavailable.</p></li>;
    })}</ul>}
    <p className={styles.copy}>{text || 'Your post text will appear here.'}</p>
    {!!content.hashtags.length && <p className={styles.copy}>{content.hashtags.join(' ')}</p>}
    {link && <p className={styles.copy}>{httpsUrl(link) ? <a href={httpsUrl(link)} target='_blank' rel='noopener noreferrer'>{link}</a> : link}</p>}
    {account?.platform === 'instagram' && link && <p className={styles.muted}>Caption URLs may not be clickable on Instagram.</p>}
    {account?.platform === 'tiktok' && <p className={styles.muted}>TikTok access and consent must pass backend validation.</p>}
    {account?.platform === 'x' && <p className={styles.muted}>X uses weighted text rules and may require paid access. Backend validation is authoritative.</p>}
    <p className={`${styles.muted} ${styles.previewFooter}`}>Approximate preview. The platform controls final presentation. {validation ? 'Saved revision checked by the server.' : 'Local preview; validation required.'}</p>
  </section>;
}

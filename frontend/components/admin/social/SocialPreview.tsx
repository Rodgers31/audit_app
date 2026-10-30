import { DocumentTarget, SocialAccount, SocialContent, TargetValidation } from '@/lib/api/social';
import { auditgavaUrl, platformLabels, postDestinationIssue, resolveContent } from './socialDocument';
import styles from './social.module.css';
import AssetPreview from './media/AssetPreview';
import { xWeightedLength, threadsConservativeLength } from '@/lib/socialPlatformCounters';

export default function SocialPreview({ master, target, account, validation }: { master: SocialContent; target?: DocumentTarget; account?: SocialAccount; validation?: TargetValidation }) {
  const content = resolveContent(master, target);
  const resolved = validation?.resolved_preview;
  const text = typeof resolved?.text === 'string' ? resolved.text : content.text;
  const link = resolved && ('link' in resolved) ? (typeof resolved.link === 'string' ? resolved.link : null) : content.link;
  const safeLink = auditgavaUrl(link);
  const inspected = resolved?.assets ?? [];
  const rendered = [text, content.hashtags.map(tag => tag.startsWith('#') ? tag : '#' + tag).join(' '), link].filter(Boolean).join('\n\n');
  const xCount = account?.platform === 'x' ? xWeightedLength(rendered) : undefined;
  const threadsCount = account?.platform === 'threads' ? threadsConservativeLength(rendered) : undefined;
  const destinationIssue = postDestinationIssue(content);
  return <section className={styles.preview} aria-label='Resolved post preview'>
    <div className={styles.previewAccount}><span className={styles.avatar} aria-hidden='true'>AG</span><div><strong>{account?.display_name ?? 'Master content'}</strong><p className={styles.muted}>{account ? `${account.handle ?? 'Handle unavailable'} · ${platformLabels[account.platform]}` : 'Select a connected account to preview its version'}</p></div></div>
    {content.media.length > 0 && <ul className={styles.mediaList} aria-label='Preview media references'>{content.media.map((asset, index) => {
      const metadata = inspected.find(item => item.asset_id === asset.asset_id);
      return <li className={styles.mediaItem} key={`${asset.asset_id}-${index}`}><strong>Media {index + 1}</strong><span className={styles.mediaId}>Asset {asset.asset_id}</span><AssetPreview id={asset.asset_id} alt={asset.alt_text} /><p>{asset.alt_text || 'No alt text supplied'}</p>{asset.caption_asset_id && <p className={styles.muted}>Caption asset: {asset.caption_asset_id}</p>}{metadata && <p className={styles.muted}>Server-inspected {typeof metadata.mime_type === 'string' ? metadata.mime_type : 'media'}{typeof metadata.width === 'number' && typeof metadata.height === 'number' ? ` · ${metadata.width} × ${metadata.height}` : ''}{typeof metadata.byte_size === 'number' ? ` · ${metadata.byte_size} bytes` : ''}</p>}</li>;
    })}</ul>}
    <p className={styles.copy}>{text || 'Your post text will appear here.'}</p>
    {!!content.hashtags.length && <p className={styles.copy}>{account?.platform === 'threads' ? `Topic: ${content.hashtags[0].replace(/^#/, '')}` : content.hashtags.map(tag => tag.startsWith('#') ? tag : '#'+tag).join(' ')}</p>}
    {link && <div className={styles.destination}><span className={styles.muted}>Post destination</span><p className={styles.copy}>{safeLink ? <a href={safeLink} target='_blank' rel='noopener noreferrer'>{link}</a> : link}</p></div>}
    {account?.platform === 'instagram' && link && <p className={styles.muted}>Caption URLs may not be clickable on Instagram.</p>}
    {account?.platform === 'tiktok' && <p className={styles.muted}>TikTok {target?.tiktok_options?.mode === 'draft' ? 'draft inbox delivery requires completion in TikTok and is never a public success.' : 'direct publication requires approved product access, explicit privacy and consent.'}</p>}
    {destinationIssue && <p className={styles.notice}>{destinationIssue}</p>}
    {xCount && <p className={styles.muted} aria-live='polite'>{xCount.length === null ? `X counter unavailable: ${xCount.error}` : `${xCount.length} / 280 weighted X characters, including hashtags and link.`} Paid access and a reserved budget are required.</p>}
    {threadsCount && <p className={styles.muted} aria-live='polite'>{threadsCount.length === null ? threadsCount.error : `${threadsCount.length} / 500 UTF-8 bytes · conservative application limit.`} The selected tag is sent as the Threads topic. Owned-post confirmation does not prove public visibility.</p>}
    <p className={`${styles.muted} ${styles.previewFooter}`}>Approximate preview. The platform controls final presentation. {validation ? 'Saved revision checked by the server.' : 'Local preview; validation required.'}</p>
  </section>;
}

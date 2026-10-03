import { MediaReference } from '@/lib/api/social';
import { useId } from 'react';
import styles from './social.module.css';

export default function SocialMedia({ media, onChange, label }: { media: MediaReference[]; onChange: (media: MediaReference[]) => void; label: string }) {
  const descriptionId = useId();
  function move(index: number, delta: number) {
    const next = [...media]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; onChange(next);
  }
  return <div className={styles.fields}>
    <div className={styles.actions}><button type='button' className={styles.button} disabled aria-describedby={descriptionId}>Upload media</button><button type='button' className={styles.button} disabled aria-describedby={descriptionId}>Choose from library</button></div>
    <p className={styles.muted} id={descriptionId}>Media uploads and the storage library are unavailable in this batch. Existing asset references are retained and checked by the server.</p>
    {!media.length && <p className={styles.muted}>No media references selected.</p>}
    <ol className={styles.mediaList}>{media.map((asset, index) => <li className={styles.mediaItem} key={`${asset.asset_id}-${index}`}>
      <span className={styles.mediaId}>{index + 1}. Asset {asset.asset_id}</span>
      <label>{label} media {index + 1} alt text<input value={asset.alt_text ?? ''} onChange={e => onChange(media.map((item, i) => i === index ? { ...item, alt_text: e.target.value } : item))} /></label>
      {asset.caption_asset_id && <p className={styles.muted}>Caption asset: {asset.caption_asset_id}</p>}
      <div className={styles.mediaControls}><button type='button' className={styles.button} disabled={index === 0} aria-label={`Move ${label} media ${index + 1} earlier`} onClick={() => move(index, -1)}>Earlier</button><button type='button' className={styles.button} disabled={index === media.length - 1} aria-label={`Move ${label} media ${index + 1} later`} onClick={() => move(index, 1)}>Later</button><button type='button' className={styles.button} aria-label={`Remove ${label} media ${index + 1}`} onClick={() => onChange(media.filter((_, i) => i !== index))}>Remove</button></div>
    </li>)}</ol>
  </div>;
}

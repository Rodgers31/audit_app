'use client';
import { MediaReference } from '@/lib/api/social';
import { MediaAsset } from '@/lib/api/socialMedia';
import { useMediaCapabilities } from '@/lib/hooks/useSocialMedia';
import { useEffect, useId, useRef, useState } from 'react';
import MediaPicker from './media/MediaPicker';
import MediaUpload from './media/MediaUpload';
import AssetPreview from './media/AssetPreview';
import styles from './social.module.css';

export default function SocialMedia({ media, onChange, label, contextKey = label, onBusyChange }: { media: MediaReference[]; onChange: (media: MediaReference[]) => void; label: string; contextKey?: string; onBusyChange?: (busy: boolean) => void }) {
  const descriptionId = useId();
  const capabilities = useMediaCapabilities();
  const [mode, setMode] = useState<'upload' | 'library'>();
  const [busy, setBusy] = useState(false);
  const current = useRef({ media, onChange, contextKey, onBusyChange });
  current.current = { media, onChange, contextKey, onBusyChange };
  useEffect(() => () => current.current.onBusyChange?.(false), []);
  function uploadBusy(value: boolean) { setBusy(value); current.current.onBusyChange?.(value); }
  function select(asset: MediaAsset) {
    if (asset.state !== 'ready') return;
    const latest = current.current;
    if (!latest.media.some(item => item.asset_id === asset.id)) latest.onChange([...latest.media, { asset_id: asset.id, alt_text: asset.default_alt_text, caption_asset_id: null }]);
    setMode(undefined); setBusy(false);
  }
  function move(index: number, delta: number) {
    const next = [...media]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; onChange(next);
  }
  return <div className={styles.fields}>
    <div className={styles.actions}><button type='button' className={styles.button} disabled={busy || !capabilities.data?.upload_available} aria-expanded={mode === 'upload'} aria-describedby={descriptionId} onClick={() => setMode(mode === 'upload' ? undefined : 'upload')}>Upload media</button><button type='button' className={styles.button} disabled={busy || !capabilities.data?.library_available} aria-expanded={mode === 'library'} aria-describedby={descriptionId} onClick={() => setMode(mode === 'library' ? undefined : 'library')}>Choose from library</button></div>
    <p className={styles.muted} id={descriptionId}>{capabilities.isPending ? 'Checking private media availability…' : capabilities.error ? 'The private media service is unavailable. Existing references are retained.' : capabilities.data?.unavailable_reason ?? 'Select inspected media or upload an original file. Ready media can be reused across posts.'}</p>
    {capabilities.error && <button type='button' className={styles.button} onClick={() => void capabilities.refetch()}>Retry media availability</button>}
    {mode === 'upload' && capabilities.data && <MediaUpload contextKey={contextKey} capabilities={capabilities.data} onSelect={select} onClose={() => setMode(undefined)} onBusy={uploadBusy} />}
    {mode === 'library' && <MediaPicker selected={media.map(item => item.asset_id)} onSelect={select} onClose={() => setMode(undefined)} />}
    {!media.length && <p className={styles.muted}>No media references selected.</p>}
    <ol className={styles.mediaList}>{media.map((asset, index) => <li className={styles.mediaItem} key={`${asset.asset_id}-${index}`}>
      <span className={styles.mediaId}>{index + 1}. Asset {asset.asset_id}</span>
      <AssetPreview id={asset.asset_id} alt={asset.alt_text} />
      <label>{label} media {index + 1} alt text<input maxLength={2000} disabled={busy} value={asset.alt_text ?? ''} onChange={e => onChange(media.map((item, i) => i === index ? { ...item, alt_text: e.target.value } : item))} /></label>
      {asset.caption_asset_id && <p className={styles.muted}>Caption asset: {asset.caption_asset_id}</p>}
      <div className={styles.mediaControls}><button type='button' className={styles.button} disabled={busy || index === 0} aria-label={`Move ${label} media ${index + 1} earlier`} onClick={() => move(index, -1)}>Earlier</button><button type='button' className={styles.button} disabled={busy || index === media.length - 1} aria-label={`Move ${label} media ${index + 1} later`} onClick={() => move(index, 1)}>Later</button><button type='button' className={styles.button} disabled={busy} aria-label={`Remove ${label} media ${index + 1}`} onClick={() => onChange(media.filter((_, i) => i !== index))}>Remove</button></div>
    </li>)}</ol>
  </div>;
}

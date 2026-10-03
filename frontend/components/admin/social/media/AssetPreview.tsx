'use client';
import { useState } from 'react';
import { useMediaPreview } from '@/lib/hooks/useSocialMedia';
import { MediaAsset } from '@/lib/api/socialMedia';
import styles from './media.module.css';

export function assetMetadata(asset: MediaAsset) { return `${asset.mime_type ?? 'Media'} · ${asset.width} × ${asset.height} · ${((asset.byte_size ?? 0) / 1024 / 1024).toFixed(2)} MiB${asset.duration_ms ? ` · ${(asset.duration_ms / 1000).toFixed(1)}s` : ''}`; }
export default function AssetPreview({ id, alt }: { id: string; alt?: string | null }) {
  const [active, setActive] = useState(false), [expired, setExpired] = useState(false);
  const query = useMediaPreview(id, active);
  const grant = query.data, usable = grant && Date.parse(grant.expires_at) > Date.now() && !expired;
  return <div className={styles.preview}>
    {!active && <button type='button' className={styles.button} onClick={() => setActive(true)}>Load private preview</button>}
    {active && query.isFetching && <p role='status'>Loading private preview…</p>}
    {active && query.error && <p className={styles.error} role='alert'>{query.error.message}</p>}
    {active && usable && <>
      {grant.asset.mime_type === 'video/mp4' ? <video className={styles.visual} src={grant.url} controls preload='none' aria-label={alt || grant.asset.filename} onError={() => setExpired(true)} /> : /* eslint-disable-next-line @next/next/no-img-element -- short authenticated storage grants */ <img className={styles.visual} src={grant.url} alt={alt ?? grant.asset.default_alt_text ?? grant.asset.filename} referrerPolicy='no-referrer' onError={() => setExpired(true)} />}
      <p className={styles.muted}>{assetMetadata(grant.asset)}</p>
    </>}
    {active && (query.error || grant && !usable) && <button type='button' className={styles.button} onClick={() => { setExpired(false); void query.refetch(); }}>Refresh private preview</button>}
  </div>;
}

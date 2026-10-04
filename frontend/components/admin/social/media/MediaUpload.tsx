'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { MediaAsset, MediaCapabilities, MediaMime, putMediaFile, socialMediaApi, UploadGrant } from '@/lib/api/socialMedia';
import { toSocialError } from '@/lib/api/social';
import { mediaKeys, useMediaAccess } from '@/lib/hooks/useSocialMedia';
import styles from './media.module.css';

type Attempt = { file: File; alt: string; initiateKey: string; completeKey: string; grant?: UploadGrant; stored?: boolean; contextKey: string; actor: string };
export default function MediaUpload({ capabilities, onSelect, onClose, onBusy, contextKey }: { capabilities: MediaCapabilities; onSelect: (asset: MediaAsset) => void; onClose: () => void; onBusy: (busy: boolean) => void; contextKey: string }) {
  const title = useId(), [file, setFile] = useState<File>(), [alt, setAlt] = useState(''), [phase, setPhase] = useState(''), [error, setError] = useState(''), [retryable, setRetryable] = useState(false), [busy, setBusy] = useState(false);
  const attempt = useRef<Attempt | undefined>(undefined), { actor, enabled } = useMediaAccess(), access = useRef({ actor, enabled }); access.current = { actor, enabled };
  const mounted = useRef(false), latest = useRef({ contextKey, onSelect, onBusy }); latest.current = { contextKey, onSelect, onBusy };
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; latest.current.onBusy(false); }; }, []);
  const qc = useQueryClient();
  const imageFormats = [capabilities.allowed_mime_types.includes('image/jpeg') && 'JPEG', capabilities.allowed_mime_types.includes('image/png') && 'PNG'].filter(Boolean).join('/');
  async function upload() {
    if (!file || !actor || !enabled || !capabilities.upload_available || busy) return;
    if (!capabilities.allowed_mime_types.includes(file.type as MediaMime) || file.size <= 0 || file.size > (file.type === 'video/mp4' ? capabilities.max_video_bytes : capabilities.max_image_bytes)) { setError('Choose a supported file within the displayed size limit.'); return; }
    const current = attempt.current ?? { file, alt, initiateKey: crypto.randomUUID(), completeKey: crypto.randomUUID(), contextKey, actor };
    attempt.current = current; setBusy(true); onBusy(true); setError(''); setRetryable(false);
    try {
      setPhase('Preparing private upload…');
      if (!current.grant || !current.stored && Date.parse(current.grant.expires_at) <= Date.now()) current.grant = await socialMediaApi.initiate({ filename: current.file.name, declared_mime_type: current.file.type as MediaMime, declared_size: current.file.size, alt_text: current.alt }, current.initiateKey);
      if (!current.stored) { setPhase('Uploading original file…'); await putMediaFile(current.grant, current.file); current.stored = true; }
      setPhase('Inspecting actual media bytes…');
      const asset = await socialMediaApi.complete(current.grant.asset.id, current.grant.asset.version, current.completeKey);
      await qc.invalidateQueries({ queryKey: mediaKeys.root(current.actor) });
      if (!mounted.current) return;
      if (!access.current.enabled || access.current.actor !== current.actor || latest.current.contextKey !== current.contextKey) { setPhase('Upload completed and retained in the library. Choose it in the intended editor.'); attempt.current = undefined; return; }
      latest.current.onSelect(asset); setPhase('Media inspected and added.'); attempt.current = undefined;
    } catch (failure) { if (mounted.current) { const safe = toSocialError(failure); setError(safe.message); setRetryable(safe.retryable); setPhase(''); } }
    finally { if (mounted.current) { setBusy(false); latest.current.onBusy(false); } }
  }
  function reset() { attempt.current = undefined; setFile(undefined); setError(''); setRetryable(false); setPhase(''); }
  return <section className={styles.panel} aria-labelledby={title} aria-busy={busy}>
    <h3 id={title}>Upload original media</h3>
    <p className={styles.muted}>{capabilities.upload_available ? <>{imageFormats ? `${imageFormats} up to ${(capabilities.max_image_bytes / 1024 / 1024).toFixed(0)} MiB.` : 'Image inspection is unavailable.'} {capabilities.allowed_mime_types.includes('video/mp4') ? `H.264 MP4 with optional AAC up to ${(capabilities.max_video_bytes / 1024 / 1024).toFixed(0)} MiB and 120 seconds.` : 'Video inspection is unavailable.'} Files are checked before they can be selected.</> : capabilities.unavailable_reason || 'Private media uploads are unavailable.'}</p>
    <label>Media file<input type='file' accept={capabilities.allowed_mime_types.join(',')} disabled={busy || !capabilities.upload_available || !!attempt.current} onChange={event => { setFile(event.target.files?.[0]); setError(''); }} /></label>
    <label>Default media alt text<input maxLength={2000} value={alt} disabled={busy || !capabilities.upload_available || !!attempt.current} onChange={event => setAlt(event.target.value)} /></label>
    {phase && <p role='status'>{phase}</p>}{error && <p className={styles.error} role='alert'>{error}</p>}
    <div className={styles.actions}><button type='button' className={`${styles.button} ${styles.primary}`} disabled={!file || busy || !enabled || !capabilities.upload_available || !!attempt.current && !retryable} onClick={() => void upload()}>{retryable ? 'Retry this upload' : 'Upload and inspect'}</button>{attempt.current && !busy && <button type='button' className={styles.button} onClick={reset}>Choose another file</button>}<button type='button' className={styles.button} disabled={busy} onClick={onClose}>Close upload</button></div>
  </section>;
}

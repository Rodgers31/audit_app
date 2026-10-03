import { DocumentTarget, SocialContent } from '@/lib/api/social';
import { useState } from 'react';
import { resolveContent } from './socialDocument';
import SocialMedia from './SocialMedia';
import styles from './social.module.css';

export default function SocialOverrides({ target, master, onChange, contextKey, onMediaBusyChange }: { target: DocumentTarget; master: SocialContent; onChange: (target: DocumentTarget) => void; contextKey?: string; onMediaBusyChange?: (busy: boolean) => void }) {
  const resolved = resolveContent(master, target);
  const [rawHashtags, setRawHashtags] = useState<{ account: string; value: string }>();
  const hashtagText = rawHashtags?.account === target.account_id && JSON.stringify(rawHashtags.value.split(/\s+/).filter(Boolean)) === JSON.stringify(resolved.hashtags) ? rawHashtags.value : resolved.hashtags.join(' ');
  function reset(field: keyof SocialContent) { const overrides = { ...target.overrides }; delete overrides[field]; if (field === 'hashtags') setRawHashtags(undefined); onChange({ ...target, overrides }); }
  function replace<K extends keyof SocialContent>(field: K, value: SocialContent[K]) { onChange({ ...target, overrides: { ...target.overrides, [field]: { mode: 'replace', value } } }); }
  return <section className={styles.fields} aria-label='Account overrides'>
    <h3>Customize this account</h3><p className={styles.muted}>Each field inherits master content until customized. Intentional empty values apply only to this account.</p>
    {(['text', 'link', 'hashtags', 'media'] as const).map(field => <div className={styles.override} key={field}>
      <div className={styles.overrideHead}><strong>{({ text: 'Text', link: 'Link', hashtags: 'Hashtags', media: 'Media' })[field]} · {target.overrides[field] ? 'Customized' : 'Inherits master'}</strong>{target.overrides[field] ? <button type='button' className={styles.button} onClick={() => reset(field)}>Reset {field} to master</button> : <button type='button' className={styles.button} onClick={() => replace(field, resolved[field])}>Customize {field}</button>}</div>
      {target.overrides[field] && field === 'text' && <label>Account text<textarea rows={5} value={resolved.text} onChange={e => replace('text', e.target.value)} /></label>}
      {target.overrides[field] && field === 'link' && <label>Account URL<input type='url' value={resolved.link ?? ''} onChange={e => replace('link', e.target.value || null)} /><span className={styles.muted}>An empty URL intentionally removes the master link.</span></label>}
      {target.overrides[field] && field === 'hashtags' && <label>Account hashtags<input value={hashtagText} onChange={e => { setRawHashtags({ account: target.account_id, value: e.target.value }); replace('hashtags', e.target.value.split(/\s+/).filter(Boolean)); }} /><span className={styles.muted}>An empty list intentionally removes master hashtags.</span></label>}
      {target.overrides[field] && field === 'media' && <SocialMedia key={target.account_id} label='Account' contextKey={`${contextKey ?? 'editor'}:account:${target.account_id}`} onBusyChange={onMediaBusyChange} media={resolved.media} onChange={value => replace('media', value)} />}
    </div>)}
  </section>;
}

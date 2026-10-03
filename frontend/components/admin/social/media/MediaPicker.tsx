'use client';
import { useId, useState } from 'react';
import { MediaAsset } from '@/lib/api/socialMedia';
import { useMediaLibrary } from '@/lib/hooks/useSocialMedia';
import AssetPreview, { assetMetadata } from './AssetPreview';
import styles from './media.module.css';

export default function MediaPicker({ onSelect, onClose, selected }: { onSelect: (asset: MediaAsset) => void; onClose: () => void; selected: string[] }) {
  const [page, setPage] = useState(1), [search, setSearch] = useState(''), [query, setQuery] = useState(''), [kind, setKind] = useState<'' | 'image' | 'video'>('');
  const title = useId(), library = useMediaLibrary(page, query, kind, true);
  return <section className={styles.panel} aria-labelledby={title}>
    <h3 id={title}>Choose inspected media</h3>
    <div className={styles.filters}>
      <label>Search filenames<input maxLength={100} value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); setQuery(search); setPage(1); } }} /></label>
      <label>Media type<select value={kind} onChange={event => { setKind(event.target.value as typeof kind); setPage(1); }}><option value=''>All media</option><option value='image'>Images</option><option value='video'>Videos</option></select></label>
      <button type='button' className={styles.button} onClick={() => { setQuery(search); setPage(1); }}>Search library</button>
    </div>
    {library.isFetching && <p role='status'>Loading inspected media…</p>}
    {library.error && <p className={styles.error} role='alert'>{library.error.message}</p>}
    {library.error && <button type='button' className={styles.button} onClick={() => void library.refetch()}>Retry library</button>}
    {library.data && !library.isFetching && <>
      <p className={styles.muted}>{library.data.total} ready assets · Page {page}</p>
      {!library.data.assets.length && <p>No ready media matches these filters.</p>}
      <ul className={styles.list}>{library.data.assets.map(asset => <li className={styles.item} key={asset.id}>
        <strong>{asset.filename}</strong><p className={styles.muted}>{assetMetadata(asset)}</p>
        <AssetPreview id={asset.id} alt={asset.default_alt_text} />
        <button type='button' className={`${styles.button} ${styles.primary}`} disabled={selected.includes(asset.id)} onClick={() => onSelect(asset)}>{selected.includes(asset.id) ? 'Already selected' : `Use ${asset.filename}`}</button>
      </li>)}</ul>
      <div className={styles.actions}><button type='button' className={styles.button} disabled={page === 1} onClick={() => setPage(page - 1)}>Previous media page</button><button type='button' className={styles.button} disabled={!library.data.has_more} onClick={() => setPage(page + 1)}>Next media page</button></div>
    </>}
    <button type='button' className={styles.button} onClick={onClose}>Close media library</button>
  </section>;
}

'use client';

import { useId, useState, type Key, type ReactNode } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';

export default function TopList<T>({ items, limit, itemKey, searchText, renderItem }: {
  items: readonly T[];
  limit: number;
  itemKey: (item: T) => Key;
  searchText: (item: T) => string;
  renderItem: (item: T) => ReactNode;
}) {
  const { t, lang } = useLang();
  const id = useId();
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const normalize = (text: string) => text.trim().toLocaleLowerCase(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const search = normalize(query);
  const filtered = search ? items.filter(item => normalize(searchText(item)).includes(search)) : items;
  const shown = showAll ? filtered : filtered.slice(0, limit);
  return (
    <div className='min-w-0 space-y-3'>
      <label className='block text-sm font-medium'>
        {t('foundation.find_item')}
        <input type='search' value={query} onChange={event => setQuery(event.target.value)} className='audit-control mt-1 block w-full bg-surface-base text-left' />
      </label>
      {filtered.length === 0 && <p role='status' className='text-sm'>{t('foundation.empty_list')}</p>}
      <ul id={id} className='space-y-2'>
        {shown.map(item => <li key={itemKey(item)}>{renderItem(item)}</li>)}
      </ul>
      {filtered.length > limit && (
        <button type='button' className='audit-control' aria-expanded={showAll} aria-controls={id} onClick={() => setShowAll(value => !value)}>
          {showAll ? t('foundation.show_less') : t('foundation.show_all').replace('{count}', String(filtered.length))}
        </button>
      )}
    </div>
  );
}

'use client';

import type { CountyAuditListItem } from '@/lib/api/audits';
import { useCountyAuditList } from '@/lib/react-query/useAudits';

type Props = {
  countyId: string;
  year?: string;
  status?: string;
  severity?: string;
  limit?: number;
};

function webSourceUrl(value?: string | null) {
  if (!value) return undefined;
  try {
    const protocol = new URL(value).protocol;
    return protocol === 'https:' || protocol === 'http:' ? value : undefined;
  } catch {
    return undefined;
  }
}

export default function AuditListWithSources({
  countyId,
  year,
  status,
  severity,
  limit = 10,
}: Props) {
  const { data, isLoading, error } = useCountyAuditList(countyId, {
    page: 1,
    limit,
    year,
    status,
    severity,
  });

  if (isLoading) return <div className='text-sm text-slate-600 dark:text-neutral-muted'>Loading audits…</div>;
  if (error) return <div className='text-sm text-red-600'>Failed to load audits</div>;
  if (!data || data.items.length === 0)
    return <div className='text-sm text-slate-600 dark:text-neutral-muted'>No audits found</div>;

  return (
    <ul className='space-y-2'>
      {data.items.map((item: CountyAuditListItem) => {
        const page = item.source?.page;
        const source = item.source;
        const anchor = webSourceUrl(source.page_url === undefined ? source.url : source.page_url);
        const pageLabel = source.page_url && typeof page === 'number' && page > 0
          ? `page ${page}`
          : source.page_url && typeof page === 'string' ? page : null;
        return (
          <li key={String(item.id)} className='p-3 rounded-lg border border-slate-200 bg-white dark:bg-surface-base'>
            <div className='text-sm text-slate-800 dark:text-neutral-text'>{item.description || 'Audit finding'}</div>
            <div className='flex gap-3 text-xs text-slate-600 dark:text-neutral-muted mt-1'>
              {item.severity && <span>Severity: {item.severity}</span>}
              {item.status && <span>Status: {item.status}</span>}
              {item.fiscal_year && <span>FY: {item.fiscal_year}</span>}
            </div>
            {anchor && (
              <a
                href={anchor}
                target='_blank'
                rel='noreferrer'
                className='inline-block mt-2 text-xs text-blue-600 hover:underline'
                title={
                  item.source?.table_index != null
                    ? `Open source (table #${item.source.table_index})`
                    : 'Open source'
                }>
                Open source{pageLabel ? ` (${pageLabel})` : ''}
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

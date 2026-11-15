'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import InfoSheet from '@/components/ui/InfoSheet';
import { useLang } from '@/lib/i18n/LangProvider';

export type PageSection = { id: string; label: string; hint?: string };

export default function SectionNavigation({ sections, children }: { sections: readonly PageSection[]; children: ReactNode }) {
  const { t } = useLang();
  const overview = useRef<HTMLElement>(null);
  const [current, setCurrent] = useState(0);
  const [sticky, setSticky] = useState(false);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const edge = 120;
      setSticky(Boolean(overview.current && overview.current.getBoundingClientRect().bottom <= 64));
      const firstBelow = sections.findIndex(({ id }) => {
        const target = document.getElementById(id);
        return target && target.getBoundingClientRect().top > edge;
      });
      setCurrent(firstBelow < 0 ? sections.length - 1 : Math.max(0, firstBelow - 1));
    };
    const requestUpdate = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', requestUpdate);
    update();
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', requestUpdate);
      window.removeEventListener('resize', requestUpdate);
    };
  }, [sections]);

  if (sections.length === 0) return children;
  const heading = t('foundation.on_this_page');
  const location = t('foundation.section_position').replace('{position}', String(current + 1)).replace('{total}', String(sections.length));

  const list = (className: string, includeHint: boolean, sheet = false) => (
    <ul className={className}>
      {sections.map(({ id, label, hint }, index) => (
        <li key={id} className='min-w-0'>
          <a href={`#${id}`} aria-current={index === current ? 'location' : undefined}
            onClick={sheet ? event => event.currentTarget.closest('dialog')?.close() : undefined}
            className='flex min-h-11 flex-col justify-center border-b border-neutral-border px-2 py-1.5 text-sm hover:bg-surface-sunken aria-[current=location]:font-semibold aria-[current=location]:text-signal-good'>
            <span>{label}</span>
            {includeHint && hint && <span className='text-xs font-normal text-neutral-muted'>{hint}</span>}
          </a>
        </li>
      ))}
    </ul>
  );

  return (
    <div className='redesign-section-layout min-w-0 min-[900px]:grid min-[900px]:grid-cols-[220px_minmax(0,1fr)] min-[900px]:gap-8'>
      <nav ref={overview} aria-label={heading} className='mb-4 min-[900px]:sticky min-[900px]:top-20 min-[900px]:mb-0 min-[900px]:self-start'>
        <p className='text-sm font-semibold'>{heading}</p>
        {list('grid grid-cols-2 gap-x-2 min-[900px]:grid-cols-1', true)}
      </nav>
      {sticky && (
        <nav aria-label={heading} className='fixed inset-x-0 top-16 z-30 flex min-h-12 items-center justify-between gap-1 border-b border-neutral-border bg-surface-base px-2 min-[900px]:hidden'>
          <a href={current ? `#${sections[current - 1].id}` : undefined} aria-disabled={current === 0}
            aria-label={t('foundation.previous_section')} className='audit-control min-w-11 px-0 aria-disabled:opacity-40'><ChevronLeft aria-hidden='true' size={18} /></a>
          <p className='min-w-0 text-xs'><span>{location}</span><strong className='ml-1'>{sections[current]?.label}</strong></p>
          <a href={current < sections.length - 1 ? `#${sections[current + 1].id}` : undefined} aria-disabled={current === sections.length - 1}
            aria-label={t('foundation.next_section')} className='audit-control min-w-11 px-0 aria-disabled:opacity-40'><ChevronRight aria-hidden='true' size={18} /></a>
          <InfoSheet title={heading} trigger={props => <button {...props} type='button' className='audit-control px-2'>{t('foundation.sections')}</button>}>
            {list('space-y-1', false, true)}
          </InfoSheet>
        </nav>
      )}
      <div className='min-w-0'>{children}</div>
    </div>
  );
}

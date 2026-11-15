'use client';

import { useId, useRef, type PointerEvent, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useLang } from '@/lib/i18n/LangProvider';

type SheetTrigger = {
  onClick: () => void;
  'aria-haspopup': 'dialog';
  'aria-controls': string;
};

export default function InfoSheet({ title, children, trigger }: {
  title: string;
  children: ReactNode;
  trigger: (props: SheetTrigger) => ReactNode;
}) {
  const { t } = useLang();
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const gestureStart = useRef<number | null>(null);

  function endGesture(event: PointerEvent<HTMLElement>) {
    if (gestureStart.current != null && event.clientY - gestureStart.current > 72) {
      dialog.current?.close();
    }
    gestureStart.current = null;
  }

  return (
    <>
      {trigger({ onClick: () => dialog.current?.showModal(), 'aria-haspopup': 'dialog', 'aria-controls': id })}
      <dialog
        ref={dialog}
        id={id}
        aria-labelledby={`${id}-heading`}
        className='audit-sheet fixed inset-x-0 bottom-0 top-auto m-0 max-h-[85dvh] w-full max-w-none overflow-y-auto overscroll-contain rounded-t border border-neutral-border bg-surface-base p-0 text-neutral-text shadow-elevated md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[min(30rem,95vw)] md:rounded-none'
        onClick={(event) => {
          if (event.target !== event.currentTarget) return;
          const rect = event.currentTarget.getBoundingClientRect();
          if (event.clientX < rect.left || event.clientX > rect.right ||
              event.clientY < rect.top || event.clientY > rect.bottom) event.currentTarget.close();
        }}>
        <header
          className='sticky top-0 flex touch-none items-center justify-between gap-3 border-b border-neutral-border bg-surface-base px-4 py-2'
          onPointerDown={event => {
            if (event.pointerType === 'touch' && event.target === event.currentTarget) {
              event.currentTarget.setPointerCapture(event.pointerId);
              gestureStart.current = event.clientY;
            }
          }}
          onPointerCancel={() => { gestureStart.current = null; }}
          onPointerUp={endGesture}>
          <h2 id={`${id}-heading`} className='pointer-events-none text-audit-heading font-semibold'>{title}</h2>
          <form method='dialog'>
            <button type='submit' aria-label={t('foundation.close')} autoFocus className='audit-control min-w-11 px-0'>
              <X aria-hidden='true' size={20} />
            </button>
          </form>
        </header>
        <div className='min-w-0 space-y-3 break-words px-4 pb-6 pt-4 text-sm leading-relaxed'>{children}</div>
      </dialog>
    </>
  );
}

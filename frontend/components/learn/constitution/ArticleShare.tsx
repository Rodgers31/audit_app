'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { ArrowUpRight } from 'lucide-react';
import { useId, useRef, useState } from 'react';

export default function ArticleShare({ articleNumber, articleTitle }: {
  articleNumber: number;
  articleTitle: string;
}) {
  const { lang } = useLang();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const shareAttempt = useRef(0);
  const [manualUrl, setManualUrl] = useState('');
  const [copied, setCopied] = useState(false);
  const [manualStatus, setManualStatus] = useState<'copied' | 'articleCopyManually' | null>(null);
  const title = learnCopy(lang, 'shareArticle');

  async function share(opener: HTMLButtonElement, openSheet: () => void) {
    if (inFlight.current) return;
    inFlight.current = true;
    shareAttempt.current += 1;
    setCopied(false);
    setManualStatus(null);
    opener.focus({ preventScroll: true });
    const url = new URL(`/learn?article=${articleNumber}`, window.location.origin).href;

    function showManualLink() {
      // While a browser prompt is open, the reader may navigate or leave this control.
      if (!opener.isConnected || document.activeElement !== opener) return;
      setManualUrl(url);
      openSheet();
    }

    try {
      if (window.matchMedia('(pointer: coarse)').matches && typeof navigator.share === 'function') {
        const article = learnCopy(lang, 'article', { number: articleNumber });
        await navigator.share({ title: `${article} · ${articleTitle}`, url });
      } else {
        await navigator.clipboard.writeText(url);
        if (opener.isConnected) setCopied(true);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) showManualLink();
    } finally {
      inFlight.current = false;
    }
  }

  async function copyFromSheet() {
    const attempt = ++shareAttempt.current;
    const field = input.current;
    if (!field) return;

    let status: 'copied' | 'articleCopyManually' = 'copied';
    try {
      await navigator.clipboard.writeText(field.value);
    } catch {
      status = 'articleCopyManually';
    }

    if (attempt !== shareAttempt.current || !field.isConnected || !field.closest('dialog')?.open) return;
    if (status === 'articleCopyManually') {
      field.focus();
      field.select();
    }
    setManualStatus(status);
  }

  return (
    <div className='min-w-0 space-y-2'>
      <InfoSheet title={title} trigger={props => (
        <button {...props} type='button' className='audit-control gap-2'
          onClick={event => { void share(event.currentTarget, props.onClick); }}>
          <ArrowUpRight size={16} aria-hidden='true' />
          {learnCopy(lang, 'share')}
        </button>
      )}>
        <label htmlFor={inputId} className='block font-semibold'>{learnCopy(lang, 'articleLink')}</label>
        <input
          id={inputId}
          ref={input}
          type='url'
          readOnly
          value={manualUrl}
          onFocus={event => event.currentTarget.select()}
          className='audit-control block w-full min-w-0 bg-surface-elevated text-base'
        />
        <button type='button' onClick={() => { void copyFromSheet(); }} className='audit-control'>
          {learnCopy(lang, 'articleCopy')}
        </button>
        <p role='status'>{manualStatus && learnCopy(lang, manualStatus)}</p>
      </InfoSheet>
      <p role='status' className='text-sm text-neutral-text empty:m-0'>
        {copied && learnCopy(lang, 'copied')}
      </p>
    </div>
  );
}

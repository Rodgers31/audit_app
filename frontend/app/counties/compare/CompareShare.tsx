'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_COMPARE_MESSAGES as messages } from '@/lib/i18n/messages/countyCompare';
import { Link2 } from 'lucide-react';
import { useId, useRef, useState } from 'react';

export default function CompareShare({ href }: { href: string }) {
  const { lang } = useLang();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState('');
  const [copyStatus, setCopyStatus] = useState<'copied' | 'copyManually' | null>(null);
  const title = messages.share[lang];

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopyStatus('copied');
    } catch {
      input.current?.select();
      setCopyStatus('copyManually');
    }
  }

  return (
    <InfoSheet title={title} trigger={(props) => (
      <button {...props} type='button' className='audit-control gap-2 self-start motion-reduce:transition-none'
        onClick={(event) => {
          event.currentTarget.focus();
          setUrl(new URL(href, window.location.origin).href);
          setCopyStatus(null);
          props.onClick();
        }}>
        <Link2 aria-hidden='true' size={18} />
        {title}
      </button>
    )}>
      <label htmlFor={id} className='font-semibold'>{messages.link[lang]}</label>
      <input id={id} ref={input} type='url' readOnly value={url}
        onFocus={(event) => event.currentTarget.select()}
        className='audit-control block w-full bg-surface-elevated text-base motion-reduce:transition-none' />
      <button type='button' onClick={copy} className='audit-control motion-reduce:transition-none'>
        {messages.copy[lang]}
      </button>
      <p role='status'>{copyStatus && messages[copyStatus][lang]}</p>
    </InfoSheet>
  );
}

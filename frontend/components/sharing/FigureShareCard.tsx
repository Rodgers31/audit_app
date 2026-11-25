'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { FIGURE_SHARE_MESSAGES } from '@/lib/i18n/messages/figureShare';
import {
  figureSourceText,
  preparePublicFigure,
  SHARE_CARD_COLORS as colors,
  SHARE_CARD_FILENAME,
  SHARE_CARD_SITE,
  type PublicFigureShareData,
  type PublicFigureShareInput,
} from '@/lib/sharing/figureShare';
import { createPublicFigurePng } from '@/lib/sharing/figureShareImage';
import { useEffect, useRef, useState } from 'react';

const control = 'audit-control min-w-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';

function canShareFile(file: File) {
  try {
    return typeof navigator.share === 'function' && navigator.canShare?.({ files: [file] }) === true;
  } catch {
    return false;
  }
}

function FigureImage({ figure }: { figure: PublicFigureShareData }) {
  const { lang } = useLang();
  const copy = (key: keyof typeof FIGURE_SHARE_MESSAGES) => FIGURE_SHARE_MESSAGES[key][lang];
  const metric = useRef<HTMLParagraphElement>(null);
  const value = useRef<HTMLParagraphElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [image, setImage] = useState<{ file: File; url: string; native: boolean } | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<'prepareFailed' | 'shareFailed' | null>(null);

  useEffect(() => {
    if (!file) return;
    try {
      const url = URL.createObjectURL(file);
      setImage({ file, url, native: canShareFile(file) });
      return () => URL.revokeObjectURL(url);
    } catch {
      setError('prepareFailed');
    }
  }, [file]);

  const ready = image?.file === file ? image : null;

  async function prepareImage() {
    if (preparing || sharing || !metric.current || !value.current) return;
    const fonts = { body: getComputedStyle(metric.current).fontFamily, display: getComputedStyle(value.current).fontFamily };
    setFile(null);
    setImage(null);
    setError(null);
    setPreparing(true);
    try {
      const png = await createPublicFigurePng(figure, fonts);
      setFile(new File([png], SHARE_CARD_FILENAME, { type: 'image/png' }));
    } catch {
      setError('prepareFailed');
    } finally {
      setPreparing(false);
    }
  }

  async function shareImage() {
    if (!ready || sharing) return;
    if (!canShareFile(ready.file)) {
      setError('shareFailed');
      return;
    }
    setError(null);
    setSharing(true);
    try {
      // PNG preparation is complete, so the click directly invokes the share sheet.
      await navigator.share({ files: [ready.file] });
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError('shareFailed');
    } finally {
      setSharing(false);
    }
  }

  const status = error ?? (preparing ? 'preparing' : ready ? ready.native ? 'readyShare' : 'readyDownload' : null);

  return (
    <section aria-label={copy('card')} className='min-w-0 space-y-3 rounded bg-surface-base p-3'>
      <figure
        className='min-w-0 rounded border border-t-4 p-4 sm:p-5'
        style={{ backgroundColor: colors.paper, color: colors.ink, borderColor: colors.rule, borderTopColor: colors.accent }}>
        <p ref={metric} className='whitespace-pre-wrap break-words text-base font-semibold'>{figure.metric}</p>
        <p ref={value} className='mt-2 whitespace-pre-wrap break-words font-display text-5xl font-semibold leading-tight tabular-nums'>{figure.value}</p>
        <figcaption className='mt-3 border-t text-sm' style={{ color: colors.muted, borderColor: colors.rule }}>
          <a href={figure.sourceUrl}
            className='inline-flex min-h-11 min-w-11 max-w-full items-center rounded underline decoration-current underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage'>
            <span className='min-w-0 whitespace-pre-wrap break-words'>{figureSourceText(figure)}</span>
          </a>
          <span className='inline-block whitespace-nowrap'> · {SHARE_CARD_SITE}</span>
        </figcaption>
      </figure>
      <div className='flex flex-wrap items-center gap-2'>
        <button type='button' className={control} disabled={preparing || sharing} onClick={() => void prepareImage()}>
          {copy(ready ? 'prepareAgain' : 'prepare')}
        </button>
        {ready?.native && (
          <button type='button' className={control} disabled={sharing} onClick={() => void shareImage()}>
            {copy('share')}
          </button>
        )}
        {ready && <a href={ready.url} download={ready.file.name} className={control}>{copy('download')}</a>}
      </div>
      <p role='status' className={status ? 'text-sm text-neutral-text' : 'sr-only'}>{status ? copy(status) : ''}</p>
    </section>
  );
}

/** Parent integrations supply the published observation and its exact report receipt. */
export default function FigureShareCard({ figure }: { figure: PublicFigureShareInput | null }) {
  const { lang } = useLang();
  const prepared = preparePublicFigure(figure);
  if (prepared.status !== 'ready') {
    return (
      <p role='status' className='audit-panel p-3 text-sm text-neutral-text'>
        {FIGURE_SHARE_MESSAGES[prepared.status][lang]}
      </p>
    );
  }

  const published = prepared.figure;
  // A changed receipt invalidates both the prepared file and its download URL.
  return <FigureImage key={JSON.stringify(published)} figure={published} />;
}

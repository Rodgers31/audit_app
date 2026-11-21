'use client';

import { useEffect, useState } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { DAILY_QUIZ_COUNT } from './quizDaily';

const CARD_FILENAME = 'auditgava-daily-3.png';

function drawResultCard(message: string) {
  const canvas = document.createElement('canvas');
  canvas.width = 1200;
  canvas.height = 630;
  const context = canvas.getContext('2d');
  if (!context) return null;

  // The approved gov-sand and gov-dark tokens make the shared image legible in either theme.
  context.fillStyle = '#F3EEE4';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#101B14';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.font = 'bold 62px system-ui, sans-serif';

  const lines: string[] = [];
  let line = '';
  for (const word of message.split(' ')) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && context.measureText(candidate).width > 1060) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  lines.push(line);

  const lineHeight = 84;
  const start = (canvas.height - lines.length * lineHeight) / 2;
  lines.forEach((text, index) => context.fillText(text, canvas.width / 2, start + index * lineHeight));
  context.font = '40px system-ui, sans-serif';
  context.fillText('auditgava.com', canvas.width / 2, start + lines.length * lineHeight + 8);
  return canvas;
}

export default function QuizDailyShare({ score }: { score: number }) {
  const { lang } = useLang();
  const message = learnCopy(lang, 'quizDailyCard', { score, total: DAILY_QUIZ_COUNT });
  const [image, setImage] = useState<{ message: string; file: File; url: string } | null>(null);
  const [error, setError] = useState(false);
  const card = image?.message === message ? image : null;

  useEffect(() => {
    let active = true;
    let url: string | undefined;
    try {
      const canvas = drawResultCard(message);
      if (!canvas) throw new Error('Canvas unavailable');
      canvas.toBlob(blob => {
        if (!active) return;
        if (!blob) {
          setError(true);
          return;
        }
        const file = new File([blob], CARD_FILENAME, { type: 'image/png' });
        url = URL.createObjectURL(file);
        setImage({ message, file, url });
      }, 'image/png');
    } catch {
      setError(true);
    }
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [message]);

  async function share(file: File) {
    try {
      await navigator.share({ files: [file] });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setError(true);
    }
  }

  return (
    <>
      {card && typeof navigator.share === 'function' && navigator.canShare?.({ files: [card.file] }) && (
        <button type='button' onClick={() => share(card.file)} className='audit-control'>
          {learnCopy(lang, 'quizDailyShare')}
        </button>
      )}
      {card && (
        <a href={card.url} download={CARD_FILENAME} className='audit-control'>
          {learnCopy(lang, 'quizDailyDownload')}
        </a>
      )}
      {error && <p role='status' className='w-full text-sm'>{learnCopy(lang, 'quizDailyShareError')}</p>}
    </>
  );
}

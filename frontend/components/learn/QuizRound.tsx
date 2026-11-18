'use client';

import { ArrowRight, Check, X } from 'lucide-react';
import { useId, useLayoutEffect, useRef } from 'react';
import type { QuizQuestion } from '@/data/quizData';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import QuizCitation from './QuizCitation';

interface QuizRoundProps {
  category: string;
  question: QuizQuestion;
  current: number;
  total: number;
  selected: number | null;
  onAnswer: (choice: number) => void;
  onNext: () => void;
  onQuit: () => void;
}

export default function QuizRound({ category, question, current, total, selected, onAnswer, onNext, onQuit }: QuizRoundProps) {
  const { lang } = useLang();
  const dialog = useRef<HTMLDialogElement>(null);
  const questionHeading = useRef<HTMLHeadingElement>(null);
  const explanationHeading = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const answered = selected !== null;
  const isLast = current === total;
  const position = learnCopy(lang, 'quizPosition', { current, total });

  useLayoutEffect(() => {
    const round = dialog.current;
    if (!round) return;
    if (!round.open) round.showModal();
    if (answered) explanationHeading.current?.focus();
    else {
      questionHeading.current?.focus({ preventScroll: true });
      round.scrollTop = 0;
    }
  }, [answered, question.id]);

  const quit = () => {
    dialog.current?.close();
    onQuit();
  };

  return (
    <dialog
      ref={dialog}
      data-quiz-round
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        quit();
      }}
      className='fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-x-hidden overflow-y-auto overscroll-contain bg-gov-sand p-0 text-neutral-text dark:bg-surface-sunken'>
      <header className='sticky inset-x-0 top-0 z-10 border-b border-neutral-border bg-surface-base'>
        <div className='mx-auto grid min-h-[54px] max-w-2xl grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-2.5 px-4'>
          <button type='button' onClick={quit} aria-label={learnCopy(lang, 'quizQuit')}
            className='grid size-11 place-items-center rounded text-neutral-text hover:bg-surface-sunken focus-visible:outline-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100'>
            <X aria-hidden='true' size={20} />
          </button>
          <progress
            aria-label={learnCopy(lang, 'quizProgress')}
            aria-valuetext={position}
            value={current}
            max={total}
            className='h-1.5 w-full appearance-none overflow-hidden rounded-full bg-surface-sunken [&::-moz-progress-bar]:bg-neutral-text [&::-webkit-progress-bar]:bg-surface-sunken [&::-webkit-progress-value]:bg-neutral-text' />
          <span className='text-sm font-semibold tabular-nums' aria-hidden='true'>{position}</span>
        </div>
      </header>

      <section className='mx-auto grid max-w-2xl gap-4 px-4 pb-6 pt-5 sm:px-6'>
        {/* The question has room to grow. Short prompts still leave the answers within thumb reach. */}
        <div className='min-w-0 min-h-[clamp(9rem,calc(45dvh-4.75rem),21rem)]'>
          <p className='text-sm font-semibold text-neutral-muted'>{category}</p>
          <h1 ref={questionHeading} id={titleId} lang='en' tabIndex={-1}
            className='mt-2 break-words font-display text-[clamp(1.5rem,4vw,2rem)] font-bold leading-[1.1] outline-none'>
            {question.question}
          </h1>
        </div>
        <div role='group' aria-label={learnCopy(lang, 'quizAnswers')} className='grid gap-2'>
          {question.options.map((option, index) => {
            const correct = answered && index === question.correctIndex;
            const incorrect = answered && index === selected && !correct;
            const className = correct
              ? 'border-signal-good bg-[color:color-mix(in_srgb,var(--signal-good)_8%,rgb(var(--c-surface-base)))] text-signal-good'
              : incorrect
                ? 'border-signal-alarm bg-surface-base text-signal-alarm'
                : 'border-neutral-border bg-surface-base text-neutral-text enabled:hover:bg-surface-sunken';
            return (
              <button key={index} type='button' disabled={answered} onClick={() => onAnswer(index)}
                className={`flex min-h-12 w-full items-center justify-between gap-3 rounded-md border px-3.5 py-2 text-left text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100 ${className}`}>
                <span lang='en' className='min-w-0 break-words'>{option}</span>
                {correct && <Check aria-hidden='true' size={20} className='shrink-0' />}
                {incorrect && <X aria-hidden='true' size={20} className='shrink-0' />}
                {correct && <span className='sr-only'>{learnCopy(lang, 'quizCorrectAnswer')}</span>}
                {incorrect && <span className='sr-only'>{learnCopy(lang, 'quizSelectedAnswer')}</span>}
              </button>
            );
          })}
        </div>
        {answered && (
          <>
            <section className='rounded-md border border-neutral-border bg-surface-sunken p-3 text-sm leading-relaxed'>
              <h2 ref={explanationHeading} tabIndex={-1} className='inline font-semibold outline-none'>
                {learnCopy(lang, selected === question.correctIndex ? 'quizCorrect' : 'quizIncorrect')}.
              </h2>{' '}
              <p lang='en' className='inline'>{question.explanation}</p>
              <div className='empty:hidden'><QuizCitation questionId={question.id} /></div>
            </section>
            <button type='button' onClick={() => {
              if (isLast) dialog.current?.close();
              onNext();
            }} className='audit-control justify-self-end gap-2'>
              {learnCopy(lang, isLast ? 'quizSeeResults' : 'quizNext')}
              <ArrowRight size={18} aria-hidden='true' />
            </button>
          </>
        )}
      </section>
    </dialog>
  );
}

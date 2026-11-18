'use client';

import {
  ArrowRight, BookOpen, Building2, Landmark, Map as MapIcon, Play, Scale, Search,
} from 'lucide-react';
import { useLayoutEffect, useRef, useState } from 'react';
import PageShell from '@/components/layout/PageShell';
import {
  getRandomQuestions, quizCategories, TOTAL_QUESTIONS,
  type QuizCategory, type QuizQuestion,
} from '@/data/quizData';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import QuizCitation from './QuizCitation';
import QuizRound from './QuizRound';

type Phase = 'categories' | 'playing' | 'feedback' | 'results';

interface GameState {
  phase: Phase;
  category: QuizCategory | null;
  questions: QuizQuestion[];
  index: number;
  answers: number[];
}

const INITIAL_GAME: GameState = { phase: 'categories', category: null, questions: [], index: 0, answers: [] };
const QUICK_PLAY_COUNT = 10;

const categoryPresentation = {
  constitution: { icon: BookOpen, label: 'quizConstitution' },
  government: { icon: Landmark, label: 'quizGovernment' },
  devolution: { icon: MapIcon, label: 'quizDevolution' },
  finance: { icon: Building2, label: 'quizFinance' },
  rights: { icon: Scale, label: 'quizRights' },
  accountability: { icon: Search, label: 'quizAccountability' },
} as const;

const categoryByQuestion = new Map(quizCategories.flatMap(category =>
  category.questions.map(question => [question.id, category] as const),
));

export default function QuizGame() {
  const { lang } = useLang();
  const [game, setGame] = useState(INITIAL_GAME);
  const launchButtons = useRef(new Map<string, HTMLButtonElement>());
  const previousLaunch = useRef<string | null>(null);
  const restoreLaunch = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const current = game.questions[game.index];
  const total = game.questions.length;

  function categoryLabel(category: QuizCategory | undefined) {
    const presentation = categoryPresentation[category?.id as keyof typeof categoryPresentation];
    return presentation ? learnCopy(lang, presentation.label) : category?.title;
  }

  useLayoutEffect(() => {
    if (game.phase === 'results') resultHeading.current?.focus();
    if (game.phase === 'categories' && restoreLaunch.current && previousLaunch.current) {
      launchButtons.current.get(previousLaunch.current)?.focus();
      restoreLaunch.current = false;
    }
  }, [game.phase]);

  function rememberButton(id: string, node: HTMLButtonElement | null) {
    if (node) launchButtons.current.set(id, node);
    else launchButtons.current.delete(id);
  }

  function start(category: QuizCategory | null) {
    previousLaunch.current = category?.id ?? 'quick';
    const questions = category
      ? [...category.questions].sort(() => Math.random() - 0.5)
      : getRandomQuestions(QUICK_PLAY_COUNT);
    setGame({ phase: 'playing', category, questions, index: 0, answers: [] });
  }

  function answer(choice: number) {
    setGame(previous => previous.phase === 'playing' && current === previous.questions[previous.index]
      ? { ...previous, phase: 'feedback', answers: [...previous.answers, choice] }
      : previous);
  }

  function next() {
    setGame(previous => {
      if (previous.phase !== 'feedback') return previous;
      return previous.index + 1 < previous.questions.length
        ? { ...previous, phase: 'playing', index: previous.index + 1 }
        : { ...previous, phase: 'results' };
    });
  }

  function reset() {
    restoreLaunch.current = true;
    setGame(INITIAL_GAME);
  }

  if ((game.phase === 'playing' || game.phase === 'feedback') && current) {
    return <QuizRound
      category={categoryLabel(categoryByQuestion.get(current.id)) ?? ''}
      question={current}
      current={game.index + 1}
      total={total}
      selected={game.answers[game.index] ?? null}
      onAnswer={answer}
      onNext={next}
      onQuit={reset} />;
  }

  const score = game.answers.filter((choice, index) => choice === game.questions[index]?.correctIndex).length;

  return (
    <PageShell
      title={learnCopy(lang, 'quizTitle')}
      subtitle={learnCopy(lang, 'quizSubtitle')}
      back={{ href: '/learn', label: learnCopy(lang, 'quizBack') }}>
      {game.phase === 'categories' ? (
        <div data-quiz-categories className='space-y-4'>
          <button ref={(node) => rememberButton('quick', node)} type='button' onClick={() => start(null)}
            className='grid min-h-11 w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-neutral-border bg-surface-base p-4 text-left hover:bg-surface-sunken focus-visible:outline-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100'>
            <Play size={20} aria-hidden='true' />
            <span className='min-w-0 space-y-0.5'>
              <strong className='block text-base'>{learnCopy(lang, 'quizQuick')}</strong>
              <span className='block text-sm text-neutral-muted'>{learnCopy(lang, 'quizQuickDetail', { count: QUICK_PLAY_COUNT })}</span>
            </span>
            <ArrowRight size={18} aria-hidden='true' />
          </button>

          <ul className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
            {quizCategories.map(category => {
              const Icon = categoryPresentation[category.id as keyof typeof categoryPresentation]?.icon ?? BookOpen;
              return (
                <li key={category.id}>
                  <button ref={(node) => rememberButton(category.id, node)} type='button' onClick={() => start(category)}
                    className='grid h-full min-h-11 w-full grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 rounded-md border border-neutral-border bg-surface-base p-4 text-left hover:bg-surface-sunken focus-visible:outline-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100'>
                    <Icon size={20} aria-hidden='true' />
                    <span className='min-w-0 space-y-1'>
                      <strong className='block text-base'>{categoryLabel(category)}</strong>
                      <span className='block break-words text-sm text-neutral-muted' lang='en'>{category.description}</span>
                      <span className='block text-sm text-neutral-text'>{learnCopy(lang, 'quizQuestionCount', { count: category.questions.length })}</span>
                    </span>
                    <ArrowRight size={18} aria-hidden='true' />
                  </button>
                </li>
              );
            })}
          </ul>
          <p className='text-sm text-neutral-muted'>{learnCopy(lang, 'quizBankCount', { count: TOTAL_QUESTIONS, categories: quizCategories.length })}</p>
        </div>
      ) : (
        <div data-quiz-results className='mx-auto max-w-2xl space-y-6'>
          <section className='audit-panel space-y-3 p-4 sm:p-6'>
            <h2 ref={resultHeading} tabIndex={-1} className='font-display text-3xl font-bold outline-none'>
              {learnCopy(lang, 'quizResult', { score, total })}
            </h2>
            {game.category
              ? <p className='text-sm text-neutral-muted'>{categoryLabel(game.category)}</p>
              : <p className='text-sm text-neutral-muted'>{learnCopy(lang, 'quizQuick')}</p>}
            <div className='flex flex-wrap gap-2'>
              <button type='button' onClick={() => start(game.category)} className='audit-control'>{learnCopy(lang, 'quizReplay')}</button>
              <button type='button' onClick={reset} className='audit-control'>{learnCopy(lang, 'quizAllCategories')}</button>
            </div>
          </section>

          <section aria-labelledby='quiz-review' className='audit-panel space-y-3 p-4 sm:p-6'>
            <h2 id='quiz-review' className='text-audit-heading font-semibold'>{learnCopy(lang, 'quizReview')}</h2>
            <ol className='divide-y divide-neutral-border'>
              {game.answers.map((choice, index) => {
                const question = game.questions[index];
                const correct = choice === question.correctIndex;
                return (
                  <li key={question.id} className='space-y-1 py-3 text-sm'>
                    <h3 lang='en' className='font-semibold'>{question.question}</h3>
                    <p className={correct ? 'font-semibold text-signal-good' : 'font-semibold text-signal-alarm'}>
                      {learnCopy(lang, correct ? 'quizCorrect' : 'quizIncorrect')}
                    </p>
                    {!correct && (
                      <dl>
                        <div><dt className='inline font-semibold'>{learnCopy(lang, 'quizSelectedAnswer')}</dt>{' '}<dd className='inline' lang='en'>{question.options[choice]}</dd></div>
                        <div><dt className='inline font-semibold'>{learnCopy(lang, 'quizCorrectAnswer')}</dt>{' '}<dd className='inline' lang='en'>{question.options[question.correctIndex]}</dd></div>
                      </dl>
                    )}
                    <p lang='en'>{question.explanation}</p>
                    <QuizCitation questionId={question.id} />
                  </li>
                );
              })}
            </ol>
          </section>
        </div>
      )}
    </PageShell>
  );
}

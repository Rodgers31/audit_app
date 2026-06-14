/**
 * QuizGame — Gamified, immersive quiz experience.
 *
 * Features:
 *   • Category select screen with gradient cards
 *   • Animated question flow with instant feedback
 *   • Streak tracking, score counter, progress ring
 *   • Explanation + "Did you know?" after each answer
 *   • Celebration confetti on quiz completion
 *   • "Quick Play" mode picks 10 random questions across categories
 */
'use client';

import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle2,
  Flame,
  RotateCcw,
  Sparkles,
  Trophy,
  XCircle,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  getRandomQuestions,
  quizCategories,
  QuizCategory,
  QuizQuestion,
  TOTAL_QUESTIONS,
} from '@/data/quizData';

/* ──────────────────────────────────────
   Types
   ────────────────────────────────────── */
type Phase = 'categories' | 'playing' | 'feedback' | 'results';

interface GameState {
  phase: Phase;
  category: QuizCategory | null;
  questions: QuizQuestion[];
  index: number;
  selected: number | null;
  answers: { questionId: string; selected: number; correct: boolean }[];
  streak: number;
  bestStreak: number;
}

const QUICK_PLAY_COUNT = 10;

/* ──────────────────────────────────────
   Tiny progress ring (SVG)
   ────────────────────────────────────── */
function ProgressRing({ current, total }: { current: number; total: number }) {
  const r = 18;
  const circ = 2 * Math.PI * r;
  const pct = total > 0 ? current / total : 0;

  return (
    <svg width={48} height={48} className='rotate-[-90deg]'>
      <circle cx={24} cy={24} r={r} fill='none' stroke='#e5e7eb' strokeWidth={4} />
      <motion.circle
        cx={24}
        cy={24}
        r={r}
        fill='none'
        stroke='#4A7C5C'
        strokeWidth={4}
        strokeLinecap='round'
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: circ * (1 - pct) }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </svg>
  );
}

/* ──────────────────────────────────────
   Confetti burst (lightweight)
   ────────────────────────────────────── */
function ConfettiBurst() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 40 }, (_, i) => ({
        id: i,
        x: Math.random() * 300 - 150,
        y: -(Math.random() * 400 + 100),
        rotate: Math.random() * 720,
        color: ['#D9A441', '#4A7C5C', '#C94A4A', '#0ea5e9', '#f59e0b', '#8b5cf6'][i % 6],
        size: Math.random() * 6 + 4,
        delay: Math.random() * 0.3,
      })),
    []
  );

  return (
    <div className='pointer-events-none fixed inset-0 z-50 overflow-hidden'>
      {pieces.map((p) => (
        <motion.div
          key={p.id}
          className='absolute rounded-sm'
          style={{
            width: p.size,
            height: p.size * 1.4,
            backgroundColor: p.color,
            left: '50%',
            top: '40%',
          }}
          initial={{ x: 0, y: 0, rotate: 0, opacity: 1 }}
          animate={{ x: p.x, y: p.y, rotate: p.rotate, opacity: 0 }}
          transition={{ duration: 1.4, delay: p.delay, ease: 'easeOut' }}
        />
      ))}
    </div>
  );
}

/* ══════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════ */
export default function QuizGame() {
  const [game, setGame] = useState<GameState>({
    phase: 'categories',
    category: null,
    questions: [],
    index: 0,
    selected: null,
    answers: [],
    streak: 0,
    bestStreak: 0,
  });

  const [showConfetti, setShowConfetti] = useState(false);

  /* ── Derived ── */
  const currentQ = game.questions[game.index] as QuizQuestion | undefined;
  const score = game.answers.filter((a) => a.correct).length;
  const total = game.questions.length;

  /* ── Start a category quiz ── */
  const startCategory = useCallback((cat: QuizCategory) => {
    setGame({
      phase: 'playing',
      category: cat,
      questions: [...cat.questions].sort(() => Math.random() - 0.5),
      index: 0,
      selected: null,
      answers: [],
      streak: 0,
      bestStreak: 0,
    });
  }, []);

  /* ── Quick Play ── */
  const startQuickPlay = useCallback(() => {
    setGame({
      phase: 'playing',
      category: null,
      questions: getRandomQuestions(QUICK_PLAY_COUNT),
      index: 0,
      selected: null,
      answers: [],
      streak: 0,
      bestStreak: 0,
    });
  }, []);

  /* ── Select answer → show feedback ── */
  const selectAnswer = useCallback(
    (idx: number) => {
      if (game.phase !== 'playing' || !currentQ) return;
      const correct = idx === currentQ.correctIndex;
      const newStreak = correct ? game.streak + 1 : 0;
      const newBest = Math.max(game.bestStreak, newStreak);

      setGame((prev) => ({
        ...prev,
        phase: 'feedback',
        selected: idx,
        streak: newStreak,
        bestStreak: newBest,
        answers: [...prev.answers, { questionId: currentQ.id, selected: idx, correct }],
      }));
    },
    [game.phase, game.streak, game.bestStreak, currentQ]
  );

  /* ── Next question or finish ── */
  const advance = useCallback(() => {
    if (game.index + 1 >= game.questions.length) {
      setGame((prev) => ({ ...prev, phase: 'results' }));
      setShowConfetti(true);
    } else {
      setGame((prev) => ({
        ...prev,
        phase: 'playing',
        index: prev.index + 1,
        selected: null,
      }));
    }
  }, [game.index, game.questions.length]);

  /* ── Reset back to categories ── */
  const reset = useCallback(() => {
    setGame({
      phase: 'categories',
      category: null,
      questions: [],
      index: 0,
      selected: null,
      answers: [],
      streak: 0,
      bestStreak: 0,
    });
  }, []);

  /* Turn off confetti after animation */
  useEffect(() => {
    if (showConfetti) {
      const t = setTimeout(() => setShowConfetti(false), 2000);
      return () => clearTimeout(t);
    }
  }, [showConfetti]);

  /* ──────────────────────────────────────
     CATEGORY SELECT
     ────────────────────────────────────── */
  if (game.phase === 'categories') {
    return (
      <div className='space-y-8'>
        {/* Quick-play banner */}
        <motion.button
          onClick={startQuickPlay}
          className='w-full relative overflow-hidden rounded-2xl bg-gradient-to-r from-gov-forest to-gov-dark p-6 text-left text-white shadow-elevated group'
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}>
          <div className='absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/5 group-hover:bg-white/10 transition-colors' />
          <div className='absolute -right-2 bottom-0 h-16 w-16 rounded-full bg-white/5 group-hover:bg-white/10 transition-colors' />
          <div className='flex items-center gap-4'>
            <div className='flex h-14 w-14 items-center justify-center rounded-xl bg-gov-gold/20'>
              <Zap size={28} className='text-gov-gold' />
            </div>
            <div>
              <h3 className='text-xl font-bold'>Quick Play</h3>
              <p className='text-sm text-white/70'>
                {QUICK_PLAY_COUNT} random questions from all categories — test your overall
                knowledge!
              </p>
            </div>
          </div>
          <ArrowRight
            size={20}
            className='absolute right-5 top-1/2 -translate-y-1/2 text-white/40 group-hover:text-white/80 transition-colors'
          />
        </motion.button>

        {/* Category grid */}
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {quizCategories.map((cat, i) => (
            <motion.button
              key={cat.id}
              onClick={() => startCategory(cat)}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.45 }}
              whileHover={{ y: -4 }}
              whileTap={{ scale: 0.97 }}
              className='group relative overflow-hidden rounded-2xl bg-white/60 dark:bg-surface-elevated backdrop-blur border border-white/50 p-5 text-left shadow-surface hover:shadow-elevated transition-shadow'>
              {/* Gradient accent bar */}
              <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${cat.gradient}`} />
              <span className='text-3xl mb-3 block'>{cat.emoji}</span>
              <h3 className='font-bold text-gov-dark dark:text-white text-lg mb-1 group-hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                {cat.title}
              </h3>
              <p className='text-sm text-neutral-muted leading-relaxed mb-3'>{cat.description}</p>
              <div className='flex items-center justify-between'>
                <span className='text-xs font-medium text-gov-sage'>
                  {cat.questions.length} questions
                </span>
                <ArrowRight
                  size={16}
                  className='text-neutral-muted group-hover:text-gov-sage transition-colors'
                />
              </div>
            </motion.button>
          ))}
        </div>

        <p className='text-center text-sm text-neutral-muted'>
          {TOTAL_QUESTIONS} questions across {quizCategories.length} categories
        </p>
      </div>
    );
  }

  /* ──────────────────────────────────────
     PLAYING / FEEDBACK
     ────────────────────────────────────── */
  if ((game.phase === 'playing' || game.phase === 'feedback') && currentQ) {
    const isCorrect = game.selected === currentQ.correctIndex;

    return (
      <div className='mx-auto max-w-2xl space-y-6'>
        {/* Top bar: progress ring + streak + quit */}
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-3'>
            <div className='relative flex items-center justify-center'>
              <ProgressRing current={game.index + 1} total={total} />
              <span className='absolute text-xs font-bold text-gov-dark dark:text-white'>
                {game.index + 1}/{total}
              </span>
            </div>

            {game.streak > 1 && (
              <motion.div
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className='flex items-center gap-1 rounded-full bg-orange-100 px-3 py-1 text-sm font-bold text-orange-700'>
                <Flame size={14} /> {game.streak} streak
              </motion.div>
            )}
          </div>

          <button
            onClick={reset}
            className='text-sm text-neutral-muted hover:text-gov-dark dark:text-white transition-colors'>
            Quit
          </button>
        </div>

        {/* Question card */}
        <AnimatePresence mode='wait'>
          <motion.div
            key={currentQ.id}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -40 }}
            transition={{ duration: 0.35 }}
            className='rounded-2xl bg-white/70 dark:bg-surface-elevated backdrop-blur-xl border border-white/60 shadow-elevated p-6 sm:p-8'>
            {/* Difficulty badge */}
            <span
              className={`mb-4 inline-block rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wide ${
                currentQ.difficulty === 'easy'
                  ? 'bg-green-100 text-green-700'
                  : currentQ.difficulty === 'medium'
                    ? 'bg-yellow-100 text-yellow-700'
                    : 'bg-red-100 text-red-700'
              }`}>
              {currentQ.difficulty}
            </span>

            <h3 className='mb-6 text-xl font-bold leading-snug text-gov-dark dark:text-white'>
              {currentQ.question}
            </h3>

            {/* Options */}
            <div className='space-y-3'>
              {currentQ.options.map((opt, i) => {
                const isFeedback = game.phase === 'feedback';
                const isSelected = game.selected === i;
                const isAnswer = i === currentQ.correctIndex;

                let ring = 'border-neutral-border hover:border-gov-sage/60';
                let bg = 'bg-white/60 dark:bg-surface-elevated hover:bg-white/80 dark:bg-surface-elevated';
                let textColor = 'text-gov-dark dark:text-white';

                if (isFeedback && isAnswer) {
                  ring = 'border-green-400 ring-2 ring-green-200';
                  bg = 'bg-green-50';
                  textColor = 'text-green-800';
                } else if (isFeedback && isSelected && !isAnswer) {
                  ring = 'border-red-400 ring-2 ring-red-200';
                  bg = 'bg-red-50';
                  textColor = 'text-red-800';
                } else if (!isFeedback && isSelected) {
                  ring = 'border-gov-sage ring-2 ring-gov-sage/30';
                  bg = 'bg-gov-sage/10';
                }

                return (
                  <motion.button
                    key={i}
                    onClick={() => !isFeedback && selectAnswer(i)}
                    disabled={isFeedback}
                    whileHover={!isFeedback ? { scale: 1.015 } : {}}
                    whileTap={!isFeedback ? { scale: 0.985 } : {}}
                    className={`w-full text-left rounded-xl border p-4 transition-all ${ring} ${bg} ${textColor} ${
                      isFeedback ? 'cursor-default' : 'cursor-pointer'
                    }`}>
                    <div className='flex items-center gap-3'>
                      <span className='flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-bold'>
                        {String.fromCharCode(65 + i)}
                      </span>
                      <span className='font-medium'>{opt}</span>
                      {isFeedback && isAnswer && (
                        <CheckCircle2 size={18} className='ml-auto text-green-600' />
                      )}
                      {isFeedback && isSelected && !isAnswer && (
                        <XCircle size={18} className='ml-auto text-red-500' />
                      )}
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Feedback panel (explanation) */}
        <AnimatePresence>
          {game.phase === 'feedback' && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              className='space-y-4'>
              <div
                className={`rounded-2xl p-5 ${
                  isCorrect
                    ? 'bg-green-50 border border-green-200'
                    : 'bg-red-50 border border-red-200'
                }`}>
                <div className='flex items-center gap-2 mb-2'>
                  {isCorrect ? (
                    <>
                      <Sparkles size={18} className='text-green-600' />
                      <span className='font-bold text-green-700'>Correct!</span>
                    </>
                  ) : (
                    <>
                      <XCircle size={18} className='text-red-600' />
                      <span className='font-bold text-red-700'>Not quite</span>
                    </>
                  )}
                </div>
                <p className='text-sm leading-relaxed text-gov-dark/80 dark:text-white/80'>{currentQ.explanation}</p>
              </div>

              <motion.button
                onClick={advance}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                className='flex w-full items-center justify-center gap-2 rounded-xl bg-gov-forest px-6 py-3 font-semibold text-white shadow-surface hover:bg-gov-dark transition-colors'>
                {game.index + 1 < total ? 'Next Question' : 'See Results'}
                <ArrowRight size={18} />
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  /* ──────────────────────────────────────
     RESULTS
     ────────────────────────────────────── */
  if (game.phase === 'results') {
    const pct = total > 0 ? Math.round((score / total) * 100) : 0;
    const grade =
      pct >= 90
        ? { label: 'Outstanding!', emoji: '🏆', color: 'text-gov-gold' }
        : pct >= 70
          ? { label: 'Great job!', emoji: '🌟', color: 'text-gov-sage' }
          : pct >= 50
            ? { label: 'Good effort!', emoji: '👍', color: 'text-sky-600' }
            : { label: 'Keep learning!', emoji: '📚', color: 'text-gov-copper' };

    return (
      <>
        {showConfetti && <ConfettiBurst />}

        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          className='mx-auto max-w-lg text-center space-y-6'>
          <div className='rounded-2xl bg-white/70 dark:bg-surface-elevated backdrop-blur-xl border border-white/60 shadow-elevated p-8'>
            <span className='text-5xl mb-2 block'>{grade.emoji}</span>
            <h2 className={`text-3xl font-display ${grade.color} mb-1`}>{grade.label}</h2>
            <p className='text-neutral-muted mb-6'>
              {game.category ? game.category.title : 'Quick Play'}
            </p>

            {/* Score ring */}
            <div className='relative mx-auto mb-6 h-32 w-32'>
              <svg viewBox='0 0 120 120' className='rotate-[-90deg]'>
                <circle cx={60} cy={60} r={50} fill='none' stroke='#e5e7eb' strokeWidth={8} />
                <motion.circle
                  cx={60}
                  cy={60}
                  r={50}
                  fill='none'
                  stroke='#4A7C5C'
                  strokeWidth={8}
                  strokeLinecap='round'
                  strokeDasharray={2 * Math.PI * 50}
                  initial={{ strokeDashoffset: 2 * Math.PI * 50 }}
                  animate={{
                    strokeDashoffset: 2 * Math.PI * 50 * (1 - pct / 100),
                  }}
                  transition={{ duration: 1, ease: 'easeOut' }}
                />
              </svg>
              <div className='absolute inset-0 flex flex-col items-center justify-center'>
                <span className='text-3xl font-bold text-gov-dark dark:text-white'>{pct}%</span>
                <span className='text-xs text-neutral-muted'>
                  {score}/{total}
                </span>
              </div>
            </div>

            {/* Stats row */}
            <div className='flex justify-center gap-6 mb-6 text-sm'>
              <div className='flex items-center gap-1 text-green-600'>
                <CheckCircle2 size={16} /> {score} correct
              </div>
              <div className='flex items-center gap-1 text-red-500'>
                <XCircle size={16} /> {total - score} wrong
              </div>
              {game.bestStreak > 1 && (
                <div className='flex items-center gap-1 text-orange-600'>
                  <Flame size={16} /> {game.bestStreak} best streak
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className='flex flex-col sm:flex-row gap-3 justify-center'>
              <motion.button
                onClick={() => (game.category ? startCategory(game.category) : startQuickPlay())}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                className='inline-flex items-center justify-center gap-2 rounded-xl bg-gov-forest px-5 py-3 font-semibold text-white hover:bg-gov-dark transition-colors'>
                <RotateCcw size={16} /> Play Again
              </motion.button>
              <motion.button
                onClick={reset}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                className='inline-flex items-center justify-center gap-2 rounded-xl border border-neutral-border bg-white/60 dark:bg-surface-elevated px-5 py-3 font-semibold text-gov-dark dark:text-white hover:bg-white dark:bg-surface-base transition-colors'>
                <Trophy size={16} /> All Categories
              </motion.button>
            </div>
          </div>

          {/* Review answers */}
          <div className='rounded-2xl bg-white/50 dark:bg-surface-elevated backdrop-blur border border-white/40 p-5 text-left'>
            <h3 className='font-bold text-gov-dark dark:text-white mb-3'>Review Answers</h3>
            <div className='space-y-2'>
              {game.answers.map((a, i) => {
                const q = game.questions[i];
                return (
                  <div
                    key={i}
                    className={`rounded-lg px-4 py-3 text-sm ${
                      a.correct
                        ? 'bg-green-50 border border-green-100'
                        : 'bg-red-50 border border-red-100'
                    }`}>
                    <div className='flex items-start gap-2'>
                      {a.correct ? (
                        <CheckCircle2 size={16} className='mt-0.5 shrink-0 text-green-600' />
                      ) : (
                        <XCircle size={16} className='mt-0.5 shrink-0 text-red-500' />
                      )}
                      <div>
                        <p className='font-medium text-gov-dark dark:text-white'>{q.question}</p>
                        {!a.correct && (
                          <p className='mt-1 text-xs text-neutral-muted'>
                            Correct: {q.options[q.correctIndex]}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      </>
    );
  }

  return null;
}

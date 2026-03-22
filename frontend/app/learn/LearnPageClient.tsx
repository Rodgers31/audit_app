/**
 * Learning Hub — Single-page with sticky section navigator.
 *
 * The "Your Learning Journey" stepper stays pinned below the header.
 * Clicking a step switches the content shown below it inline — no
 * page navigation, feels like one continuous page.
 */
'use client';

// TODO: Re-enable when real video content is ready
// import ExplainerVideos from '@/components/ExplainerVideos';
import InteractiveGlossary from '@/components/InteractiveGlossary';
import PageShell from '@/components/layout/PageShell';
import GovernmentExplorer from '@/components/learn/GovernmentExplorer';
import QuizGame from '@/components/learn/QuizGame';
import WhyThisMatters from '@/components/WhyThisMatters';
import { TOTAL_QUESTIONS } from '@/data/quizData';
import { AnimatePresence, motion, useInView } from 'framer-motion';
import {
  ArrowRight,
  BookOpen,
  Brain,
  Gamepad2,
  GraduationCap,
  Landmark,
  Lightbulb,
  // Play,  // TODO: Re-enable for videos step
  Sparkles,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useRef, useState } from 'react';

/* ── Animated counter ── */
function AnimatedNumber({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: '-40px' });
  const [display, setDisplay] = useState(0);

  const started = useRef(false);
  if (inView && !started.current) {
    started.current = true;
    let frame = 0;
    const totalFrames = 40;
    const step = value / totalFrames;
    const tick = () => {
      frame++;
      setDisplay(Math.min(Math.round(step * frame), value));
      if (frame < totalFrames) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  return <span ref={ref}>{display}</span>;
}

/* ── Step config ── */
// TODO: Re-enable 'videos' when real content is ready
// type SectionId = 'quiz' | 'government' | 'glossary' | 'videos' | 'why';
type SectionId = 'quiz' | 'government' | 'glossary' | 'why';

interface Step {
  id: SectionId;
  n: number;
  title: string;
  desc: string;
  icon: React.ElementType;
  gradient: string;
}

const steps: Step[] = [
  {
    id: 'quiz',
    n: 1,
    title: 'Play',
    desc: 'Quiz games',
    icon: Gamepad2,
    gradient: 'from-emerald-500 to-teal-600',
  },
  {
    id: 'government',
    n: 2,
    title: 'Explore',
    desc: 'Government',
    icon: Landmark,
    gradient: 'from-sky-500 to-indigo-600',
  },
  {
    id: 'glossary',
    n: 3,
    title: 'Study',
    desc: 'Key terms',
    icon: BookOpen,
    gradient: 'from-violet-500 to-purple-600',
  },
  // TODO: Re-enable when real video content is ready
  // {
  //   id: 'videos',
  //   n: 4,
  //   title: 'Watch',
  //   desc: 'Videos',
  //   icon: Play,
  //   gradient: 'from-rose-500 to-red-600',
  // },
  {
    id: 'why',
    n: 4,
    title: 'Apply',
    desc: 'Real impact',
    icon: Lightbulb,
    gradient: 'from-amber-500 to-orange-600',
  },
];

/* ═══════════════════════════════════════
   PAGE
   ═══════════════════════════════════════ */
export default function LearningHubPage() {
  const [active, setActive] = useState<SectionId>('quiz');
  const [glossarySearch, setGlossarySearch] = useState('');
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  const switchSection = useCallback((id: SectionId) => {
    setActive(id);
    // Scroll the non-sticky anchor into view so the stepper appears at the top
    scrollAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  return (
    <PageShell
      title='Learning Hub'
      subtitle="Understand how Kenya's government works, where your taxes go, and how to hold leaders accountable">
      {/* ── Quick Stats ── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className='grid grid-cols-3 gap-4'>
        {[
          { value: 6, label: 'Quiz Categories', icon: Gamepad2, color: 'text-gov-forest' },
          { value: TOTAL_QUESTIONS, label: 'Quiz Questions', icon: Brain, color: 'text-gov-gold' },
          { value: 8, label: 'Glossary Terms', icon: BookOpen, color: 'text-sky-600' },
          // TODO: Re-enable when real video content is ready
          // { value: 6, label: 'Video Lessons', icon: Play, color: 'text-gov-copper' },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <motion.div
              key={s.label}
              whileHover={{ y: -3 }}
              className='rounded-xl bg-white/60 backdrop-blur border border-white/50 p-4 text-center shadow-surface'>
              <Icon size={18} className={`mx-auto mb-2 ${s.color}`} />
              <div className={`text-2xl font-bold ${s.color}`}>
                <AnimatedNumber value={s.value} />
              </div>
              <div className='text-xs text-neutral-muted mt-1'>{s.label}</div>
            </motion.div>
          );
        })}
      </motion.div>

      {/* ══════════════════════════════════
         STICKY LEARNING JOURNEY STEPPER
         ══════════════════════════════════ */}
      {/* Non-sticky scroll anchor — scrollIntoView targets this */}
      <div ref={scrollAnchorRef} className='scroll-mt-[72px]' aria-hidden />
      <div className='sticky top-[72px] z-20'>
        <div className='rounded-2xl bg-gradient-to-r from-gov-forest to-gov-dark p-4 sm:p-5 text-white relative overflow-hidden shadow-elevated'>
          {/* Decorative circles */}
          <div className='absolute -right-10 -top-10 h-32 w-32 rounded-full border border-white/10 pointer-events-none' />
          <div className='absolute -right-4 -bottom-4 h-20 w-20 rounded-full border border-white/5 pointer-events-none' />

          <div className='flex items-center gap-2 mb-3'>
            <GraduationCap size={18} className='text-gov-gold' />
            <h3 className='font-bold text-sm sm:text-base'>Your Learning Journey</h3>
          </div>

          {/* Steps row */}
          <div className='flex gap-1 sm:gap-2'>
            {steps.map((step) => {
              const isActive = active === step.id;
              const Icon = step.icon;

              return (
                <button
                  key={step.id}
                  onClick={() => switchSection(step.id)}
                  className={`relative flex-1 rounded-xl px-2 py-2.5 sm:px-3 sm:py-3 text-left transition-all duration-300 ${
                    isActive
                      ? 'bg-white/20 ring-2 ring-gov-gold shadow-lg scale-[1.02]'
                      : 'bg-white/5 hover:bg-white/10'
                  }`}>
                  {/* Active indicator bar */}
                  {isActive && (
                    <motion.div
                      layoutId='activeStep'
                      className={`absolute inset-x-0 top-0 h-1 rounded-t-xl bg-gradient-to-r ${step.gradient}`}
                      transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                    />
                  )}

                  <div className='flex items-center gap-1.5 sm:gap-2 mb-1'>
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                        isActive ? 'bg-gov-gold text-gov-dark' : 'bg-white/15 text-white/70'
                      }`}>
                      {isActive ? <Icon size={14} /> : step.n}
                    </span>
                    <span
                      className={`font-semibold text-xs sm:text-sm truncate transition-colors ${
                        isActive ? 'text-gov-gold' : 'text-white/70'
                      }`}>
                      {step.title}
                    </span>
                  </div>
                  <p
                    className={`text-[10px] sm:text-xs leading-tight truncate transition-colors ${
                      isActive ? 'text-white/90' : 'text-white/40'
                    }`}>
                    {step.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════
         SECTION CONTENT
         ══════════════════════════════════ */}
      <AnimatePresence mode='wait'>
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
          {active === 'quiz' && <QuizGame />}

          {active === 'government' && <GovernmentExplorer />}

          {active === 'glossary' && (
            <div className='space-y-4'>
              <div className='max-w-md'>
                <input
                  type='text'
                  placeholder='Search terms…'
                  value={glossarySearch}
                  onChange={(e) => setGlossarySearch(e.target.value)}
                  className='w-full rounded-xl border border-neutral-border bg-white/60 backdrop-blur px-4 py-2.5 text-sm placeholder:text-neutral-muted focus:outline-none focus:ring-2 focus:ring-gov-sage/40 transition-shadow'
                />
              </div>
              <InteractiveGlossary searchTerm={glossarySearch} />
            </div>
          )}

          {/* TODO: Re-enable when real video content is ready */}
          {/* {active === 'videos' && <ExplainerVideos searchTerm='' />} */}

          {active === 'why' && <WhyThisMatters searchTerm='' />}
        </motion.div>
      </AnimatePresence>

      {/* ── CTA ── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        className='rounded-2xl bg-gradient-to-br from-gov-forest via-gov-dark to-gov-forest p-8 sm:p-10 text-center text-white relative overflow-hidden'>
        <div className='absolute -left-10 -top-10 h-32 w-32 rounded-full bg-gov-gold/10' />
        <div className='absolute -right-8 -bottom-8 h-24 w-24 rounded-full bg-white/5' />
        <Sparkles size={28} className='mx-auto mb-4 text-gov-gold' />
        <h2 className='font-display text-2xl sm:text-3xl mb-3'>
          Ready to put your knowledge to use?
        </h2>
        <p className='text-white/70 max-w-lg mx-auto mb-6'>
          Explore live government data on our dashboard — track budgets, audit reports, and county
          spending in real time.
        </p>
        <Link
          href='/'
          className='inline-flex items-center gap-2 rounded-xl bg-gov-gold px-6 py-3 font-semibold text-gov-dark hover:bg-gov-gold/90 transition-colors shadow-elevated'>
          Go to Dashboard
          <ArrowRight size={16} />
        </Link>
      </motion.div>
    </PageShell>
  );
}

/**
 * Learning Hub — civic learning hub for AuditGava.
 *
 * Layout (top → bottom):
 *   1. LearnHero          — headline + hero search (hybrid BM25 + semantic)
 *   2. ConstitutionBook   — interactive reader for the Constitution
 *   3. Keep learning      — three entry points into dedicated practice pages
 *   4. PopularQuestions   — expandable civic FAQ
 *   5. CTA                — jump back to the dashboard
 *
 * The hero search pipes into the ConstitutionBook: number queries (e.g.
 * "Article 229") directly open that article; keyword queries seed the
 * book's search so the user sees matches in context.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import ConstitutionBook from '@/components/learn/constitution/ConstitutionBook';
import LearnHero from '@/components/learn/LearnHero';
import PopularQuestions from '@/components/learn/PopularQuestions';
import {
  CONSTITUTION_META,
  findChapterForArticle,
  TOTAL_ARTICLES,
} from '@/data/constitution';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Gamepad2,
  Heart,
  Landmark,
  Library,
  Sparkles,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useRef, useState } from 'react';

const KEEP_LEARNING: {
  href: string;
  eyebrow: string;
  title: string;
  description: string;
  icon: React.ElementType;
  accent: string;
  iconTint: string;
}[] = [
  {
    href: '/learn/quiz',
    eyebrow: 'Practice',
    title: 'Civic quiz',
    description:
      'Short, playful questions that turn what you just read into recall you can use.',
    icon: Gamepad2,
    accent:
      'from-gov-forest/10 via-white to-gov-sage/20 dark:from-gov-forest/[0.18] dark:via-surface-base dark:to-surface-elevated',
    iconTint: 'bg-gov-forest text-white',
  },
  {
    href: '/learn/government',
    eyebrow: 'Explore',
    title: 'Government explorer',
    description:
      'Walk through the three arms of government and the commissions that keep them honest.',
    icon: Landmark,
    accent:
      'from-gov-gold/15 via-white to-gov-sand dark:from-gov-gold/[0.18] dark:via-surface-base dark:to-surface-elevated',
    iconTint: 'bg-gov-gold text-gov-dark dark:text-white',
  },
  {
    href: '/learn/glossary',
    eyebrow: 'Reference',
    title: 'Plain-English glossary',
    description:
      'Every budget, audit and finance term, translated into language that actually makes sense.',
    icon: Library,
    accent:
      'from-gov-sage/15 via-white to-gov-cream dark:from-gov-sage/[0.22] dark:via-surface-base dark:to-surface-elevated',
    iconTint: 'bg-gov-sage text-white',
  },
  {
    href: '/learn/why-it-matters',
    eyebrow: 'Real life',
    title: 'Why this matters',
    description:
      'The stories behind each clause — how constitutional rights touch your day-to-day.',
    icon: Heart,
    accent:
      'from-rose-100 via-white to-gov-cream dark:from-rose-500/20 dark:via-surface-base dark:to-surface-elevated',
    iconTint: 'bg-rose-500 text-white',
  },
];

function parseArticleNumber(q: string): number | null {
  const trimmed = q.trim();
  const m = trimmed.match(/^(?:article|art\.?)\s+(\d+)$/i);
  if (m) return parseInt(m[1]!, 10);
  if (/^\d{1,3}$/.test(trimmed)) return parseInt(trimmed, 10);
  return null;
}

export default function LearningHubPage() {
  /* ── Constitution book seeding ── */
  const [seedQuery, setSeedQuery] = useState<string>('');
  const [seedChapter, setSeedChapter] = useState<number>(12);
  const [seedArticle, setSeedArticle] = useState<number | undefined>(229);
  const [bookKey, setBookKey] = useState<number>(0);
  const bookRef = useRef<HTMLDivElement>(null);

  const scrollToBook = useCallback(() => {
    // Small delay so that:
    //   • React has committed the state update (bookKey bump, seeds)
    //   • The ConstitutionBook's own re-focus/re-fetch effects have run
    //   • The exit animation of the hero dropdown has finished its first frame
    // Smooth scroll otherwise gets silently cancelled by those concurrent layout
    // shifts on some browsers.
    setTimeout(() => {
      bookRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  }, []);

  const openArticle = useCallback(
    (articleNumber: number) => {
      const meta = findChapterForArticle(articleNumber);
      if (!meta) return;
      setSeedChapter(meta.number);
      setSeedArticle(articleNumber);
      setSeedQuery('');
      setBookKey((k) => k + 1);
      scrollToBook();
    },
    [scrollToBook]
  );

  /** Jump to a specific chapter + article (used by hero autocomplete). */
  const jumpToArticle = useCallback(
    (chapterNumber: number, articleNumber: number) => {
      setSeedChapter(chapterNumber);
      setSeedArticle(articleNumber);
      setSeedQuery('');
      setBookKey((k) => k + 1);
      scrollToBook();
    },
    [scrollToBook]
  );

  const handleHeroSearch = useCallback(
    (raw: string) => {
      const q = raw.trim();
      if (!q) return;
      const articleNum = parseArticleNumber(q);
      if (articleNum !== null) {
        openArticle(articleNum);
        return;
      }
      setSeedQuery(q);
      setBookKey((k) => k + 1);
      scrollToBook();
    },
    [openArticle, scrollToBook]
  );

  return (
    <PageShell
      title='Learning Hub'
      subtitle='Understand the rules behind every shilling — the Constitution, budgets, audits and devolution, in plain Kenyan English.'>
      {/* 1 ── Hero ─────────────────────────────────── */}
      <LearnHero onSearchSubmit={handleHeroSearch} onArticleSelect={jumpToArticle} />

      {/* 2 ── Constitution book ───────────────────── */}
      <div ref={bookRef} className='scroll-mt-[72px]'>
        <div className='mb-3 flex items-end justify-between gap-4'>
          <div>
            <h2 className='font-display text-2xl leading-tight text-gov-dark dark:text-white sm:text-[1.7rem]'>
              The Constitution, as a book you can actually read
            </h2>
            <p className='text-sm text-neutral-muted'>
              {CONSTITUTION_META.length} chapters, {TOTAL_ARTICLES} articles, every one with a plain-English note.
            </p>
          </div>
          <Link
            href='#constitution-book'
            className='hidden shrink-0 items-center gap-1.5 rounded-full bg-gov-forest/10 px-3 py-1.5 text-xs font-semibold text-gov-forest dark:text-emerald-100 hover:bg-gov-forest/15 sm:inline-flex'>
            <Sparkles size={12} />
            New
          </Link>
        </div>
        <ConstitutionBook
          key={bookKey}
          initialChapter={seedChapter}
          initialArticle={seedArticle}
          seedQuery={seedQuery}
        />
      </div>

      {/* 3 ── Keep learning ───────────────────────── */}
      <section aria-labelledby='keep-learning-heading' className='space-y-4'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div>
            <h2
              id='keep-learning-heading'
              className='font-display text-2xl leading-tight text-gov-dark dark:text-white sm:text-[1.7rem]'>
              Keep learning
            </h2>
            <p className='text-sm text-neutral-muted'>
              Four focused stops once you&rsquo;ve closed the book — pick whichever fits your
              mood.
            </p>
          </div>
        </div>

        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4'>
          {KEEP_LEARNING.map((card, i) => {
            const Icon = card.icon;
            return (
              <motion.div
                key={card.href}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ duration: 0.4, delay: i * 0.06 }}>
                <Link
                  href={card.href}
                  className={`group relative flex h-full flex-col overflow-hidden rounded-2xl border border-white/70 dark:border-neutral-border bg-gradient-to-br ${card.accent} p-5 shadow-surface transition-shadow hover:shadow-elevated`}>
                  <span
                    className={`inline-flex h-10 w-10 items-center justify-center rounded-xl ${card.iconTint} shadow-surface`}>
                    <Icon size={18} />
                  </span>
                  <div className='mt-4 text-[11px] font-semibold uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
                    {card.eyebrow}
                  </div>
                  <h3 className='mt-0.5 font-display text-lg text-gov-dark dark:text-white'>
                    {card.title}
                  </h3>
                  <p className='mt-1 flex-1 text-[13.5px] leading-relaxed text-neutral-text'>
                    {card.description}
                  </p>
                  <span className='mt-4 inline-flex items-center gap-1 text-sm font-semibold text-gov-forest dark:text-emerald-100 transition-transform group-hover:translate-x-0.5'>
                    Open
                    <ArrowRight size={14} />
                  </span>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* 4 ── Popular questions ───────────────────── */}
      <PopularQuestions onOpenArticle={openArticle} />

      {/* 5 ── CTA ─────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 22 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        className='relative overflow-hidden rounded-3xl bg-gradient-to-br from-gov-forest via-gov-dark to-gov-forest p-8 text-center text-white sm:p-10'>
        <div className='pointer-events-none absolute -left-10 -top-10 h-32 w-32 rounded-full bg-gov-gold/10' />
        <div className='pointer-events-none absolute -right-8 -bottom-8 h-24 w-24 rounded-full bg-white/5' />
        <Sparkles size={26} className='mx-auto mb-3 text-gov-gold' />
        <h2 className='font-display text-2xl sm:text-3xl'>
          Ready to put your knowledge to use?
        </h2>
        <p className='mx-auto mt-2 max-w-lg text-white/75'>
          Explore live government data — audits, budgets, debt and county spending — powered by the
          same constitutional rules you just read.
        </p>
        <Link
          href='/'
          className='mt-6 inline-flex items-center gap-2 rounded-xl bg-gov-gold px-6 py-3 font-semibold text-gov-dark dark:text-white shadow-elevated transition-colors hover:bg-gov-gold/90'>
          Go to dashboard
          <ArrowRight size={16} />
        </Link>
      </motion.div>
    </PageShell>
  );
}

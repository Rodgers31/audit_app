/**
 * PopularQuestions — expandable FAQ for the Learn hub.
 *
 * One question open at a time. Each row carries a category icon, a small
 * uppercase eyebrow (category · article), and the question itself. The
 * expanded panel pulls in a gold border rail so the answer feels
 * anchored to the row above it.
 */
'use client';

import { POPULAR_QUESTIONS, type PopularQuestion } from '@/data/popularQuestions';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Banknote,
  ChevronDown,
  ExternalLink,
  HelpCircle,
  MapPin,
  ScrollText,
  ShieldCheck,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

const CATEGORY_ICON: Record<PopularQuestion['category'], LucideIcon> = {
  Budget: Wallet,
  Audit: ShieldCheck,
  Debt: Banknote,
  Devolution: MapPin,
  Citizens: Users,
  Constitution: ScrollText,
};

interface Props {
  /** Scrolls to ConstitutionBook and opens the given article, if set. */
  onOpenArticle?: (articleNumber: number) => void;
}

export default function PopularQuestions({ onOpenArticle }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <section aria-labelledby='popular-questions-heading' className='space-y-4'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h2
            id='popular-questions-heading'
            className='font-display text-2xl leading-tight text-gov-dark dark:text-white sm:text-[1.7rem]'>
            Popular questions
          </h2>
          <p className='text-sm text-neutral-muted'>
            Real questions from Kenyans — each answered in a few sentences, with the
            article behind it.
          </p>
        </div>
        <span className='inline-flex shrink-0 items-center gap-1.5 rounded-full bg-gov-forest/10 px-3 py-1.5 text-[11.5px] font-semibold text-gov-forest dark:text-emerald-100'>
          <HelpCircle size={12} />
          {POPULAR_QUESTIONS.length} questions · linked to the law
        </span>
      </div>

      <ul className='overflow-hidden rounded-2xl border border-white/70 dark:border-neutral-border bg-gradient-to-br from-white/85 via-white/70 to-gov-cream/50 dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated shadow-surface backdrop-blur'>
        {POPULAR_QUESTIONS.map((q, i) => {
          const Icon = CATEGORY_ICON[q.category];
          const isOpen = openId === q.id;
          const isLast = i === POPULAR_QUESTIONS.length - 1;
          return (
            <li
              key={q.id}
              className={isLast ? '' : 'border-b border-neutral-border/40'}>
              <button
                type='button'
                onClick={() => setOpenId(isOpen ? null : q.id)}
                aria-expanded={isOpen}
                className={`group flex w-full items-start gap-3 px-4 py-3 text-left transition-colors sm:gap-3.5 sm:px-5 sm:py-3.5 ${
                  isOpen ? 'bg-gov-forest/[0.05]' : 'hover:bg-gov-forest/[0.03]'
                }`}>
                <span
                  className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
                    isOpen
                      ? 'bg-gov-forest text-white shadow-surface'
                      : 'bg-gov-forest/10 text-gov-forest dark:text-emerald-100 group-hover:bg-gov-forest/15'
                  }`}>
                  <Icon size={14} />
                </span>
                <span className='min-w-0 flex-1'>
                  <span className='flex flex-wrap items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
                    <span>{q.category}</span>
                    {q.articleNumber && (
                      <>
                        <span className='text-neutral-border'>·</span>
                        <span>Article {q.articleNumber}</span>
                      </>
                    )}
                  </span>
                  <span className='mt-0.5 block text-[13px] font-semibold leading-snug text-gov-dark dark:text-white sm:text-[13.5px]'>
                    {q.question}
                  </span>
                </span>
                <motion.span
                  animate={{ rotate: isOpen ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                  className='mt-1 shrink-0 text-neutral-muted group-hover:text-gov-forest dark:text-emerald-100'>
                  <ChevronDown size={16} />
                </motion.span>
              </button>

              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className='overflow-hidden'>
                    <div className='bg-gov-forest/[0.04] px-4 pb-4 pt-1 sm:px-5'>
                      <div className='ml-[44px] border-l-2 border-gov-gold/50 pl-3.5 sm:ml-[46px]'>
                        <p className='text-[13px] leading-relaxed text-gov-dark/90 dark:text-white/90 sm:text-[13.5px]'>
                          {q.answer}
                        </p>
                        {(q.articleNumber || q.learnMoreHref) && (
                          <div className='mt-3 flex flex-wrap gap-2'>
                            {q.articleNumber && onOpenArticle && (
                              <button
                                type='button'
                                onClick={() => onOpenArticle(q.articleNumber!)}
                                className='inline-flex items-center gap-1.5 rounded-full bg-gov-forest px-3 py-1 text-[11.5px] font-semibold text-white transition-colors hover:bg-gov-dark'>
                                <ScrollText size={11} />
                                Read Article {q.articleNumber}
                              </button>
                            )}
                            {q.learnMoreHref && (
                              <Link
                                href={q.learnMoreHref}
                                className='inline-flex items-center gap-1.5 rounded-full bg-gov-forest/10 px-3 py-1 text-[11.5px] font-semibold text-gov-forest dark:text-emerald-100 hover:bg-gov-forest/15'>
                                Learn more
                                <ExternalLink size={11} />
                              </Link>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

import { ArrowUpRight } from 'lucide-react';
import type { QuizQuestion } from '@/data/quizData';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { quizArticleReferences } from './quizArticleReferences';

export default function QuizCitation({ question }: { question: QuizQuestion }) {
  const { lang } = useLang();
  const reference = quizArticleReferences.get(question.id);
  const link = (href: string, label: string) => (
    <a href={href} target='_blank' rel='noopener noreferrer'
      className='inline-flex min-h-11 min-w-11 items-center gap-1.5 rounded px-1 text-sm font-semibold text-neutral-text underline decoration-neutral-muted underline-offset-4 focus-visible:outline-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100'>
      <span>{label}<span className='sr-only'> ({learnCopy(lang, 'quizNewTab')})</span></span>
      <ArrowUpRight aria-hidden='true' size={16} className='shrink-0' />
    </a>
  );

  if (question.sourceUrl) {
    return (
      <div className='flex flex-wrap gap-x-3'>
        {link('/debt', learnCopy(lang, 'quizDebtSeePage'))}
        {link(question.sourceUrl, learnCopy(lang, 'quizDebtSource'))}
      </div>
    );
  }

  if (!reference) return null;
  const label = learnCopy(lang, 'quizSourceArticle', { number: reference.article }) + (reference.clause ?? '');
  return link(`/learn?article=${reference.article}`, label);
}

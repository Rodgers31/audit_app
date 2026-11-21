import { ArrowUpRight } from 'lucide-react';
import type { QuizQuestion } from '@/data/quizData';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';

// Only explanations checked against the published text get an article link.
const articleReferences = new Map<string, { article: number; clause?: string }>([
  ['const-5', { article: 2, clause: '(1)' }],
  ['const-6', { article: 1, clause: '(1)' }],
  ['gov-2', { article: 97, clause: '(1)' }],
  ['gov-3', { article: 98, clause: '(1)' }],
  ['gov-5', { article: 152, clause: '(1)(d)' }],
  ['dev-1', { article: 6, clause: '(1)' }],
  ['dev-3', { article: 216, clause: '(1)(a)' }],
  ['dev-6', { article: 179, clause: '(2)' }],
  ['fin-2', { article: 228, clause: '(4)–(5)' }],
  ['fin-5', { article: 229, clause: '(4), (7)' }],
  ['fin-6', { article: 206, clause: '(1)' }],
  ['rights-1', { article: 35, clause: '(1)' }],
  ['rights-4', { article: 33, clause: '(1)' }],
  ['rights-5', { article: 25 }],
  ['rights-6', { article: 43, clause: '(1)' }],
]);

export default function QuizCitation({ question }: { question: QuizQuestion }) {
  const { lang } = useLang();
  const reference = articleReferences.get(question.id);
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

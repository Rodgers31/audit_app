'use client';

import QuizGame from '@/components/learn/QuizGame';
import { quizDebtQuestion } from '@/components/learn/quizDebtQuestion';
import { useLang } from '@/lib/i18n/LangProvider';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';

export default function LiveQuiz() {
  const { lang } = useLang();
  const { data } = useFiscalSummary();
  return <QuizGame liveQuestion={quizDebtQuestion(data?.current, lang)} />;
}

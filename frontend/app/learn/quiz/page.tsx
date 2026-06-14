/**
 * /learn/quiz — Dedicated quiz games page.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import QuizGame from '@/components/learn/QuizGame';

export default function QuizPage() {
  return (
    <PageShell
      title='Quiz Games'
      subtitle='Test your knowledge of the Kenyan Constitution, government structure, public finance, devolution, rights, and accountability'
      back={{ href: '/learn', label: 'Back to Learning Hub' }}>
      <QuizGame />
    </PageShell>
  );
}

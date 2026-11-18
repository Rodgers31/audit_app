import type { Metadata } from 'next';
import QuizGame from '@/components/learn/QuizGame';

export const metadata: Metadata = {
  title: 'Civic Quiz — AuditGava',
  description: 'Take a quiz about Kenya’s Constitution, government and public money.',
};

export default function QuizPage() {
  return <QuizGame />;
}

import type { Metadata } from 'next';
import LiveQuiz from './LiveQuiz';

export const metadata: Metadata = {
  title: 'Civic Quiz — AuditGava',
  description: 'Take a quiz about Kenya’s Constitution, government and public money.',
};

export default function QuizPage() {
  return <LiveQuiz />;
}

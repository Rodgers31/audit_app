import { Metadata } from 'next';
import LearningHubPage from './LearnPageClient';

export const metadata: Metadata = {
  title: 'Learn — AuditGava',
  description:
    "Understand Kenya's public finance system. Glossary, explainers, quizzes, and videos about budgets, audits, and devolution.",
};

export default function LearnPage() {
  return <LearningHubPage />;
}

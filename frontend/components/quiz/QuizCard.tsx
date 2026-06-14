/**
 * QuizCard - Individual quiz selection card with metadata and start button
 * Shows quiz difficulty, duration, and completion status
 */
'use client';

import { motion } from 'framer-motion';
import { ArrowRight, CheckCircle } from 'lucide-react';

interface QuizCardProps {
  id: string;
  title: string;
  description: string;
  difficulty: 'beginner' | 'intermediate';
  estimatedTime: string;
  icon: string;
  questionCount: number;
  isCompleted: boolean;
  onStart: (quizId: string) => void;
}

export default function QuizCard({
  id,
  title,
  description,
  difficulty,
  estimatedTime,
  icon,
  questionCount,
  isCompleted,
  onStart,
}: QuizCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className='bg-white dark:bg-surface-base rounded-2xl border border-gray-200 dark:border-neutral-border p-6 hover:shadow-lg transition-all duration-300'>
      {/* Quiz Icon */}
      <div className='text-4xl mb-4'>{icon}</div>

      {/* Quiz Info */}
      <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text mb-2'>{title}</h3>
      <p className='text-gray-600 dark:text-neutral-muted text-sm mb-4'>{description}</p>

      {/* Metadata */}
      <div className='flex items-center gap-4 mb-6 text-sm text-gray-500 dark:text-neutral-muted/80'>
        <div
          className={`px-2 py-1 rounded-lg ${
            difficulty === 'beginner'
              ? 'bg-green-100 text-green-800'
              : 'bg-orange-100 text-orange-800'
          }`}>
          {difficulty}
        </div>
        <div>⏱️ {estimatedTime}</div>
      </div>

      {/* Footer */}
      <div className='flex items-center justify-between'>
        <div className='text-sm text-gray-600 dark:text-neutral-muted'>{questionCount} questions</div>

        <motion.button
          onClick={() => onStart(id)}
          className='flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-xl hover:bg-purple-700 transition-colors'
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}>
          Start Quiz
          <ArrowRight size={16} />
        </motion.button>
      </div>

      {/* Completion Badge */}
      {isCompleted && (
        <div className='mt-3 flex items-center gap-2 text-green-600 text-sm'>
          <CheckCircle size={16} />
          Completed
        </div>
      )}
    </motion.div>
  );
}

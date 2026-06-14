/**
 * QuizResults - Displays quiz completion results with score and performance breakdown
 * Shows correct/incorrect answers and retry options
 */
'use client';

import { motion } from 'framer-motion';
import { CheckCircle, RotateCcw, Trophy, XCircle } from 'lucide-react';

interface Question {
  question: string;
  options: string[];
  correctAnswer: number;
  explanation: string;
  funFact: string;
}

interface QuizResultsProps {
  score: number;
  totalQuestions: number;
  answers: number[];
  questions: Question[];
  quizTitle: string;
  onRetake: () => void;
  onBackToQuizzes: () => void;
}

export default function QuizResults({
  score,
  totalQuestions,
  answers,
  questions,
  quizTitle,
  onRetake,
  onBackToQuizzes,
}: QuizResultsProps) {
  const percentage = Math.round((score / totalQuestions) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className='text-center'>
      {/* Trophy and Score */}
      <Trophy size={64} className='text-yellow-500 mx-auto mb-6' />
      <h2 className='text-3xl font-bold text-gray-900 dark:text-neutral-text mb-4'>Quiz Complete!</h2>
      <div className='text-6xl font-bold text-blue-600 mb-2'>{percentage}%</div>
      <p className='text-xl text-gray-600 dark:text-neutral-muted mb-6'>
        You got {score} out of {totalQuestions} questions correct
      </p>

      {/* Performance Breakdown */}
      <div className='bg-blue-50 rounded-2xl p-6 mb-8'>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4'>Your Performance</h3>
        <div className='space-y-3'>
          {questions.map((question, index) => (
            <div key={index} className='flex items-center gap-3'>
              {answers[index] === question.correctAnswer ? (
                <CheckCircle size={20} className='text-green-500' />
              ) : (
                <XCircle size={20} className='text-red-500' />
              )}
              <span className='text-sm text-gray-700 dark:text-neutral-muted'>Question {index + 1}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div className='flex gap-4 justify-center'>
        <motion.button
          onClick={onRetake}
          className='flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors'
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}>
          <RotateCcw size={20} />
          Retake Quiz
        </motion.button>
        <motion.button
          onClick={onBackToQuizzes}
          className='flex items-center gap-2 px-6 py-3 bg-gray-600 text-white rounded-xl hover:bg-gray-700 transition-colors'
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}>
          Back to Quizzes
        </motion.button>
      </div>
    </motion.div>
  );
}

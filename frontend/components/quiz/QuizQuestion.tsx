/**
 * QuizQuestion - Individual quiz question component with options and progress
 * Handles answer selection and submission for a single question
 */
'use client';

import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';

interface QuizQuestionProps {
  question: string;
  options: string[];
  selectedAnswer: number | null;
  onAnswerSelect: (index: number) => void;
  onSubmit: () => void;
  currentIndex: number;
  totalQuestions: number;
}

export default function QuizQuestion({
  question,
  options,
  selectedAnswer,
  onAnswerSelect,
  onSubmit,
  currentIndex,
  totalQuestions,
}: QuizQuestionProps) {
  return (
    <div>
      {/* Progress Bar */}
      <div className='w-full bg-gray-200 dark:bg-surface-sunken rounded-full h-2 mb-8'>
        <motion.div
          className='bg-blue-600 h-2 rounded-full'
          initial={{ width: 0 }}
          animate={{ width: `${((currentIndex + 1) / totalQuestions) * 100}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>

      {/* Question */}
      <motion.div
        key={currentIndex}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}>
        <h3 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-6'>{question}</h3>

        {/* Answer Options */}
        <div className='space-y-3 mb-8'>
          {options.map((option, index) => (
            <motion.button
              key={index}
              onClick={() => onAnswerSelect(index)}
              className={`w-full p-4 text-left rounded-xl border transition-all duration-200 ${
                selectedAnswer === index
                  ? 'bg-blue-100 border-blue-300 text-blue-800'
                  : 'bg-white dark:bg-surface-base border-gray-200 dark:border-neutral-border hover:border-blue-300'
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}>
              <div className='flex items-center gap-3'>
                <div
                  className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                    selectedAnswer === index ? 'border-blue-500 bg-blue-500' : 'border-gray-300 dark:border-neutral-border'
                  }`}>
                  {selectedAnswer === index && <div className='w-2 h-2 bg-white dark:bg-surface-base rounded-full' />}
                </div>
                <span>{option}</span>
              </div>
            </motion.button>
          ))}
        </div>

        {/* Submit Button */}
        <motion.button
          onClick={onSubmit}
          disabled={selectedAnswer === null}
          className={`flex items-center gap-2 px-6 py-3 rounded-xl transition-all duration-200 ${
            selectedAnswer !== null
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-300 text-gray-500 dark:text-neutral-muted/80 cursor-not-allowed'
          }`}
          whileHover={selectedAnswer !== null ? { scale: 1.05 } : {}}
          whileTap={selectedAnswer !== null ? { scale: 0.95 } : {}}>
          {currentIndex < totalQuestions - 1 ? 'Next Question' : 'Finish Quiz'}
          <ArrowRight size={20} />
        </motion.button>
      </motion.div>
    </div>
  );
}

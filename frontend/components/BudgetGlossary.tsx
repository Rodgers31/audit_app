'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { HelpCircle } from 'lucide-react';
import { useRef, useState } from 'react';

interface BudgetGlossaryProps {
  term: string;
  children: React.ReactNode;
}

export default function BudgetGlossary({ term, children }: BudgetGlossaryProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);

  const definitions: { [key: string]: { definition: string; examples: string[] } } = {
    'Recurrent Expenditure': {
      definition:
        'Day-to-day costs that occur regularly to keep government operations running smoothly.',
      examples: [
        'Staff salaries and benefits',
        'Electricity and utility bills',
        'Office supplies and maintenance',
        'Fuel and transportation costs',
      ],
    },
    'Development Budget': {
      definition:
        'Long-term investments in infrastructure and projects that benefit future generations.',
      examples: [
        'Building new roads and bridges',
        'Constructing hospitals and schools',
        'Installing water systems',
        'Technology infrastructure',
      ],
    },
    'Conditional Grants': {
      definition: 'Money given to counties with specific requirements on how it must be spent.',
      examples: [
        'Healthcare improvement funds',
        'Education quality grants',
        'Infrastructure development money',
        'Emergency response funds',
      ],
    },
    'Capital Expenditure': {
      definition: 'Large purchases of assets that will be used for many years to provide services.',
      examples: [
        'Government vehicles and equipment',
        'Building construction and renovations',
        'Computer systems and technology',
        'Medical equipment for hospitals',
      ],
    },
    'Budget Deficit': {
      definition: 'When the government spends more money than it collects in taxes and revenue.',
      examples: [
        'Borrowing money to fund projects',
        'Using reserves from previous years',
        'Seeking loans from development partners',
        'Issuing government bonds',
      ],
    },
  };

  const glossaryData = definitions[term] || {
    definition: 'Budget terminology explained in simple terms.',
    examples: ['General budget information'],
  };

  const handleMouseEnter = (e: React.MouseEvent) => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setTooltipPosition({
        x: rect.left + rect.width / 2,
        y: rect.top - 10,
      });
    }
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <>
      <button
        ref={buttonRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className='inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 underline decoration-dotted underline-offset-2 decoration-indigo-400 hover:decoration-indigo-600 transition-colors'>
        {children}
        <HelpCircle size={14} className='opacity-60' />
      </button>

      {/* Tooltip Portal */}
      <AnimatePresence>
        {isHovered && (
          <div className='fixed inset-0 pointer-events-none z-50'>
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={{
                left: tooltipPosition.x,
                top: tooltipPosition.y,
                transform: 'translateX(-50%) translateY(-100%)',
              }}
              className='absolute bg-white dark:bg-surface-base rounded-xl shadow-2xl border border-gray-200 dark:border-neutral-border p-6 max-w-sm pointer-events-auto'>
              {/* Arrow */}
              <div
                className='absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0'
                style={{
                  borderLeft: '8px solid transparent',
                  borderRight: '8px solid transparent',
                  borderTop: '8px solid white',
                }}
              />

              {/* Content */}
              <div className='space-y-4'>
                <div className='flex items-center gap-2'>
                  <HelpCircle size={18} className='text-indigo-600' />
                  <h4 className='font-semibold text-gray-900 dark:text-neutral-text'>{term}</h4>
                </div>

                <p className='text-gray-700 dark:text-neutral-muted text-sm leading-relaxed'>{glossaryData.definition}</p>

                <div>
                  <h5 className='font-medium text-gray-900 dark:text-neutral-text text-sm mb-2'>Examples:</h5>
                  <ul className='space-y-1'>
                    {glossaryData.examples.map((example, index) => (
                      <li key={index} className='text-xs text-gray-600 dark:text-neutral-muted flex items-start gap-2'>
                        <span className='text-indigo-400 mt-1'>•</span>
                        <span>{example}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className='pt-2 border-t border-gray-100 dark:border-neutral-border'>
                  <p className='text-xs text-gray-500 dark:text-neutral-muted/80 italic'>
                    Hover over underlined terms for explanations
                  </p>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

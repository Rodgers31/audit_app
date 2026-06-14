/**
 * ActionSteps - Practical steps citizens can take to engage with government accountability
 * Provides actionable guidance for monitoring and influencing government spending
 */
'use client';

import { motion } from 'framer-motion';
import { CheckCircle } from 'lucide-react';

interface ActionStep {
  step: number;
  title: string;
  description: string;
  actions: string[];
}

export default function ActionSteps() {
  const actionSteps: ActionStep[] = [
    {
      step: 1,
      title: 'Stay Informed',
      description: 'Regularly check county and national budget documents',
      actions: [
        'Read simplified budget summaries',
        'Attend public budget forums',
        'Follow audit report releases',
        'Join community WhatsApp groups sharing budget updates',
      ],
    },
    {
      step: 2,
      title: 'Ask Questions',
      description: 'Engage with your elected representatives',
      actions: [
        'Ask your MP/MCA about specific budget allocations',
        'Request updates on project implementation',
        'Demand explanations for cost overruns',
        'Question why promised projects are delayed',
      ],
    },
    {
      step: 3,
      title: 'Monitor Implementation',
      description: 'Track if budgeted projects actually happen',
      actions: [
        'Visit project sites to verify progress',
        'Count actual vs. promised infrastructure',
        'Check if services are being delivered as planned',
        'Document evidence of problems with photos/videos',
      ],
    },
    {
      step: 4,
      title: 'Demand Accountability',
      description: 'Take action when things go wrong',
      actions: [
        'Report suspected misuse to relevant authorities',
        'Join or organize community pressure groups',
        'Use social media to highlight issues',
        'Support transparency initiatives and civil society groups',
      ],
    },
  ];

  return (
    <div className='bg-gradient-to-r from-green-50 to-blue-50 rounded-2xl p-6'>
      <h3 className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-6'>What You Can Do</h3>

      <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6'>
        {actionSteps.map((step, index) => (
          <motion.div
            key={step.step}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            className='bg-white dark:bg-surface-base rounded-xl p-4 border border-gray-200 dark:border-neutral-border'>
            {/* Step Header */}
            <div className='flex items-center gap-3 mb-3'>
              <div className='w-8 h-8 rounded-full bg-green-100 flex items-center justify-center text-green-800 font-bold text-sm'>
                {step.step}
              </div>
              <h4 className='font-bold text-gray-900 dark:text-neutral-text'>{step.title}</h4>
            </div>

            {/* Step Description */}
            <p className='text-sm text-gray-600 dark:text-neutral-muted mb-3'>{step.description}</p>

            {/* Action Items */}
            <ul className='space-y-1'>
              {step.actions.map((action, i) => (
                <li key={i} className='flex items-start gap-2 text-xs text-gray-700 dark:text-neutral-muted'>
                  <CheckCircle size={12} className='text-green-500 mt-0.5 flex-shrink-0' />
                  <span>{action}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        ))}
      </div>

      {/* Footer Message */}
      <div className='mt-6 text-center'>
        <p className='text-gray-700 dark:text-neutral-muted font-medium'>
          Remember: Government accountability starts with informed citizens. Every question you ask
          and every oversight you provide makes a difference.
        </p>
      </div>
    </div>
  );
}

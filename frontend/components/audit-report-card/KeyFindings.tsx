/**
 * Key findings section for audit reports
 */
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { getConcernLevelColor } from './auditUtils';

interface KeyFindingsProps {
  keyFindings: string[];
  concernLevel: string;
}

export default function KeyFindings({ keyFindings, concernLevel }: KeyFindingsProps) {
  const getDotColor = (level: string) => {
    switch (level) {
      case 'low':
        return 'bg-green-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'high':
        return 'bg-red-500';
      case 'critical':
        return 'bg-red-700';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <div>
      <h5 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center gap-2'>
        <AlertTriangle size={20} className={getConcernLevelColor(concernLevel)} />
        Key Findings
      </h5>
      <ul className='space-y-3'>
        {keyFindings.map((finding, index) => (
          <motion.li
            key={index}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1, duration: 0.4 }}
            className='flex items-start gap-3 p-3 bg-gray-50 dark:bg-surface-elevated rounded-lg'>
            <div
              className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${getDotColor(concernLevel)}`}
            />
            <span className='text-gray-700 dark:text-neutral-muted leading-relaxed'>{finding}</span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

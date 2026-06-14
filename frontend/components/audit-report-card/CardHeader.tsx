/**
 * Card header component for audit report cards
 */
import { County } from '@/types';
import { motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { getConcernLevelColor } from './auditUtils';
import QuickStats from './QuickStats';
import StatusBadge from './StatusBadge';

interface CardHeaderProps {
  county: County & {
    auditSummary: {
      headline: string;
      summary: string;
      keyFindings: string[];
      concern_level: string;
    };
  };
  statusIcon: React.ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
}

export default function CardHeader({ county, statusIcon, isExpanded, onToggle }: CardHeaderProps) {
  return (
    <motion.div
      className='p-6 cursor-pointer'
      onClick={onToggle}
      whileHover={{ backgroundColor: '#f8fafc' }}
      transition={{ duration: 0.2 }}>
      <div className='flex items-start justify-between'>
        <div className='flex items-start gap-4 flex-1'>
          {/* Status Icon */}
          <div className='flex-shrink-0 mt-1'>{statusIcon}</div>

          {/* County Info */}
          <div className='flex-1 min-w-0'>
            <div className='flex items-center gap-3 mb-2'>
              <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text'>{county.name} County</h3>
              <StatusBadge auditStatus={county.auditStatus} />
            </div>

            {/* Headline Summary */}
            <h4
              className={`text-lg font-semibold mb-3 ${getConcernLevelColor(
                county.auditSummary.concern_level
              )}`}>
              {county.auditSummary.headline}
            </h4>

            {/* Quick Stats */}
            <QuickStats county={county} />

            {/* Short Summary */}
            <p className='text-gray-700 dark:text-neutral-muted leading-relaxed'>{county.auditSummary.summary}</p>
          </div>
        </div>

        {/* Expand Button */}
        <motion.div
          className='flex-shrink-0 ml-4'
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.3 }}>
          <ChevronDown size={24} className='text-gray-400 dark:text-neutral-muted/80' />
        </motion.div>
      </div>
    </motion.div>
  );
}

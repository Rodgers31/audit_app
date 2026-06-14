/**
 * Expandable content section for audit report cards
 */
import { County } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import AuditIssues from './AuditIssues';
import CitizenImpact from './CitizenImpact';
import FinancialOverview from './FinancialOverview';
import KeyFindings from './KeyFindings';

interface ExpandableContentProps {
  county: County & {
    auditSummary: {
      headline: string;
      summary: string;
      keyFindings: string[];
      concern_level: string;
    };
  };
  isExpanded: boolean;
}

export default function ExpandableContent({ county, isExpanded }: ExpandableContentProps) {
  return (
    <AnimatePresence>
      {isExpanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className='overflow-hidden'>
          <div className='px-6 pb-6 border-t border-gray-100 dark:border-neutral-border'>
            <div className='pt-6 space-y-6'>
              <KeyFindings
                keyFindings={county.auditSummary.keyFindings}
                concernLevel={county.auditSummary.concern_level}
              />
              <FinancialOverview county={county} />
              <CitizenImpact auditStatus={county.auditStatus} />
              <AuditIssues auditIssues={county.auditIssues} />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

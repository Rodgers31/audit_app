/**
 * Refactored AuditReportCard - Main component for displaying county audit information
 * Broken down into focused sub-components for better maintainability
 */
'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import { useState } from 'react';
import CardHeader from './audit-report-card/CardHeader';
import ExpandableContent from './audit-report-card/ExpandableContent';

interface AuditReportCardProps {
  county: County & {
    auditSummary: {
      headline: string;
      summary: string;
      keyFindings: string[];
      concern_level: string;
    };
  };
  statusIcon: React.ReactNode;
  statusColor: string;
}

export default function AuditReportCard({ county, statusIcon, statusColor }: AuditReportCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <motion.div
      layout
      className='bg-white dark:bg-surface-base rounded-3xl shadow-xl border border-gray-200 dark:border-neutral-border overflow-hidden hover:shadow-2xl transition-shadow duration-300'>
      <CardHeader
        county={county}
        statusIcon={statusIcon}
        isExpanded={isExpanded}
        onToggle={() => setIsExpanded(!isExpanded)}
      />
      <ExpandableContent county={county} isExpanded={isExpanded} />
    </motion.div>
  );
}

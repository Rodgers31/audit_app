'use client';

import { AuditIssue } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, AlertTriangle, Info, Shield, X } from 'lucide-react';

interface AuditIssuesModalProps {
  isOpen: boolean;
  onClose: () => void;
  countyName: string;
  auditIssues: AuditIssue[];
}

const severityConfig = {
  low: {
    icon: Info,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  medium: {
    icon: AlertCircle,
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
  },
  high: {
    icon: AlertTriangle,
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
  },
  critical: {
    icon: Shield,
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
  },
};

const typeConfig = {
  financial: { label: 'Financial', color: 'bg-purple-100 text-purple-800' },
  compliance: { label: 'Compliance', color: 'bg-blue-100 text-blue-800' },
  performance: { label: 'Performance', color: 'bg-green-100 text-green-800' },
  governance: { label: 'Governance', color: 'bg-orange-100 text-orange-800' },
};

const statusConfig = {
  open: { label: 'Open', color: 'bg-red-100 text-red-800' },
  pending: { label: 'Pending', color: 'bg-yellow-100 text-yellow-800' },
  resolved: { label: 'Resolved', color: 'bg-green-100 text-green-800' },
};

export default function AuditIssuesModal({
  isOpen,
  onClose,
  countyName,
  auditIssues,
}: AuditIssuesModalProps) {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const groupedIssues = auditIssues.reduce((acc, issue) => {
    if (!acc[issue.severity]) {
      acc[issue.severity] = [];
    }
    acc[issue.severity].push(issue);
    return acc;
  }, {} as Record<string, AuditIssue[]>);

  const severityOrder: (keyof typeof severityConfig)[] = ['critical', 'high', 'medium', 'low'];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className='fixed inset-0 bg-black bg-opacity-50 z-50'
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className='fixed inset-x-4 top-4 bottom-4 md:inset-x-8 md:top-8 md:bottom-8 lg:inset-x-16 lg:top-16 lg:bottom-16 bg-white dark:bg-surface-base rounded-2xl shadow-2xl z-50 flex flex-col max-w-6xl mx-auto'>
            {/* Header */}
            <div className='flex items-center justify-between p-6 border-b border-gray-200 dark:border-neutral-border'>
              <div>
                <h2 className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>Audit Issues - {countyName}</h2>
                <p className='text-sm text-gray-600 dark:text-neutral-muted mt-1'>
                  {auditIssues.length} issues found in the latest audit report
                </p>
              </div>
              <button
                onClick={onClose}
                className='p-2 hover:bg-gray-100 dark:bg-surface-elevated rounded-full transition-colors'>
                <X size={24} className='text-gray-500 dark:text-neutral-muted/80' />
              </button>
            </div>

            {/* Content */}
            <div className='flex-1 overflow-y-auto p-6'>
              {auditIssues.length === 0 ? (
                <div className='text-center py-16'>
                  <Shield className='mx-auto h-16 w-16 text-green-500 mb-4' />
                  <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-2'>
                    No Audit Issues Found
                  </h3>
                  <p className='text-gray-600 dark:text-neutral-muted'>
                    This county has a clean audit report with no issues identified.
                  </p>
                </div>
              ) : (
                <div className='space-y-6'>
                  {severityOrder.map((severity) => {
                    const issues = groupedIssues[severity];
                    if (!issues || issues.length === 0) return null;

                    const config = severityConfig[severity];
                    const Icon = config.icon;

                    return (
                      <div key={severity} className='space-y-4'>
                        <div className='flex items-center gap-3'>
                          <Icon className={`${config.color} h-6 w-6`} />
                          <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text capitalize'>
                            {severity} Priority Issues ({issues.length})
                          </h3>
                        </div>

                        <div className='grid gap-4'>
                          {issues.map((issue) => (
                            <motion.div
                              key={issue.id}
                              initial={{ opacity: 0, y: 10 }}
                              animate={{ opacity: 1, y: 0 }}
                              className={`${config.bgColor} ${config.borderColor} border rounded-xl p-4`}>
                              <div className='flex items-start justify-between mb-3'>
                                <div className='flex items-center gap-2'>
                                  <span
                                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      typeConfig[issue.type].color
                                    }`}>
                                    {typeConfig[issue.type].label}
                                  </span>
                                  <span
                                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      statusConfig[issue.status].color
                                    }`}>
                                    {statusConfig[issue.status].label}
                                  </span>
                                </div>
                                {issue.amount && (
                                  <span className='text-sm font-semibold text-gray-900 dark:text-neutral-text'>
                                    {formatCurrency(issue.amount)}
                                  </span>
                                )}
                              </div>

                              <p className='text-gray-800 dark:text-neutral-text leading-relaxed'>{issue.description}</p>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className='border-t border-gray-200 dark:border-neutral-border p-6'>
              <div className='flex items-center justify-between'>
                <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>
                  Last updated from Auditor-General's office
                </div>
                <button
                  onClick={onClose}
                  className='px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors'>
                  Close
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

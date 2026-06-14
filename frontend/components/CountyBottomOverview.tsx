'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { County } from '@/types';
import { motion } from 'framer-motion';

interface CountyBottomOverviewProps {
  county: County | null;
  className?: string;
}

export default function CountyBottomOverview({
  county,
  className = '',
}: CountyBottomOverviewProps) {
  if (!county) {
    return (
      <Card
        className={`bg-gradient-to-br from-blue-50 to-blue-100 border-2 border-blue-200 shadow-lg max-w-sm mx-auto ${className}`}>
        <CardContent className='p-6'>
          <div className='text-center'>
            <h3 className='text-lg font-semibold text-gray-700 dark:text-neutral-muted mb-2'>Kenya Counties Overview</h3>
            <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Select a county to view details</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const formatKES = (amount: number | undefined) => {
    if (!amount || amount === 0) return 'KES 0';
    if (amount >= 1e9) return `KES ${(amount / 1e9).toFixed(1)}B`;
    if (amount >= 1e6) return `KES ${(amount / 1e6).toFixed(1)}M`;
    return `KES ${amount.toLocaleString()}`;
  };

  const formatPopulation = (pop: number | undefined) => {
    if (!pop || pop === 0) return 'N/A';
    if (pop >= 1e6) return `${(pop / 1e6).toFixed(1)}M`;
    if (pop >= 1e3) return `${(pop / 1e3).toFixed(0)}K`;
    return pop.toString();
  };

  const getAuditStatusConfig = (status: string) => {
    switch (status) {
      case 'clean':
        return {
          label: 'CLEAN',
          color: 'bg-green-100 text-green-700 border-green-300',
        };
      case 'qualified':
        return {
          label: 'QUALIFIED',
          color: 'bg-yellow-100 text-yellow-700 border-yellow-300',
        };
      case 'adverse':
        return {
          label: 'ADVERSE',
          color: 'bg-red-100 text-red-700 border-red-300',
        };
      case 'disclaimer':
        return {
          label: 'DISCLAIMER',
          color: 'bg-orange-100 text-orange-700 border-orange-300',
        };
      default:
        return {
          label: 'PENDING',
          color: 'bg-gray-100 dark:bg-surface-elevated text-gray-700 dark:text-neutral-muted border-gray-300 dark:border-neutral-border',
        };
    }
  };

  const auditConfig = getAuditStatusConfig(county.auditStatus || 'pending');
  const issuesCount = Array.isArray(county.auditIssues)
    ? county.auditIssues.length
    : county.auditStatus === 'clean'
    ? 0
    : 1;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`max-w-sm mx-auto ${className}`}>
      <Card className='bg-gradient-to-br from-blue-50 to-blue-100 border-2 border-blue-200 shadow-lg'>
        <CardContent className='p-6'>
          {/* Header */}
          <div className='text-center mb-4'>
            <h3 className='text-xl font-bold text-slate-800 dark:text-neutral-text mb-1'>{county.name} County</h3>
            <p className='text-sm text-slate-600 dark:text-neutral-muted'>
              Population: {formatPopulation(county.population)}
            </p>
          </div>

          {/* 2x2 Metrics Grid */}
          <div className='grid grid-cols-2 gap-3 mb-4'>
            {/* Budget */}
            <div className='bg-white/80 dark:bg-surface-elevated rounded-lg p-3 text-center'>
              <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1'>Budget</div>
              <div className='text-sm font-bold text-green-600'>
                {formatKES(county.budget || county.budget_2025 || 0)}
              </div>
            </div>

            {/* Debt */}
            <div className='bg-white/80 dark:bg-surface-elevated rounded-lg p-3 text-center'>
              <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1'>Debt</div>
              <div className='text-sm font-bold text-orange-600'>{formatKES(county.debt || 0)}</div>
            </div>

            {/* Received */}
            <div className='bg-white/80 dark:bg-surface-elevated rounded-lg p-3 text-center'>
              <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1'>Received</div>
              <div className='text-sm font-bold text-blue-600'>
                {formatKES(
                  county.moneyReceived || (county.budget || county.budget_2025 || 0) * 0.94
                )}
              </div>
            </div>

            {/* Issues */}
            <div className='bg-white/80 dark:bg-surface-elevated rounded-lg p-3 text-center'>
              <div className='text-xs text-gray-600 dark:text-neutral-muted mb-1'>Issues</div>
              <div className='text-lg font-bold text-red-600'>{issuesCount}</div>
            </div>
          </div>

          {/* Audit Status Badge */}
          <div className='text-center'>
            <Badge className={`px-4 py-1 text-xs font-semibold border ${auditConfig.color}`}>
              {auditConfig.label}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

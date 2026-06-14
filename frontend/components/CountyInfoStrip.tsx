'use client';

import { formatCurrency, formatNumber } from '@/lib/utils';
import { County } from '@/types';
import { motion } from 'framer-motion';
import { BarChart, DollarSign, FileText, TrendingUp, Users } from 'lucide-react';

interface CountyInfoStripProps {
  county: County | null;
  className?: string;
}

const getAuditConfig = (status: string) => {
  const configs = {
    clean: {
      label: 'Clean Opinion',
      color: 'text-green-700',
      bgColor: 'bg-green-50',
      borderColor: 'border-green-200',
      icon: '✅',
      description: 'No material issues found',
    },
    qualified: {
      label: 'Qualified Opinion',
      color: 'text-yellow-700',
      bgColor: 'bg-yellow-50',
      borderColor: 'border-yellow-200',
      icon: '⚠️',
      description: 'Minor issues identified',
    },
    adverse: {
      label: 'Adverse Opinion',
      color: 'text-red-700',
      bgColor: 'bg-red-50',
      borderColor: 'border-red-200',
      icon: '❌',
      description: 'Significant concerns found',
    },
    disclaimer: {
      label: 'Disclaimer',
      color: 'text-gray-700 dark:text-neutral-muted',
      bgColor: 'bg-gray-50 dark:bg-surface-elevated',
      borderColor: 'border-gray-200 dark:border-neutral-border',
      icon: '❓',
      description: 'Insufficient information',
    },
    pending: {
      label: 'Audit Pending',
      color: 'text-blue-700',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      icon: '⏳',
      description: 'Audit in progress',
    },
  };
  return configs[status as keyof typeof configs] || configs.pending;
};

export default function CountyInfoStrip({ county, className = '' }: CountyInfoStripProps) {
  if (!county) {
    return (
      <div className={`bg-white dark:bg-surface-base rounded-2xl border border-gray-200 dark:border-neutral-border p-8 ${className}`}>
        <div className='text-center text-gray-500 dark:text-neutral-muted/80 py-8'>
          <div className='text-4xl mb-4'>🏛️</div>
          <div className='text-lg font-medium text-gray-700 dark:text-neutral-muted mb-2'>No County Selected</div>
          <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>
            Click on a county or use the slider to view details
          </div>
        </div>
      </div>
    );
  }

  const auditConfig = getAuditConfig(county.auditStatus || 'pending');
  const debtRatio =
    county.budget && county.budget > 0 ? ((county.debt || 0) / county.budget) * 100 : 0;
  const budgetUtilization = county.budgetUtilization || 97;
  const perCapitaDebt =
    county.population && county.population > 0 ? (county.debt || 0) / county.population : 0;
  const revenue = county.moneyReceived || (county.budget || 0) * 1.06; // Assuming revenue is slightly higher than budget
  const expenditure = (county.budget || 0) * (budgetUtilization / 100);
  const balance = revenue - expenditure;

  return (
    <motion.div
      key={county.id}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={`bg-white dark:bg-surface-base rounded-2xl border border-gray-200 dark:border-neutral-border p-8 ${className}`}>
      {/* Header Section */}
      <div className='flex items-start justify-between mb-8'>
        <div>
          <h2 className='text-3xl font-bold text-gray-900 dark:text-neutral-text mb-2'>{county.name} County</h2>
          <div className='flex items-center text-gray-600 dark:text-neutral-muted'>
            <Users className='w-4 h-4 mr-2' />
            <span>Population: {formatNumber(county.population)}</span>
          </div>
        </div>

        <div
          className={`px-4 py-2 rounded-xl border-2 ${auditConfig.borderColor} ${auditConfig.bgColor}`}>
          <div className='flex items-center gap-2'>
            <FileText className={`w-4 h-4 ${auditConfig.color}`} />
            <span className={`text-sm font-semibold ${auditConfig.color}`}>clean Audit (2024)</span>
          </div>
        </div>
      </div>

      {/* Main Metrics Cards */}
      <div className='grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8'>
        {/* Budget Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1, duration: 0.3 }}
          className='bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-6 border border-green-200'>
          <div className='flex items-center justify-between mb-4'>
            <div className='flex items-center gap-2'>
              <div className='w-10 h-10 bg-green-600 rounded-lg flex items-center justify-center'>
                <DollarSign className='w-5 h-5 text-white' />
              </div>
              <div className='flex items-center gap-1 text-green-700 font-medium'>
                <TrendingUp className='w-4 h-4' />
                <span className='text-sm'>BUDGET</span>
              </div>
            </div>
          </div>

          <div className='text-3xl font-bold text-green-800 mb-2'>
            {formatCurrency(county.budget ?? county.totalBudget ?? 0).replace('KES ', 'KES ')}
          </div>
          <div className='text-sm text-green-700 mb-3'>Annual allocation</div>

          <div className='bg-green-200 rounded-full h-2 mb-2'>
            <div
              className='bg-green-600 h-2 rounded-full transition-all duration-1000'
              style={{ width: `${budgetUtilization}%` }}
            />
          </div>
          <div className='text-sm text-green-700 font-medium'>{budgetUtilization}% used</div>
        </motion.div>

        {/* Debt Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.3 }}
          className='bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-6 border border-orange-200'>
          <div className='flex items-center justify-between mb-4'>
            <div className='flex items-center gap-2'>
              <div className='w-10 h-10 bg-orange-600 rounded-lg flex items-center justify-center'>
                <BarChart className='w-5 h-5 text-white' />
              </div>
              <div className='flex items-center gap-1 text-orange-700 font-medium'>
                <TrendingUp className='w-4 h-4' />
                <span className='text-sm'>DEBT</span>
              </div>
            </div>
          </div>

          <div className='text-3xl font-bold text-orange-800 mb-2'>
            {formatCurrency(county.debt ?? county.totalDebt ?? 0).replace('KES ', 'KES ')}
          </div>
          <div className='text-sm text-orange-700 mb-1'>Outstanding obligations</div>
          <div className='text-sm text-orange-600'>{debtRatio.toFixed(0)}% of annual revenue</div>
        </motion.div>

        {/* Audit Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3, duration: 0.3 }}
          className={`bg-gradient-to-br ${auditConfig.bgColor} to-green-100 rounded-xl p-6 border ${auditConfig.borderColor}`}>
          <div className='flex items-center justify-between mb-4'>
            <div className='flex items-center gap-2'>
              <div className={`w-10 h-10 bg-green-600 rounded-lg flex items-center justify-center`}>
                <FileText className='w-5 h-5 text-white' />
              </div>
              <div className={`flex items-center gap-1 ${auditConfig.color} font-medium`}>
                <BarChart className='w-4 h-4' />
                <span className='text-sm'>AUDIT</span>
              </div>
            </div>
          </div>

          <div className={`text-2xl font-bold ${auditConfig.color} mb-2`}>{auditConfig.label}</div>
          <div className={`text-sm ${auditConfig.color} mb-1`}>{auditConfig.description}</div>
          <div className='text-sm text-gray-600 dark:text-neutral-muted'>Year: 2024</div>
        </motion.div>
      </div>

      {/* Financial Summary Section */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.3 }}
        className='bg-gray-50 dark:bg-surface-elevated rounded-xl p-6'>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4'>Financial Summary</h3>

        <div className='grid grid-cols-2 lg:grid-cols-4 gap-6'>
          <div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted mb-1'>Revenue</div>
            <div className='text-xl font-bold text-green-600'>
              {formatCurrency(revenue).replace('KES ', 'KES ')}
            </div>
          </div>

          <div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted mb-1'>Expenditure</div>
            <div className='text-xl font-bold text-blue-600'>
              {formatCurrency(expenditure).replace('KES ', 'KES ')}
            </div>
          </div>

          <div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted mb-1'>Balance</div>
            <div
              className={`text-xl font-bold ${balance >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatCurrency(Math.abs(balance)).replace('KES ', 'KES ')}
            </div>
          </div>

          <div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted mb-1'>Per Capita Debt</div>
            <div className='text-xl font-bold text-orange-600'>
              {formatCurrency(perCapitaDebt).replace('KES ', 'KES ')}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

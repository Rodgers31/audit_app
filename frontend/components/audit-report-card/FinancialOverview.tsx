/**
 * Financial overview section for audit reports
 */
import { County } from '@/types';
import { DollarSign } from 'lucide-react';
import { formatCurrency } from './auditUtils';

interface FinancialOverviewProps {
  county: County;
}

export default function FinancialOverview({ county }: FinancialOverviewProps) {
  return (
    <div>
      <h5 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center gap-2'>
        <DollarSign size={20} className='text-blue-600' />
        Financial Overview
      </h5>
      <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4'>
        <div className='p-4 bg-blue-50 rounded-xl border border-blue-200'>
          <div className='text-sm text-blue-600 font-medium mb-1'>Total Budget</div>
          <div className='text-xl font-bold text-blue-700'>
            {formatCurrency(county.budget ?? 0)}
          </div>
        </div>
        <div className='p-4 bg-green-50 rounded-xl border border-green-200'>
          <div className='text-sm text-green-600 font-medium mb-1'>Budget Used</div>
          <div className='text-xl font-bold text-green-700'>{county.budgetUtilization ?? 0}%</div>
        </div>
        <div className='p-4 bg-purple-50 rounded-xl border border-purple-200'>
          <div className='text-sm text-purple-600 font-medium mb-1'>Revenue Collected</div>
          <div className='text-xl font-bold text-purple-700'>
            {formatCurrency(county.revenueCollection ?? 0)}
          </div>
        </div>
        <div className='p-4 bg-red-50 rounded-xl border border-red-200'>
          <div className='text-sm text-red-600 font-medium mb-1'>Pending Bills</div>
          <div className='text-xl font-bold text-red-700'>
            {formatCurrency(county.pendingBills ?? 0)}
          </div>
        </div>
      </div>
    </div>
  );
}

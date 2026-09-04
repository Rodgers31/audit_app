/**
 * BudgetCard - Budget information card with utilization progress
 * Displays county budget allocation and usage percentage
 */
'use client';

import { DollarSign } from 'lucide-react';

interface BudgetCardProps {
  budget: number;
  budgetUtilization: number | null;
}

export default function BudgetCard({ budget, budgetUtilization }: BudgetCardProps) {
  return (
    <div className='bg-green-50 border border-green-200 rounded-2xl p-5'>
      {/* Header */}
      <div className='flex items-start gap-3 mb-3'>
        <div className='w-14 h-14 bg-green-500 rounded-2xl flex items-center justify-center'>
          <DollarSign className='text-white' size={24} />
        </div>
        <div className='flex-1'>
          <div className='flex items-center gap-2 mb-1'>
            <span className='text-orange-600 text-base'>💰</span>
            <span className='text-green-700 font-semibold text-xs tracking-wide'>BUDGET</span>
          </div>
        </div>
      </div>

      {/* Budget Amount */}
      <div className='text-2xl font-bold text-green-800 mb-1'>KES {(budget / 1e9).toFixed(2)}B</div>
      <div className='text-green-600 mb-3 font-medium text-sm'>Annual allocation</div>

      {/* Utilization Progress Bar */}
      <div className='w-full bg-green-200 rounded-full h-2'>
        <div
          className='bg-green-500 h-2 rounded-full transition-all duration-500'
          style={{ width: budgetUtilization != null ? `${budgetUtilization}%` : '0%' }}
        />
      </div>
      <div className='text-xs text-green-700 mt-1 font-medium'>
        {budgetUtilization != null ? `${budgetUtilization}% used` : 'Not reported'}
      </div>
    </div>
  );
}

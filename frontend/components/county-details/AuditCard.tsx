/**
 * AuditCard - Audit status card with detailed audit opinion information
 * Displays audit status with appropriate colors and descriptions
 */
'use client';

import { County } from '@/types';
import { AlertTriangle } from 'lucide-react';
import {
  getAuditDescription,
  getAuditStatusBackground,
  getAuditStatusIconColor,
  getAuditStatusText,
} from './countyUtils';

interface AuditCardProps {
  county: County;
}

export default function AuditCard({ county }: AuditCardProps) {
  const status = county.auditStatus || 'pending';
  const statusText = getAuditStatusText(status);
  const statusDescription = getAuditDescription(status);
  const backgroundClass = getAuditStatusBackground(status);
  const iconColorClass = getAuditStatusIconColor(status);

  const getTextColorClass = (status: string) => {
    switch (status) {
      case 'clean':
        return 'text-green-700';
      case 'qualified':
        return 'text-yellow-700';
      case 'adverse':
        return 'text-red-700';
      case 'disclaimer':
        return 'text-orange-700';
      default:
        return 'text-gray-700 dark:text-neutral-muted';
    }
  };

  const getTitleColorClass = (status: string) => {
    switch (status) {
      case 'clean':
        return 'text-green-800';
      case 'qualified':
        return 'text-yellow-800';
      case 'adverse':
        return 'text-red-800';
      case 'disclaimer':
        return 'text-orange-800';
      default:
        return 'text-gray-800 dark:text-neutral-text';
    }
  };

  const getDescriptionColorClass = (status: string) => {
    switch (status) {
      case 'clean':
        return 'text-green-600';
      case 'qualified':
        return 'text-yellow-600';
      case 'adverse':
        return 'text-red-600';
      case 'disclaimer':
        return 'text-orange-600';
      default:
        return 'text-gray-600 dark:text-neutral-muted';
    }
  };

  return (
    <div className={`border rounded-2xl p-5 ${backgroundClass}`}>
      {/* Header */}
      <div className='flex items-start gap-3 mb-3'>
        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${iconColorClass}`}>
          <AlertTriangle className='text-white' size={24} />
        </div>
        <div className='flex-1'>
          <div className='flex items-center gap-2 mb-1'>
            <span className='text-base'>📋</span>
            <span className={`font-semibold text-xs tracking-wide ${getTextColorClass(status)}`}>
              AUDIT
            </span>
          </div>
        </div>
      </div>

      {/* Audit Status */}
      <div className={`text-2xl font-bold mb-1 ${getTitleColorClass(status)}`}>{statusText}</div>

      {/* Description */}
      <div className={`font-medium mb-1 ${getDescriptionColorClass(status)}`}>
        {statusDescription}
      </div>

      {/* Year */}
      {county.lastAuditDate && (
        <div className={`text-sm font-medium ${getTextColorClass(status)}`}>
          Year: {new Date(county.lastAuditDate).getFullYear()}
        </div>
      )}
    </div>
  );
}

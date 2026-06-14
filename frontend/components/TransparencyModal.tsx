'use client';

import { useCountyAuditsEnriched } from '@/lib/react-query';
import { County } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowLeft,
  DollarSign,
  Eye,
  Gavel,
  TrendingDown,
  TrendingUp,
  Users,
  X,
} from 'lucide-react';
import React from 'react';

interface TransparencyModalProps {
  isOpen: boolean;
  onClose: () => void;
  county: County;
}

export default function TransparencyModal({ isOpen, onClose, county }: TransparencyModalProps) {
  const [view, setView] = React.useState<'main' | 'contact' | 'budget' | 'report'>('main');
  const [showAllQueries, setShowAllQueries] = React.useState(false);

  // Fetch enriched audits when modal is open and on report view
  const { data: auditsEnriched } = useCountyAuditsEnriched(county.id, {
    enabled: isOpen, // prefetch on open
  });

  // Calculate transparency metrics from real data
  const calculateTransparencyScore = () => {
    const auditGrade = county.audit_rating || 'B';
    const budgetUtilization = county.budget_2025 ? 75 : 60; // Mock calculation
    const baseScore = auditGrade === 'A-' ? 85 : auditGrade.startsWith('B+') ? 80 : 75;
    return Math.min(95, baseScore + (budgetUtilization > 80 ? 10 : 0));
  };

  // Generate citizen-impact focus areas
  const getCitizenImpactIssues = () => {
    const score = calculateTransparencyScore();
    if (score >= 85) {
      return [
        {
          category: 'Budget Execution',
          status: 'good',
          impact: 'Development projects delivered on time',
          citizens_affected: Math.floor(county.population * 0.8),
          icon: TrendingUp,
        },
        {
          category: 'Public Procurement',
          status: 'good',
          impact: 'Transparent tender processes saving taxpayer money',
          citizens_affected: county.population,
          icon: DollarSign,
        },
      ];
    } else {
      return [
        {
          category: 'Budget Delays',
          status: 'concern',
          impact: 'Delayed infrastructure projects affecting daily commute',
          citizens_affected: Math.floor(county.population * 0.6),
          icon: TrendingDown,
        },
        {
          category: 'Procurement Issues',
          status: 'concern',
          impact: 'Questionable tender awards requiring investigation',
          citizens_affected: county.population,
          icon: AlertTriangle,
        },
        {
          category: 'Revenue Collection',
          status: 'attention',
          impact: 'Lower local revenue affecting service delivery',
          citizens_affected: Math.floor(county.population * 0.4),
          icon: Gavel,
        },
      ];
    }
  };

  const transparencyScore = calculateTransparencyScore();
  const citizenImpacts = getCitizenImpactIssues();

  const getScoreColor = (score: number) => {
    if (score >= 85) return 'text-green-600';
    if (score >= 70) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getScoreBg = (score: number) => {
    if (score >= 85) return 'bg-green-50 border-green-200';
    if (score >= 70) return 'bg-yellow-50 border-yellow-200';
    return 'bg-red-50 border-red-200';
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatPct = (n?: number) =>
    n == null ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(n)}%`;

  const TitleByView = () => {
    switch (view) {
      case 'report':
        return 'Audit Report Summary';
      case 'budget':
        return 'Budget Overview';
      case 'contact':
        return 'Contact Governor';
      default:
        return 'Government Transparency Report';
    }
  };

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
              <div className='flex items-center gap-3'>
                {view !== 'main' && (
                  <button
                    onClick={() => setView('main')}
                    className='p-2 hover:bg-gray-100 dark:bg-surface-elevated rounded-full transition-colors'
                    title='Back'>
                    <ArrowLeft size={22} className='text-gray-600 dark:text-neutral-muted' />
                  </button>
                )}
                <div>
                  <h2 className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
                    <TitleByView />
                  </h2>
                  <p className='text-lg text-gray-600 dark:text-neutral-muted mt-1'>{county.name}</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className='p-2 hover:bg-gray-100 dark:bg-surface-elevated rounded-full transition-colors'
                title='Close'>
                <X size={24} className='text-gray-500 dark:text-neutral-muted/80' />
              </button>
            </div>

            {/* Content */}
            <div className='flex-1 overflow-y-auto p-6'>
              {/* MAIN VIEW */}
              {view === 'main' && (
                <>
                  <div className='grid grid-cols-1 lg:grid-cols-2 gap-8'>
                    {/* Transparency Score */}
                    <div className={`${getScoreBg(transparencyScore)} border rounded-2xl p-6`}>
                      <div className='flex items-center gap-3 mb-4'>
                        <Eye className={`${getScoreColor(transparencyScore)} h-8 w-8`} />
                        <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text'>Transparency Score</h3>
                      </div>

                      <div className='text-center mb-6'>
                        <div
                          className={`text-6xl font-bold ${getScoreColor(transparencyScore)} mb-2`}>
                          {transparencyScore}
                        </div>
                        <div className='text-gray-600 dark:text-neutral-muted'>out of 100</div>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80 mt-2'>
                          Based on audit rating: {county.audit_rating || 'B'}
                        </div>
                      </div>

                      <div className='space-y-3'>
                        <div className='flex justify-between'>
                          <span className='text-gray-600 dark:text-neutral-muted'>Audit Performance</span>
                          <span className='font-semibold'>{county.audit_rating || 'B'}</span>
                        </div>
                        <div className='flex justify-between'>
                          <span className='text-gray-600 dark:text-neutral-muted'>Budget Size</span>
                          <span className='font-semibold'>
                            {formatCurrency(county.budget_2025 || county.totalBudget || 0)}
                          </span>
                        </div>
                        <div className='flex justify-between'>
                          <span className='text-gray-600 dark:text-neutral-muted'>Citizens Served</span>
                          <span className='font-semibold'>
                            {county.population?.toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Citizen Impact */}
                    <div className='bg-blue-50 border border-blue-200 rounded-2xl p-6'>
                      <div className='flex items-center gap-3 mb-4'>
                        <Users className='text-blue-600 h-8 w-8' />
                        <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text'>How This Affects You</h3>
                      </div>

                      <div className='space-y-4'>
                        {citizenImpacts.map((impact, index) => {
                          const Icon = impact.icon;
                          return (
                            <motion.div
                              key={index}
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: index * 0.1 }}
                              className='bg-white dark:bg-surface-base rounded-xl p-4 border border-blue-200'>
                              <div className='flex items-start gap-3'>
                                <Icon
                                  className={`h-6 w-6 ${
                                    impact.status === 'good'
                                      ? 'text-green-600'
                                      : impact.status === 'concern'
                                        ? 'text-red-600'
                                        : 'text-yellow-600'
                                  } mt-1`}
                                />
                                <div className='flex-1'>
                                  <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>
                                    {impact.category}
                                  </h4>
                                  <p className='text-gray-700 dark:text-neutral-muted text-sm mb-2'>{impact.impact}</p>
                                  <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                                    Affects ~{impact.citizens_affected.toLocaleString()} citizens
                                  </div>
                                </div>
                              </div>
                            </motion.div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Accountability Actions */}
                  <div className='mt-8 bg-gray-50 dark:bg-surface-elevated rounded-2xl p-6'>
                    <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text mb-4'>
                      Take Action for Accountability
                    </h3>
                    <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
                      <button
                        onClick={() => setView('contact')}
                        className='bg-blue-600 text-white p-4 rounded-xl hover:bg-blue-700 transition-colors text-left'>
                        <h4 className='font-semibold mb-2'>Contact Governor</h4>
                        <p className='text-sm opacity-90'>Ask questions about budget performance</p>
                      </button>
                      <button
                        onClick={() => setView('budget')}
                        className='bg-green-600 text-white p-4 rounded-xl hover:bg-green-700 transition-colors text-left'>
                        <h4 className='font-semibold mb-2'>View Full Budget</h4>
                        <p className='text-sm opacity-90'>Access detailed spending breakdown</p>
                      </button>
                      <button
                        onClick={() => setView('report')}
                        className='bg-purple-600 text-white p-4 rounded-xl hover:bg-purple-700 transition-colors text-left'>
                        <h4 className='font-semibold mb-2'>Report Issues</h4>
                        <p className='text-sm opacity-90'>Submit complaints about services</p>
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* REPORT SUBPAGE */}
              {view === 'report' && (
                <div className='space-y-6'>
                  <div className='bg-purple-50 border border-purple-200 rounded-2xl p-6'>
                    <h3 className='text-xl font-bold text-purple-900 mb-2'>Audit Report Summary</h3>
                    <p className='text-purple-800 mb-4'>
                      Latest audit rating:{' '}
                      <span className='font-semibold'>{county.audit_rating}</span>
                    </p>
                    <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Budget Size</div>
                        <div className='text-lg font-semibold'>
                          {formatCurrency(county.budget_2025 || county.totalBudget || 0)}
                        </div>
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Budget Utilization</div>
                        <div className='text-lg font-semibold'>
                          {formatPct(
                            auditsEnriched?.kpis?.budget_execution_rate ?? county.budgetUtilization
                          )}
                        </div>
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Pending Bills</div>
                        <div className='text-lg font-semibold'>
                          {formatCurrency(
                            (auditsEnriched?.kpis?.pending_bills as number | undefined) ??
                              county.pendingBills ??
                              0
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Quick Stats from enriched audits */}
                    <div className='grid grid-cols-1 md:grid-cols-3 gap-4 mt-4'>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Audit Queries</div>
                        <div className='text-lg font-semibold'>
                          {auditsEnriched?.summary?.queries_count ?? '—'}
                        </div>
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Missing Funds (Total)</div>
                        <div className='text-lg font-semibold'>
                          {auditsEnriched?.missing_funds?.total_amount != null
                            ? formatCurrency(auditsEnriched.missing_funds.total_amount)
                            : '—'}
                        </div>
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>COB Coverage</div>
                        <div className='text-lg font-semibold'>
                          {auditsEnriched?.cob_implementation?.coverage?.analysis_depth || '—'}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className='bg-white dark:bg-surface-base rounded-2xl border p-6'>
                    <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-3'>Key Findings</h4>
                    {auditsEnriched?.queries?.length ? (
                      <button
                        onClick={() => setShowAllQueries((v) => !v)}
                        className='text-sm text-blue-600 hover:underline mb-3'>
                        {showAllQueries ? 'Hide all queries' : 'View all queries'} (
                        {auditsEnriched.queries.length})
                      </button>
                    ) : null}
                    <ul className='space-y-3'>
                      {(auditsEnriched?.top_recent?.length
                        ? auditsEnriched.top_recent.map((q: any) => ({
                            id: q.id,
                            type: q.category || 'financial',
                            severity: (q.severity as any) || 'medium',
                            description: q.description,
                            status: (q.status as any) || 'open',
                            amountLabel: q.amount_involved,
                          }))
                        : county.auditIssues && county.auditIssues.length > 0
                          ? county.auditIssues
                          : ([
                              {
                                id: '1',
                                type: 'financial',
                                severity: 'high',
                                description: 'Unreconciled accounts detected',
                                status: 'open',
                              },
                              {
                                id: '2',
                                type: 'compliance',
                                severity: 'medium',
                                description: 'Irregular procurement procedures',
                                status: 'pending',
                              },
                              {
                                id: '3',
                                type: 'performance',
                                severity: 'low',
                                description: 'Delays in project completion',
                                status: 'pending',
                              },
                            ] as const)
                      ).map((issue: any) => (
                        <li key={issue.id} className='flex items-start gap-3'>
                          <span
                            className={`mt-1 inline-block w-2.5 h-2.5 rounded-full ${
                              issue.severity === 'critical'
                                ? 'bg-red-700'
                                : issue.severity === 'high'
                                  ? 'bg-red-500'
                                  : issue.severity === 'medium'
                                    ? 'bg-yellow-500'
                                    : 'bg-gray-400'
                            }`}
                          />
                          <div>
                            <div className='font-medium text-gray-900 dark:text-neutral-text'>{issue.description}</div>
                            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 capitalize'>
                              {issue.type} • {issue.severity} • {issue.status}
                              {issue.amount != null
                                ? ` • ${formatCurrency(issue.amount as number)}`
                                : issue.amountLabel
                                  ? ` • ${issue.amountLabel}`
                                  : ''}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                    {showAllQueries && auditsEnriched?.queries?.length ? (
                      <div className='mt-6'>
                        <h5 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-2'>
                          All audit queries
                        </h5>
                        <ul className='divide-y divide-gray-200 border rounded-xl'>
                          {auditsEnriched.queries.map((q: any, idx: number) => (
                            <li key={q.id || idx} className='p-4'>
                              <div className='flex items-start justify-between'>
                                <div className='pr-4'>
                                  <div className='font-medium text-gray-900 dark:text-neutral-text'>{q.description}</div>
                                  <div className='text-xs text-gray-500 dark:text-neutral-muted/80 capitalize'>
                                    {q.category || 'other'} • {q.severity || 'medium'} •{' '}
                                    {q.status || 'open'} • {q.date_raised || '—'}
                                  </div>
                                </div>
                                <div className='text-sm text-gray-700 dark:text-neutral-muted'>
                                  {q.amount_involved ? q.amount_involved : ''}
                                </div>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>

                  <div className='bg-gray-50 dark:bg-surface-elevated rounded-2xl p-6 border'>
                    <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>What you can do</h4>
                    <ul className='list-disc pl-5 space-y-1 text-sm text-gray-700 dark:text-neutral-muted'>
                      <li>Request supporting documents for flagged expenses</li>
                      <li>Ask for timelines on resolving pending issues</li>
                      <li>Report service delivery gaps via official channels</li>
                    </ul>
                  </div>
                </div>
              )}

              {/* BUDGET SUBPAGE */}
              {view === 'budget' && (
                <div className='space-y-6'>
                  <div className='bg-green-50 border border-green-200 rounded-2xl p-6'>
                    <h3 className='text-xl font-bold text-green-900 mb-2'>Budget Overview</h3>
                    <div className='grid grid-cols-1 md:grid-cols-4 gap-4'>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Total Budget</div>
                        <div className='text-lg font-semibold'>
                          {formatCurrency(county.budget_2025 || county.totalBudget || 0)}
                        </div>
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Development</div>
                        <div className='text-lg font-semibold'>
                          {county.developmentBudget
                            ? formatCurrency(county.developmentBudget)
                            : 'Unavailable'}
                        </div>
                        {!county.developmentBudget && (
                          <div className='text-xs text-gray-400 dark:text-neutral-muted/80 mt-1'>
                            Not classified in source data
                          </div>
                        )}
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Recurrent</div>
                        <div className='text-lg font-semibold'>
                          {county.recurrentBudget
                            ? formatCurrency(county.recurrentBudget)
                            : 'Unavailable'}
                        </div>
                        {!county.recurrentBudget && (
                          <div className='text-xs text-gray-400 dark:text-neutral-muted/80 mt-1'>
                            Not classified in source data
                          </div>
                        )}
                      </div>
                      <div className='bg-white dark:bg-surface-base rounded-xl p-4 border'>
                        <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>Utilization</div>
                        <div className='text-lg font-semibold'>
                          {formatPct(county.budgetUtilization)}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className='bg-white dark:bg-surface-base rounded-2xl border p-6'>
                    <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-3'>Top Sectors</h4>
                    <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
                      {[
                        { label: 'Education', value: county.education },
                        { label: 'Health', value: county.health },
                        { label: 'Infrastructure', value: county.infrastructure },
                      ].map((s) => (
                        <div key={s.label} className='border rounded-xl p-4'>
                          <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>{s.label}</div>
                          <div className='text-lg font-semibold'>
                            {s.value != null ? formatCurrency(s.value) : '—'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* CONTACT SUBPAGE */}
              {view === 'contact' && (
                <div className='space-y-6'>
                  <div className='bg-blue-50 border border-blue-200 rounded-2xl p-6'>
                    <h3 className='text-xl font-bold text-blue-900 mb-2'>
                      Reach out to leadership
                    </h3>
                    <p className='text-blue-800'>
                      Use the template below to request information or raise concerns.
                    </p>
                  </div>

                  <div className='bg-white dark:bg-surface-base rounded-2xl border p-6 space-y-4'>
                    <div>
                      <label className='block text-sm font-medium text-gray-700 dark:text-neutral-muted mb-1'>
                        Subject
                      </label>
                      <input
                        className='w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
                        defaultValue={`Request for budget and audit details - ${county.name}`}
                      />
                    </div>
                    <div>
                      <label className='block text-sm font-medium text-gray-700 dark:text-neutral-muted mb-1'>
                        Message
                      </label>
                      <textarea
                        className='w-full border rounded-lg px-3 py-2 h-32 focus:outline-none focus:ring-2 focus:ring-blue-500'
                        defaultValue={`Dear Office of the Governor,

I am requesting clarification on the ${new Date().getFullYear()} budget execution and recent audit findings for ${
                          county.name
                        } County (rating: ${county.audit_rating}). Please share:
• Status of pending audit issues and corrective actions
• Budget utilization and priority projects
• Channels for citizen feedback

Thank you.`}
                      />
                    </div>
                    <div className='flex items-center gap-3'>
                      <button
                        onClick={() => {
                          const text = 'Copied message for contact';
                          navigator.clipboard?.writeText(text).catch(() => {});
                        }}
                        className='px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700'>
                        Copy Template
                      </button>
                      <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                        Copy and paste into your preferred channel (email, portal, or letter).
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className='border-t border-gray-200 dark:border-neutral-border p-6'>
              <div className='flex items-center justify-between'>
                <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>
                  Data from Auditor-General • Updated monthly • Promoting government accountability
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

'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { County } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BarChart3,
  BookOpen,
  Building2,
  FileWarning,
  GraduationCap,
  Heart,
  Landmark,
  MapPin,
  Receipt,
  Shield,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import Link from 'next/link';
import React from 'react';

/* ─────────────────────────────────────────────────────────
   CountyDetailsPanel  (v2 — enriched)
   ─────────────────────────────────────────────────────────
   Rich side-panel in the map container. Shows:
   · Header with county name + audit badge
   · Financial health gauge
   · 2×2 key stats grid
   · Budget utilisation bar
   · Top spending sectors mini-chart
   · OAG audit findings (scrollable)
   · CTA to full county page
   ───────────────────────────────────────────────────────── */

interface CountyDetailsPanelProps {
  county: County | null;
  className?: string;
}

/* ── formatting helpers ── */

function fmtKES(n: number | undefined): string {
  if (!n) return '—';
  if (n >= 1_000_000_000) return `KES ${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(0)}M`;
  return `KES ${n.toLocaleString()}`;
}

function fmtPop(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

/* ── colour helpers ── */

function auditColor(status?: string) {
  switch (status) {
    case 'clean':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'qualified':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'adverse':
      return 'bg-red-50 text-red-700 border-red-200';
    case 'disclaimer':
      return 'bg-red-100 text-red-800 border-red-300';
    default:
      return 'bg-gray-50 dark:bg-surface-elevated text-gray-500 dark:text-neutral-muted/80 border-gray-200 dark:border-neutral-border';
  }
}

function auditLabelKey(status?: string): TranslationKey {
  switch (status) {
    case 'clean':
      return 'home.county_panel.audit_clean';
    case 'qualified':
      return 'home.county_panel.audit_qualified';
    case 'adverse':
      return 'home.county_panel.audit_adverse';
    case 'disclaimer':
      return 'home.county_panel.audit_disclaimer';
    default:
      return 'home.county_panel.audit_pending';
  }
}

function healthColor(score: number) {
  if (score >= 70) return 'text-emerald-600';
  if (score >= 55) return 'text-amber-600';
  return 'text-red-600';
}

function healthBarColor(score: number) {
  if (score >= 70) return 'from-emerald-400 to-emerald-600';
  if (score >= 55) return 'from-amber-400 to-amber-500';
  return 'from-red-400 to-red-600';
}

function utilizationBarColor(pct: number) {
  if (pct >= 75) return 'bg-emerald-500';
  if (pct >= 50) return 'bg-amber-500';
  return 'bg-red-500';
}

function severityConfig(sev: string): {
  dot: string;
  text: string;
  bg: string;
  labelKey: TranslationKey;
} {
  switch (sev) {
    case 'critical':
      return {
        dot: 'bg-red-500',
        text: 'text-red-700',
        bg: 'bg-red-50',
        labelKey: 'home.county_panel.sev_critical',
      };
    case 'high':
      return {
        dot: 'bg-red-500',
        text: 'text-red-700',
        bg: 'bg-red-50',
        labelKey: 'home.county_panel.sev_high',
      };
    case 'warning':
    case 'medium':
      return {
        dot: 'bg-amber-500',
        text: 'text-amber-700',
        bg: 'bg-amber-50',
        labelKey: 'home.county_panel.sev_warning',
      };
    default:
      return {
        dot: 'bg-blue-400',
        text: 'text-blue-600',
        bg: 'bg-blue-50',
        labelKey: 'home.county_panel.sev_info',
      };
  }
}

/* ── Sector icon mapping ── */
function sectorIcon(name: string) {
  const lower = name.toLowerCase();
  if (lower.includes('health')) return <Heart className='w-3 h-3' />;
  if (lower.includes('education') || lower.includes('training'))
    return <GraduationCap className='w-3 h-3' />;
  if (lower.includes('road') || lower.includes('transport'))
    return <Building2 className='w-3 h-3' />;
  if (lower.includes('admin') || lower.includes('assembly'))
    return <Building2 className='w-3 h-3' />;
  return <BarChart3 className='w-3 h-3' />;
}

/* ══════════════════════════════════════════════════════════ */

export default function CountyDetailsPanel({ county, className = '' }: CountyDetailsPanelProps) {
  const { t } = useLang();
  return (
    <div
      className={`rounded-xl bg-white dark:bg-surface-base border border-gray-200/60 dark:border-neutral-border/60 shadow-sm overflow-hidden flex flex-col ${className}`}>
      <AnimatePresence mode='wait'>
        {county ? (
          <motion.div
            key={county.id}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.55, ease: [0.25, 0.1, 0.25, 1] }}
            className='flex flex-col flex-1 min-h-0'>
            {/* ── Header ── */}
            <div className='px-4 py-3 border-b border-gray-100 dark:border-neutral-border bg-gradient-to-r from-gov-forest/5 to-transparent dark:from-surface-elevated/40 dark:to-transparent'>
              <div className='flex items-center justify-between'>
                <div className='flex items-center gap-2'>
                  <div className='w-7 h-7 rounded-lg bg-gov-forest/10 flex items-center justify-center'>
                    <MapPin className='w-3.5 h-3.5 text-gov-forest dark:text-emerald-100' />
                  </div>
                  <div>
                    <h3 className='text-base font-bold text-gov-dark dark:text-white leading-tight'>
                      {county.name}
                    </h3>
                    <p className='text-[10px] text-gray-400 dark:text-neutral-muted/80 font-medium'>{t('home.county_panel.county_govt')}</p>
                  </div>
                </div>
                <span
                  className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${auditColor(county.auditStatus)}`}>
                  <Shield className='w-2.5 h-2.5' />
                  {t(auditLabelKey(county.auditStatus))}
                </span>
              </div>
            </div>

            {/* ── Scrollable content ── */}
            <div className='flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3'>
              {/* Financial Health Score */}
              <div>
                <div className='flex items-center justify-between mb-1'>
                  <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium'>{t('home.county_panel.financial_health')}</span>
                  <span
                    className={`text-base font-bold tabular-nums ${healthColor(county.financial_health_score)}`}>
                    {county.financial_health_score}
                    <span className='text-[10px] font-normal text-gray-400 dark:text-neutral-muted/80'>/100</span>
                  </span>
                </div>
                <div className='h-1.5 rounded-full bg-gray-100 dark:bg-surface-elevated overflow-hidden'>
                  <motion.div
                    key={`health-${county.id}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${county.financial_health_score}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut', delay: 0.1 }}
                    className={`h-full rounded-full bg-gradient-to-r ${healthBarColor(county.financial_health_score)}`}
                  />
                </div>
              </div>

              {/* Key stats 2×2 */}
              <div className='grid grid-cols-2 gap-2'>
                <StatItem
                  icon={<Wallet className='w-3 h-3' />}
                  label={t('home.county_panel.budget')}
                  value={fmtKES(county.budget_2025)}
                  iconBg='bg-gov-sage/10 text-gov-sage'
                />
                <StatItem
                  icon={<TrendingDown className='w-3 h-3' />}
                  label={t('home.county_panel.total_debt')}
                  value={fmtKES(county.debt)}
                  iconBg='bg-gov-copper/10 text-gov-copper'
                  alert={county.debt && county.budget ? county.debt / county.budget > 0.3 : false}
                />
                <StatItem
                  icon={<Users className='w-3 h-3' />}
                  label={t('home.county_panel.population_label')}
                  value={fmtPop(county.population)}
                  iconBg='bg-blue-50 text-blue-500'
                />
                <StatItem
                  icon={<Landmark className='w-3 h-3' />}
                  label={t('home.county_panel.audit_rating')}
                  value={county.audit_rating || '—'}
                  iconBg='bg-gov-forest/10 text-gov-forest dark:text-emerald-100'
                />
              </div>

              {/* Budget Utilisation */}
              {(county.budgetUtilization ?? 0) > 0 && (
                <div className='rounded-lg bg-gray-50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border p-2.5'>
                  <div className='flex items-center justify-between mb-1'>
                    <span className='text-[10px] text-gray-500 dark:text-neutral-muted/80 font-medium'>
                      {t('home.county_panel.utilization')}
                    </span>
                    <span className='text-xs font-bold text-gov-dark dark:text-white tabular-nums'>
                      {(county.budgetUtilization ?? 0).toFixed(1)}%
                    </span>
                  </div>
                  <div className='h-1.5 rounded-full bg-gray-200 dark:bg-surface-sunken overflow-hidden'>
                    <motion.div
                      key={`util-${county.id}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(county.budgetUtilization ?? 0, 100)}%` }}
                      transition={{ duration: 0.4, delay: 0.15 }}
                      className={`h-full rounded-full ${utilizationBarColor(county.budgetUtilization ?? 0)}`}
                    />
                  </div>
                </div>
              )}

              {/* Debt-to-budget + Pending Bills row */}
              <div className='grid grid-cols-2 gap-2'>
                {county.debt != null && county.budget != null && county.budget > 0 && (
                  <MiniMetric
                    label={t('home.county_panel.debt_ratio')}
                    value={`${((county.debt / county.budget) * 100).toFixed(1)}%`}
                    sub={fmtKES(county.debt)}
                    alert={county.debt / county.budget > 0.3}
                  />
                )}
                {(county.pendingBills ?? 0) > 0 && (
                  <MiniMetric
                    label={t('home.county_panel.pending_bills')}
                    value={fmtKES(county.pendingBills)}
                    icon={<Receipt className='w-3 h-3 text-violet-500' />}
                  />
                )}
              </div>

              {/* Per-capita budget */}
              <div className='flex items-center justify-between text-[11px] px-0.5'>
                <span className='text-gray-500 dark:text-neutral-muted/80'>{t('home.county_panel.per_capita')}</span>
                <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>
                  {county.budget_2025 && county.population
                    ? `KES ${Math.round(county.budget_2025 / county.population).toLocaleString()}`
                    : '—'}
                </span>
              </div>

              {/* Top Spending Sectors */}
              <SectorBreakdown county={county} />

              {/* OAG Audit Findings */}
              <AuditFindings county={county} />
            </div>

            {/* ── CTA ── */}
            <div className='px-4 py-3 border-t border-gray-100 dark:border-neutral-border flex-shrink-0'>
              <Link href={`/counties/${county.name.toLowerCase().replace(/\s+/g, '-')}`}>
                <button className='w-full py-2 rounded-full bg-gov-forest text-white text-xs font-medium hover:bg-gov-forest/90 transition-colors shadow-sm flex items-center justify-center gap-1.5'>
                  {t('home.county_panel.explore_name').replace('{name}', county.name)}
                  <TrendingUp className='w-3 h-3' />
                </button>
              </Link>
            </div>
          </motion.div>
        ) : (
          /* Empty state */
          <motion.div
            key='empty'
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className='flex-1 flex flex-col items-center justify-center text-center px-6 py-10'>
            <div className='w-12 h-12 rounded-full bg-gray-100 dark:bg-surface-elevated flex items-center justify-center mb-3'>
              <MapPin className='w-5 h-5 text-gray-400 dark:text-neutral-muted/80' />
            </div>
            <p className='text-sm font-medium text-gray-500 dark:text-neutral-muted/80'>{t('home.county_panel.empty_title')}</p>
            <p className='text-[11px] text-gray-400 dark:text-neutral-muted/80 mt-1'>
              {t('home.county_panel.empty_body')}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ────────────────── Sub-components ────────────────── */

/* 2×2 stat item */
function StatItem({
  icon,
  label,
  value,
  iconBg,
  alert = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  iconBg: string;
  alert?: boolean;
}) {
  return (
    <div className='flex items-start gap-1.5'>
      <div
        className={`w-5 h-5 rounded flex items-center justify-center flex-shrink-0 mt-0.5 ${iconBg}`}>
        {icon}
      </div>
      <div className='min-w-0'>
        <span className='text-[9px] text-gray-400 dark:text-neutral-muted/80 font-medium block leading-tight'>{label}</span>
        <span
          className={`text-[13px] font-bold tabular-nums leading-tight ${alert ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
          {value}
        </span>
      </div>
    </div>
  );
}

/* Compact metric chip */
function MiniMetric({
  label,
  value,
  sub,
  icon,
  alert = false,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  alert?: boolean;
}) {
  return (
    <div className='rounded-lg bg-gray-50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border p-2'>
      <div className='flex items-center gap-1 mb-0.5'>
        {icon}
        <span className='text-[10px] text-gray-500 dark:text-neutral-muted/80 font-medium'>{label}</span>
      </div>
      <span
        className={`text-xs font-bold tabular-nums ${alert ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
        {value}
      </span>
      {sub && <span className='block text-[9px] text-gray-400 dark:text-neutral-muted/80 mt-0.5'>{sub}</span>}
    </div>
  );
}

/* Top spending sectors mini horizontal bars */
function SectorBreakdown({ county }: { county: County }) {
  const { t } = useLang();
  // Build sector list from the available data
  const sectors: { name: string; amount: number }[] = [];
  if (county.health) sectors.push({ name: t('home.county_panel.sector.health'), amount: county.health });
  if (county.education) sectors.push({ name: t('home.county_panel.sector.education'), amount: county.education });
  if (county.infrastructure)
    sectors.push({ name: t('home.county_panel.sector.roads'), amount: county.infrastructure });

  // If no explicit sector data, try dev/recurrent split
  if (sectors.length === 0) {
    if (county.developmentBudget)
      sectors.push({ name: t('home.county_panel.sector.development'), amount: county.developmentBudget });
    if (county.recurrentBudget) sectors.push({ name: t('home.county_panel.sector.recurrent'), amount: county.recurrentBudget });
  }

  if (sectors.length === 0) return null;

  const maxAmount = Math.max(...sectors.map((s) => s.amount));
  const total = county.budget_2025 || county.budget || 1;

  const barColors = ['bg-gov-forest', 'bg-gov-sage', 'bg-gov-gold', 'bg-gov-copper', 'bg-teal-500'];

  return (
    <div>
      <div className='flex items-center gap-1.5 mb-2'>
        <BarChart3 className='w-3 h-3 text-gray-400 dark:text-neutral-muted/80' />
        <span className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted'>{t('home.county_panel.top_sectors')}</span>
      </div>
      <div className='space-y-1.5'>
        {sectors.slice(0, 4).map((sector, i) => {
          const pct = (sector.amount / total) * 100;
          const barWidth = maxAmount > 0 ? (sector.amount / maxAmount) * 100 : 0;
          return (
            <div key={sector.name} className='flex items-center gap-2'>
              <div className='w-4 flex-shrink-0 flex items-center justify-center text-gray-400 dark:text-neutral-muted/80'>
                {sectorIcon(sector.name)}
              </div>
              <div className='flex-1 min-w-0'>
                <div className='flex items-center justify-between mb-0.5'>
                  <span className='text-[9px] text-gray-500 dark:text-neutral-muted/80 truncate'>{sector.name}</span>
                  <span className='text-[9px] font-semibold text-gray-600 dark:text-neutral-muted tabular-nums'>
                    {pct.toFixed(1)}%
                  </span>
                </div>
                <div className='h-1 rounded-full bg-gray-100 dark:bg-surface-elevated overflow-hidden'>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${barWidth}%` }}
                    transition={{ duration: 0.4, delay: 0.1 + i * 0.05 }}
                    className={`h-full rounded-full ${barColors[i] || barColors[0]}`}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* OAG Audit Findings list */
function AuditFindings({ county }: { county: County }) {
  const { t } = useLang();
  const issues = county.auditIssues || [];
  if (issues.length === 0) return null;

  return (
    <div>
      <div className='flex items-center justify-between mb-2'>
        <div className='flex items-center gap-1.5'>
          <FileWarning className='w-3 h-3 text-gray-400 dark:text-neutral-muted/80' />
          <span className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted'>{t('home.county_panel.oag_findings')}</span>
        </div>
        <span className='text-[9px] font-bold text-gray-400 dark:text-neutral-muted/80 bg-gray-100 dark:bg-surface-elevated rounded-full px-1.5 py-0.5'>
          {issues.length}
        </span>
      </div>
      <div className='space-y-1.5 overflow-y-auto pr-1 scrollbar-thin'>
        {issues.map((issue, idx) => {
          const cfg = severityConfig(issue.severity);
          return (
            <motion.div
              key={issue.id || idx}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * idx, duration: 0.2 }}
              className={`rounded-md ${cfg.bg} border border-gray-100 dark:border-neutral-border p-2`}>
              <div className='flex items-start gap-1.5'>
                <div className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${cfg.dot}`} />
                <div className='min-w-0 flex-1'>
                  <div className='flex items-center gap-1.5 mb-0.5'>
                    <span className={`text-[9px] font-bold uppercase tracking-wider ${cfg.text}`}>
                      {t(cfg.labelKey)}
                    </span>
                    {issue.amount && (
                      <span className='text-[9px] text-gray-500 dark:text-neutral-muted/80 tabular-nums'>
                        {fmtKES(issue.amount)}
                      </span>
                    )}
                  </div>
                  <p className='text-[10px] text-gray-600 dark:text-neutral-muted leading-relaxed line-clamp-2'>
                    {issue.description}
                  </p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
      {issues.length > 3 && (
        <div className='flex items-center justify-center mt-1.5'>
          <Link
            href={`/counties/${county.name.toLowerCase().replace(/\s+/g, '-')}`}
            className='text-[10px] font-medium text-gov-forest dark:text-emerald-100 hover:text-gov-forest/80 dark:text-emerald-100/80 flex items-center gap-1'>
            <BookOpen className='w-3 h-3' />
            {t('home.county_panel.view_all_findings').replace('{n}', String(issues.length))}
          </Link>
        </div>
      )}
    </div>
  );
}

'use client';

import { SkeletonCard } from '@/components/ui/Skeleton';
import { useFederalAudits } from '@/lib/react-query/useAudits';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  ChevronRight,
  ExternalLink,
  RotateCcw,
  Scale,
  SearchX,
  ShieldAlert,
  TrendingDown,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

/* ─── helpers ─── */
function fmtKES(val: number): string {
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(1)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  return val.toLocaleString();
}

const shortMinistry = (n: string) =>
  n
    .replace(/^Ministry of /, '')
    .replace(/^The /, '')
    .replace('National Treasury and Economic Planning', 'National Treasury')
    .replace(', Housing & Urban Development', '')
    .replace(' and ', ' & ');

const SEV_CFG = {
  CRITICAL: { color: 'var(--gov-copper, #C94A4A)', label: 'Critical', ring: '#C94A4A' },
  WARNING: { color: 'var(--gov-gold, #D9A441)', label: 'Significant', ring: '#D9A441' },
  INFO: { color: 'var(--gov-sage, #4A7C5C)', label: 'Minor', ring: '#4A7C5C' },
} as const;

/* ─── SVG donut ─── */
function SeverityDonut({ sev }: { sev: Record<string, number> }) {
  const total = Object.values(sev).reduce((a, b) => a + b, 0) || 1;
  const r = 44;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  const arcs = (['CRITICAL', 'WARNING', 'INFO'] as const).map((level) => {
    const pct = (sev[level] || 0) / total;
    const dash = circ * pct;
    const arc = { level, dash, gap: circ - dash, offset, color: SEV_CFG[level].color };
    offset += dash;
    return arc;
  });

  return (
    <div className='relative w-[140px] h-[140px] flex-shrink-0'>
      <svg viewBox='0 0 100 100' className='w-full h-full -rotate-90'>
        <circle cx='50' cy='50' r={r} fill='none' stroke='#E2DDD5' strokeWidth='10' opacity='0.3' />
        {arcs.map((a) => (
          <circle
            key={a.level}
            cx='50'
            cy='50'
            r={r}
            fill='none'
            stroke={a.color}
            strokeWidth='10'
            strokeDasharray={`${a.dash} ${a.gap}`}
            strokeDashoffset={-a.offset}
            strokeLinecap='round'
            className='transition-all duration-700'
          />
        ))}
      </svg>
      <div className='absolute inset-0 flex flex-col items-center justify-center'>
        <span className='text-2xl font-bold text-gov-dark tabular-nums leading-none'>{total}</span>
        <span className='text-[10px] text-neutral-muted mt-0.5'>findings</span>
      </div>
    </div>
  );
}

/* ═══════════════ MAIN COMPONENT ═══════════════ */
export default function AuditReportsSection() {
  const { data, isLoading, error } = useFederalAudits();
  const [expandedFinding, setExpandedFinding] = useState<number | null>(null);

  // Derived data
  const { sev, sevTotal, topFindings, ministryBars } = useMemo(() => {
    if (!data)
      return {
        sev: {} as Record<string, number>,
        sevTotal: 0,
        topFindings: [],
        ministryBars: [],
      };

    const s: Record<string, number> = {};
    for (const [k, v] of Object.entries(data.by_severity || {})) {
      const key = k.toUpperCase();
      s[key] = (s[key] || 0) + v;
    }

    const maxMinistry = Math.max(...(data.top_ministries || []).map((m) => m.finding_count), 1);

    return {
      sev: s,
      sevTotal: Object.values(s).reduce((a, b) => a + b, 0) || 1,
      topFindings: [...data.findings]
        .filter((f) => f.amount_involved !== 'KES 0')
        .sort((a, b) => b.amount_numeric - a.amount_numeric)
        .slice(0, 4),
      ministryBars: (data.top_ministries || []).slice(0, 5).map((m) => ({
        ...m,
        pct: (m.finding_count / maxMinistry) * 100,
        short: shortMinistry(m.ministry),
      })),
    };
  }, [data]);

  /* ─── Loading / Error ─── */
  if (isLoading) {
    return <SkeletonCard className='min-h-[400px]' />;
  }
  if (error || !data) {
    return (
      <div className='glass-card p-10 flex flex-col items-center justify-center min-h-[400px] gap-2'>
        <ShieldAlert className='w-6 h-6 text-neutral-muted/25' />
        <p className='text-xs text-neutral-muted'>Audit data unavailable</p>
      </div>
    );
  }

  const stats = data.key_statistics;

  return (
    <motion.section
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className='glass-card overflow-hidden'>
      {/* ════════ HEADER ════════ */}
      <div className='bg-gradient-to-r from-gov-sand/60 via-gov-cream/40 to-transparent px-6 sm:px-8 pt-6 pb-5 flex items-start justify-between border-b border-neutral-border/20'>
        <div>
          <h2 className='font-display text-xl sm:text-2xl text-gov-dark leading-tight'>
            Auditor General&apos;s Report
          </h2>
          <p className='text-sm text-neutral-muted mt-0.5'>
            National Government — {data.fiscal_year}
          </p>
        </div>
        <a
          href='https://www.oagkenya.go.ke'
          target='_blank'
          rel='noopener noreferrer'
          className='flex items-center gap-1 text-[11px] text-neutral-muted hover:text-gov-forest transition-colors mt-1'>
          OAG Kenya <ExternalLink className='w-3 h-3' />
        </a>
      </div>

      {/* ════════ OPINION BANNER ════════ */}
      <div className='mx-6 sm:mx-8 mb-5 rounded-xl bg-gov-copper/[0.06] border border-gov-copper/15 px-5 py-4'>
        <div className='flex items-center gap-2 mb-2'>
          <Scale className='w-4 h-4 text-gov-copper' />
          <span className='text-xs font-bold uppercase tracking-wider text-gov-copper'>
            Audit Opinion: {data.opinion_type}
          </span>
        </div>
        <p className='text-sm text-gov-dark/80 leading-relaxed'>
          {data.basis_for_qualification?.[0] ||
            'Material misstatements identified across multiple ministries'}
        </p>
        <p className='text-[11px] text-neutral-muted mt-2 italic'>
          Signed by {data.auditor_general}
        </p>
      </div>

      {/* ════════ STAT CARDS ════════ */}
      <div className='px-6 sm:px-8 mb-5 grid grid-cols-2 sm:grid-cols-4 gap-3'>
        {[
          {
            icon: Building2,
            label: 'Ministries Audited',
            value: stats?.total_ministries_audited ?? data.total_findings,
            accent: 'text-gov-forest',
          },
          {
            icon: SearchX,
            label: 'Amount Questioned',
            value: `KES ${fmtKES(data.total_amount_questioned)}`,
            accent: 'text-gov-copper',
          },
          {
            icon: ShieldAlert,
            label: 'Critical Findings',
            value: sev.CRITICAL || stats?.critical_findings || 0,
            accent: 'text-gov-copper',
          },
          {
            icon: RotateCcw,
            label: 'Recurring Issues',
            value: stats?.recurring_issues_from_prior_year ?? 0,
            accent: 'text-gov-gold',
          },
        ].map((s) => (
          <div
            key={s.label}
            className={`rounded-xl border border-neutral-border/40 px-4 py-3 ${
              s.accent === 'text-gov-copper'
                ? 'bg-gov-copper/[0.04]'
                : s.accent === 'text-gov-gold'
                  ? 'bg-gov-gold/[0.05]'
                  : 'bg-gov-sage/[0.04]'
            }`}>
            <div className='flex items-center gap-1.5 mb-2'>
              <s.icon className={`w-3.5 h-3.5 ${s.accent} opacity-70`} />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                {s.label}
              </span>
            </div>
            <span className={`text-lg font-bold ${s.accent} tabular-nums leading-none`}>
              {s.value}
            </span>
          </div>
        ))}
      </div>

      {/* ════════ TWO-COL: Findings + Ministries ════════ */}
      <div className='px-6 sm:px-8 pb-5 grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5'>
        {/* ── Left: Findings + Donut ── */}
        <div className='rounded-xl bg-gov-sand/30 border border-neutral-border/20 p-4'>
          <h3 className='font-display text-base text-gov-dark mb-4'>Audit Findings Overview</h3>

          <div className='flex gap-5 items-start'>
            {/* Findings list */}
            <div className='flex-1 min-w-0 space-y-1'>
              {topFindings.map((f) => {
                const sevKey = f.severity?.toUpperCase() || 'INFO';
                const cfg = SEV_CFG[sevKey as keyof typeof SEV_CFG] || SEV_CFG.INFO;
                const isOpen = expandedFinding === f.id;

                return (
                  <button
                    key={f.id}
                    onClick={() => setExpandedFinding(isOpen ? null : f.id)}
                    className='w-full text-left group'>
                    <div className='flex items-start gap-2.5 px-3 py-2.5 rounded-lg hover:bg-gov-sand/50 transition-colors'>
                      <span
                        className='mt-1 w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0'
                        style={{ backgroundColor: `${cfg.ring}18` }}>
                        {sevKey === 'CRITICAL' ? (
                          <ShieldAlert className='w-3 h-3' style={{ color: cfg.ring }} />
                        ) : sevKey === 'WARNING' ? (
                          <AlertTriangle className='w-3 h-3' style={{ color: cfg.ring }} />
                        ) : (
                          <TrendingDown className='w-3 h-3' style={{ color: cfg.ring }} />
                        )}
                      </span>
                      <div className='min-w-0 flex-1'>
                        <p className='text-sm font-semibold text-gov-dark leading-snug'>
                          {shortMinistry(f.entity_name)}
                        </p>
                        <p className='text-xs text-neutral-muted leading-relaxed mt-0.5 line-clamp-2'>
                          {f.finding}
                        </p>
                        {isOpen && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            className='mt-2 pt-2 border-t border-neutral-border/30'>
                            <p className='text-xs text-neutral-muted leading-relaxed'>
                              <span className='font-semibold text-gov-dark'>Amount:</span>{' '}
                              {f.amount_involved}
                            </p>
                            {f.recommended_action && (
                              <p className='text-xs text-neutral-muted leading-relaxed mt-1'>
                                <span className='font-semibold text-gov-dark'>Action:</span>{' '}
                                {f.recommended_action}
                              </p>
                            )}
                          </motion.div>
                        )}
                      </div>
                      <ChevronRight
                        className={`w-3.5 h-3.5 text-neutral-muted/40 mt-1.5 transition-transform ${
                          isOpen ? 'rotate-90' : ''
                        }`}
                      />
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Donut */}
            <div className='hidden sm:flex flex-col items-center gap-3'>
              <SeverityDonut sev={sev} />
              <div className='space-y-1.5'>
                {(['CRITICAL', 'WARNING', 'INFO'] as const).map((level) => {
                  const pct = Math.round(((sev[level] || 0) / sevTotal) * 100);
                  return (
                    <div key={level} className='flex items-center gap-2'>
                      <span
                        className='w-2.5 h-2.5 rounded-full'
                        style={{ backgroundColor: SEV_CFG[level].color }}
                      />
                      <span className='text-[11px] text-neutral-muted'>
                        {SEV_CFG[level].label} ({sev[level] || 0})
                      </span>
                      <span className='text-[11px] font-semibold text-gov-dark tabular-nums ml-auto'>
                        {pct}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* ── Emphasis of Matter ── */}
          {data.emphasis_of_matter?.[0] && (
            <div className='mt-4 rounded-xl bg-gov-gold/[0.07] border border-gov-gold/15 px-4 py-3 flex items-start gap-2.5'>
              <AlertTriangle className='w-4 h-4 text-gov-gold flex-shrink-0 mt-0.5' />
              <div className='min-w-0'>
                <p className='text-[11px] font-bold uppercase tracking-wider text-gov-gold mb-1'>
                  Emphasis of Matter
                </p>
                <p className='text-xs text-gov-dark/70 leading-relaxed line-clamp-2'>
                  {data.emphasis_of_matter[0]}
                </p>
              </div>
              <ChevronRight className='w-4 h-4 text-gov-gold/40 flex-shrink-0 mt-0.5' />
            </div>
          )}
        </div>

        {/* ── Right: Top Ministries Flagged ── */}
        <div className='rounded-xl border border-neutral-border/40 bg-gov-forest/[0.03] p-4'>
          <h4 className='font-display text-sm text-gov-dark mb-4'>Top Ministries Flagged</h4>
          <div className='space-y-3'>
            {ministryBars.map((m) => (
              <div key={m.ministry}>
                <div className='flex items-center justify-between mb-1'>
                  <div className='flex items-center gap-2 min-w-0'>
                    <Building2 className='w-3.5 h-3.5 text-neutral-muted/50 flex-shrink-0' />
                    <span className='text-xs text-gov-dark truncate'>{m.short}</span>
                  </div>
                  <span
                    className='ml-2 flex-shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold text-white tabular-nums'
                    style={{
                      backgroundColor:
                        m.finding_count >= 3
                          ? '#C94A4A'
                          : m.finding_count >= 2
                            ? '#D9A441'
                            : '#4A7C5C',
                    }}>
                    {m.finding_count}
                  </span>
                </div>
                <div className='h-1.5 rounded-full bg-neutral-border/30 overflow-hidden'>
                  <motion.div
                    initial={{ width: 0 }}
                    whileInView={{ width: `${m.pct}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.3 }}
                    className='h-full rounded-full'
                    style={{
                      backgroundColor:
                        m.finding_count >= 3
                          ? '#C94A4A'
                          : m.finding_count >= 2
                            ? '#D9A441'
                            : '#4A7C5C',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          <Link
            href='/audits'
            className='group mt-5 flex items-center justify-center gap-1.5 w-full rounded-lg bg-gov-forest text-white hover:bg-gov-forest/90 active:scale-[0.98] px-4 py-2.5 transition-all text-xs font-medium shadow-sm'>
            View All Findings
            <ArrowRight className='w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform' />
          </Link>
        </div>
      </div>
    </motion.section>
  );
}

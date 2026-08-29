'use client';

import { SkeletonCard } from '@/components/ui/Skeleton';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
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

const SEV_CFG: Record<
  'CRITICAL' | 'WARNING' | 'INFO',
  { color: string; labelKey: TranslationKey; ring: string }
> = {
  CRITICAL: { color: 'var(--gov-copper, #C94A4A)', labelKey: 'home.audits.sev_critical', ring: '#C94A4A' },
  WARNING: { color: 'var(--gov-gold, #D9A441)', labelKey: 'home.audits.sev_significant', ring: '#D9A441' },
  INFO: { color: 'var(--gov-sage, #4A7C5C)', labelKey: 'home.audits.sev_minor', ring: '#4A7C5C' },
};

/* ─── SVG donut ─── */
function SeverityDonut({ sev }: { sev: Record<string, number> }) {
  const { t } = useLang();
  // The rendered count is the real sum. The `|| 1` denominator exists ONLY
  // to keep the arc arithmetic finite — it must never surface as a count
  // (it used to: an empty severity map rendered as "1 findings").
  const total = Object.values(sev).reduce((a, b) => a + b, 0);
  const denom = total || 1;
  const r = 44;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  const arcs = (['CRITICAL', 'WARNING', 'INFO'] as const).map((level) => {
    const pct = (sev[level] || 0) / denom;
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
        <span className='text-2xl font-bold text-gov-dark dark:text-white tabular-nums leading-none'>{total}</span>
        <span className='text-[10px] text-neutral-muted mt-0.5'>{t('home.audits.findings_label')}</span>
      </div>
    </div>
  );
}

/* ═══════════════ MAIN COMPONENT ═══════════════ */
export default function AuditReportsSection() {
  const { t } = useLang();
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
      // Real sum — 0 means 0. Guards against division live at use sites.
      sevTotal: Object.values(s).reduce((a, b) => a + b, 0),
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
        <p className='text-xs text-neutral-muted'>{t('home.audits.unavailable')}</p>
      </div>
    );
  }

  const stats = data.key_statistics;

  // Zero publishable findings is a real state that deserves a real empty
  // state — not an empty donut over a bare button. Everything rendered
  // below comes from the response (withheld_findings, findings_reason,
  // next_expected); no schedule fact is hand-written here.
  const isEmpty = (data.findings?.length ?? 0) === 0;
  const withheld = data.withheld_findings ?? 0;
  const nx = data.next_expected;
  const fmtWindowMonth = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-KE', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    });
  const cadenceWord = (cadence: string | null | undefined) => {
    if (cadence === 'annual') return t('home.audits.cadence_annual');
    if (cadence === 'quarterly') return t('home.audits.cadence_quarterly');
    if (cadence === 'monthly') return t('home.audits.cadence_monthly');
    return cadence ?? '';
  };
  const lagPhrase =
    nx?.lag != null
      ? t(nx.lag_unit === 'days' ? 'home.audits.lag_days' : 'home.audits.lag_months').replace(
          '{lag}',
          String(nx.lag)
        )
      : '';
  const windowSentence =
    nx?.window_start && nx?.window_end
      ? t('home.audits.empty_window')
          .replace('{publisher}', nx.publisher ?? 'Office of the Auditor-General')
          .replace('{cadence}', cadenceWord(nx.cadence))
          .replace('{lag}', lagPhrase)
          .replace('{start}', fmtWindowMonth(nx.window_start))
          .replace('{end}', fmtWindowMonth(nx.window_end))
      : null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className='glass-card overflow-hidden'>
      {/* ════════ HEADER ════════ */}
      <div className='bg-gradient-to-r from-gov-sand/60 via-gov-cream/40 to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-6 sm:px-8 pt-6 pb-5 flex items-start justify-between border-b border-neutral-border/20'>
        <div>
          <h2 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white leading-tight'>
            {t('home.audits.report_title')}
          </h2>
          {data.fiscal_year && (
            <p className='text-sm text-neutral-muted mt-0.5'>
              {t('home.audits.national_govt_fy').replace('{fy}', String(data.fiscal_year))}
            </p>
          )}
        </div>
        <a
          href='https://www.oagkenya.go.ke'
          target='_blank'
          rel='noopener noreferrer'
          className='flex items-center gap-1 text-[11px] text-neutral-muted hover:text-gov-forest dark:text-emerald-100 transition-colors mt-1'>
          OAG Kenya <ExternalLink className='w-3 h-3' />
        </a>
      </div>

      {/* ════════ OPINION BANNER ════════ */}
      {/* The opinion, its basis and the signature all describe one document.
          When that document is not traceable, asserting any of them — least of
          all the hardcoded "Material misstatements identified across multiple
          ministries" this used to fall back to — attributes a finding to the
          Auditor-General that no source supports. */}
      {data.opinion_type || data.basis_for_qualification?.length ? (
        <div className='mx-6 sm:mx-8 mb-5 rounded-xl bg-gov-copper/[0.06] border border-gov-copper/15 px-5 py-4'>
          <div className='flex items-center gap-2 mb-2'>
            <Scale className='w-4 h-4 text-gov-copper' />
            <span className='text-xs font-bold uppercase tracking-wider text-gov-copper'>
              {t('home.audits.opinion_label')} {data.opinion_type}
            </span>
          </div>
          {data.basis_for_qualification?.[0] && (
            <p className='text-sm text-gov-dark/80 dark:text-white/80 leading-relaxed'>
              {data.basis_for_qualification[0]}
            </p>
          )}
          {data.auditor_general && (
            <p className='text-[11px] text-neutral-muted mt-2 italic'>
              {t('home.audits.signed_by').replace('{name}', data.auditor_general)}
            </p>
          )}
        </div>
      ) : (
        <div className='mx-6 sm:mx-8 mb-5 rounded-xl bg-neutral-surface/60 dark:bg-surface-elevated border border-neutral-border/40 px-5 py-4'>
          <div className='flex items-center gap-2 mb-2'>
            <Scale className='w-4 h-4 text-neutral-muted' />
            <span className='text-xs font-bold uppercase tracking-wider text-neutral-muted'>
              Audit opinion not yet published here
            </span>
          </div>
          <p className='text-sm text-gov-dark/70 dark:text-white/70 leading-relaxed'>
            No Auditor-General opinion is shown because none currently traces to
            a page of a published report. This is not a finding that the
            national accounts are clean.
          </p>
          {typeof data.withheld_findings === 'number' && data.withheld_findings > 0 && (
            <p className='text-[11px] text-neutral-muted mt-2'>
              {data.withheld_findings} finding
              {data.withheld_findings === 1 ? '' : 's'} held back for lack of a
              traceable source document.
            </p>
          )}
        </div>
      )}

      {/* ════════ STAT CARDS ════════ */}
      <div className='px-6 sm:px-8 mb-5 grid grid-cols-2 sm:grid-cols-4 gap-3'>
        {([
          {
            icon: Building2,
            labelKey: 'home.audits.stat_ministries' as TranslationKey,
            // Authoritative count only; never fall back to the findings
            // count (which inflated this to "25"). Honest "—" when absent.
            value: stats?.total_ministries_audited ?? '—',
            accent: 'text-gov-forest dark:text-emerald-100',
          },
          {
            icon: SearchX,
            labelKey: 'home.audits.stat_amount' as TranslationKey,
            // Authoritative OAG questioned total; fall back to the report's
            // own label string, then an em-dash — never a fabricated sum.
            value:
              data.total_amount_questioned != null
                ? `KES ${fmtKES(data.total_amount_questioned)}`
                : data.total_amount_questioned_label || '—',
            accent: 'text-gov-copper',
          },
          {
            icon: ShieldAlert,
            labelKey: 'home.audits.stat_critical' as TranslationKey,
            // Prefer the OAG report's own critical count (the severity-band
            // tally over-counts because seed maps "high" -> CRITICAL).
            value: stats?.critical_findings ?? sev.CRITICAL ?? '—',
            accent: 'text-gov-copper',
          },
          {
            icon: RotateCcw,
            labelKey: 'home.audits.stat_recurring' as TranslationKey,
            // Honest "—" when unavailable: a fake "0" reads as "no recurring
            // issues", the opposite of the truth when the figure is missing.
            value: stats?.recurring_issues_from_prior_year ?? '—',
            accent: 'text-gov-gold',
          },
        ] as const).map((s) => (
          <div
            key={s.labelKey}
            className={`rounded-xl border border-neutral-border/40 px-4 py-3 dark:bg-surface-elevated/40 ${
              s.accent === 'text-gov-copper'
                ? 'bg-gov-copper/[0.04]'
                : s.accent === 'text-gov-gold'
                  ? 'bg-gov-gold/[0.05]'
                  : 'bg-gov-sage/[0.04]'
            }`}>
            <div className='flex items-center gap-1.5 mb-2'>
              <s.icon className={`w-3.5 h-3.5 ${s.accent} opacity-70`} />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                {t(s.labelKey)}
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
        <div className='rounded-xl bg-gov-sand/30 dark:bg-surface-elevated/40 border border-neutral-border/20 p-4'>
          <h3 className='font-display text-base text-gov-dark dark:text-white mb-4'>{t('home.audits.findings_overview')}</h3>

          {isEmpty ? (
            <div className='flex flex-col items-start gap-2 py-4'>
              <div className='flex items-center gap-2'>
                <SearchX className='w-4 h-4 text-neutral-muted/60 flex-shrink-0' />
                <p className='text-sm font-semibold text-gov-dark dark:text-white'>
                  {t('home.audits.empty_title')}
                </p>
              </div>
              {withheld > 0 && (
                <p className='text-xs text-neutral-muted leading-relaxed'>
                  {t('home.audits.empty_withheld').replace('{n}', String(withheld))}
                </p>
              )}
              {windowSentence && (
                <p className='text-xs text-neutral-muted leading-relaxed'>{windowSentence}</p>
              )}
            </div>
          ) : (
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
                    <div className='flex items-start gap-2.5 px-3 py-2.5 rounded-lg hover:bg-gov-sand/50 dark:hover:bg-surface-elevated transition-colors'>
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
                        <p className='text-sm font-semibold text-gov-dark dark:text-white leading-snug'>
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
                              <span className='font-semibold text-gov-dark dark:text-white'>{t('home.audits.amount_prefix')}</span>{' '}
                              {f.amount_involved}
                            </p>
                            {f.recommended_action && (
                              <p className='text-xs text-neutral-muted leading-relaxed mt-1'>
                                <span className='font-semibold text-gov-dark dark:text-white'>{t('home.audits.action_prefix')}</span>{' '}
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
                  const pct = sevTotal ? Math.round(((sev[level] || 0) / sevTotal) * 100) : 0;
                  return (
                    <div key={level} className='flex items-center gap-2'>
                      <span
                        className='w-2.5 h-2.5 rounded-full'
                        style={{ backgroundColor: SEV_CFG[level].color }}
                      />
                      <span className='text-[11px] text-neutral-muted'>
                        {t(SEV_CFG[level].labelKey)} ({sev[level] || 0})
                      </span>
                      <span className='text-[11px] font-semibold text-gov-dark dark:text-white tabular-nums ml-auto'>
                        {pct}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          )}

          {/* ── Emphasis of Matter ── */}
          {data.emphasis_of_matter?.[0] && (
            <div className='mt-4 rounded-xl bg-gov-gold/[0.07] dark:bg-gov-gold/[0.12] border border-gov-gold/15 dark:border-gov-gold/30 px-4 py-3 flex items-start gap-2.5'>
              <AlertTriangle className='w-4 h-4 text-gov-gold flex-shrink-0 mt-0.5' />
              <div className='min-w-0'>
                <p className='text-[11px] font-bold uppercase tracking-wider text-gov-gold mb-1'>
                  {t('home.audits.emphasis')}
                </p>
                <p className='text-xs text-gov-dark/70 dark:text-white/70 leading-relaxed line-clamp-2'>
                  {data.emphasis_of_matter[0]}
                </p>
              </div>
              <ChevronRight className='w-4 h-4 text-gov-gold/40 flex-shrink-0 mt-0.5' />
            </div>
          )}
        </div>

        {/* ── Right: Top Ministries Flagged ── */}
        <div className='rounded-xl border border-neutral-border/40 bg-gov-forest/[0.03] dark:bg-surface-elevated/40 p-4'>
          <h4 className='font-display text-sm text-gov-dark dark:text-white mb-4'>{t('home.audits.top_ministries')}</h4>
          {ministryBars.length === 0 && (
            <p className='text-xs text-neutral-muted leading-relaxed'>
              {t('home.audits.empty_ministries')}
            </p>
          )}
          <div className='space-y-3'>
            {ministryBars.map((m) => (
              <div key={m.ministry}>
                <div className='flex items-center justify-between mb-1'>
                  <div className='flex items-center gap-2 min-w-0'>
                    <Building2 className='w-3.5 h-3.5 text-neutral-muted/50 flex-shrink-0' />
                    <span className='text-xs text-gov-dark dark:text-white truncate'>{m.short}</span>
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
            {t('home.audits.view_all_findings')}
            <ArrowRight className='w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform' />
          </Link>
        </div>
      </div>
    </motion.section>
  );
}

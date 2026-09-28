import type { TranslationKey } from '@/lib/i18n/messages';
import { CheckCircle2, CircleHelp, Flag, Info, ShieldAlert } from 'lucide-react';
import styles from './CountyExperience.module.css';

export type SignalTone = 'positive' | 'watch' | 'concern' | 'critical' | 'info' | 'unavailable';
type GradeSignal = { tone: SignalTone; labelKey: TranslationKey };

const GRADE_SIGNALS: Record<string, GradeSignal> = {
  excellent: { tone: 'positive', labelKey: 'county.acct.grade_excellent' },
  good: { tone: 'positive', labelKey: 'county.acct.grade_good' },
  fair: { tone: 'watch', labelKey: 'county.acct.grade_fair' },
  concern: { tone: 'concern', labelKey: 'county.acct.grade_needs_improvement' },
  poor: { tone: 'critical', labelKey: 'county.acct.grade_poor' },
  unavailable: { tone: 'unavailable', labelKey: 'county.acct.grade_ungraded' },
};

// These are the two existing, distinct grade scales. Styling never recalculates a score.
export function gradeSignal(
  grade: string | null | undefined,
  scale: 'health' | 'audit'
): GradeSignal {
  const bands: Record<string, string> =
    scale === 'health'
      ? { A: 'excellent', 'B+': 'good', B: 'fair', 'B-': 'concern', C: 'poor' }
      : { A: 'excellent', B: 'good', C: 'fair', D: 'concern', F: 'poor' };
  const key = grade ?? '';
  return GRADE_SIGNALS[
    Object.prototype.hasOwnProperty.call(bands, key) ? bands[key] : 'unavailable'
  ];
}

export function severityTone(severity: string): SignalTone {
  return severity === 'critical' ? 'critical' : severity === 'warning' ? 'watch' : 'info';
}

export function SignalMark({ tone, size = 14 }: { tone: SignalTone; size?: number }) {
  const Icon = {
    positive: CheckCircle2,
    watch: Flag,
    concern: Flag,
    critical: ShieldAlert,
    info: Info,
    unavailable: CircleHelp,
  }[tone];
  return <Icon size={size} strokeWidth={1.8} aria-hidden='true' />;
}

export function AuditStatusSignal({
  status,
  label,
  className = '',
}: {
  status: string | null | undefined;
  label: string;
  className?: string;
}) {
  const tones: Record<string, SignalTone> = {
    clean: 'positive',
    unqualified: 'positive',
    qualified: 'watch',
    adverse: 'critical',
    disclaimer: 'critical',
  };
  const key = status?.toLowerCase() ?? '';
  const tone = Object.prototype.hasOwnProperty.call(tones, key) ? tones[key] : 'unavailable';
  return (
    <span className={`${styles.signal} ${styles.statusSignal} ${className}`} data-tone={tone}>
      <SignalMark tone={tone} />
      {label}
    </span>
  );
}

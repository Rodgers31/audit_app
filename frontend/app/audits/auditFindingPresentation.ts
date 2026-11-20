import { AUDITS_MESSAGES } from '@/lib/i18n/messages/audits';

export function formatFindingAmount(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1e12) return `KES ${(value / 1e12).toFixed(2)}T`;
  if (absolute >= 1e9) return `KES ${(value / 1e9).toFixed(1)}B`;
  if (absolute >= 1e6) return `KES ${(value / 1e6).toFixed(1)}M`;
  return `KES ${value.toLocaleString()}`;
}

export const FINDING_SEVERITY: Record<string, { label: keyof typeof AUDITS_MESSAGES; tone: string }> = {
  critical: { label: 'audits.severity_critical', tone: 'text-signal-alarm' },
  warning: { label: 'audits.severity_warning', tone: 'text-signal-caution' },
  info: { label: 'audits.severity_info', tone: 'text-neutral-text' },
};

/** Carries a published figure and its own receipt. Callers must use public observations. */
export interface PublicFigureShareInput {
  visibility: 'public';
  metric: string | null;
  value: string | null;
  source: {
    publisher: string | null;
    period: string | null;
    url: string | null;
  } | null;
}

export interface PublicFigureShareData {
  metric: string;
  value: string;
  publisher: string;
  period: string;
  sourceUrl: string;
}

export const SHARE_CARD_SITE = 'auditgava.com';
export const SHARE_CARD_FILENAME = 'auditgava-figure.png';

// The exported card uses the light AuditGava palette on any destination.
export const SHARE_CARD_COLORS = {
  paper: '#FBFAF6',
  ink: '#101B14',
  muted: '#5C6B72',
  accent: '#176B49',
  rule: '#D8D0C1',
} as const;

const hasText = (value: string | null | undefined): value is string =>
  typeof value === 'string' && value.trim().length > 0;

function publicReportUrl(input: string) {
  try {
    const url = new URL(input);
    const hostname = url.hostname.toLowerCase().replace(/\.$/, '');
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password ||
        !hostname.includes('.') || /^[0-9.]+$/.test(hostname) ||
        /\.(?:localhost|local|internal|invalid|test)$/.test(hostname)) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function preparePublicFigure(input: PublicFigureShareInput | null):
  | { status: 'missingFigure' | 'missingSource' | 'invalidSource' }
  | { status: 'ready'; figure: PublicFigureShareData } {
  if (input?.visibility !== 'public' || !hasText(input.metric) || !hasText(input.value)) {
    return { status: 'missingFigure' };
  }
  const source = input.source;
  if (!hasText(source?.publisher) || !hasText(source?.period) || !hasText(source?.url)) {
    return { status: 'missingSource' };
  }
  const sourceUrl = publicReportUrl(source.url);
  if (!sourceUrl) return { status: 'invalidSource' };
  return { status: 'ready', figure: {
    metric: input.metric, value: input.value, publisher: source.publisher, period: source.period, sourceUrl,
  } };
}

export function figureSourceText({ publisher, period }: PublicFigureShareData) {
  return `${publisher} · ${period}`;
}

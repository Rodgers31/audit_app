export const AUDITOR_GUIDE_PATH = '/learn/auditor-general-guide';
export const AUDITOR_GUIDE_ANCHOR = 'auditor-general-path';
export const AUDITOR_GUIDE_ENTRY = `/learn#${AUDITOR_GUIDE_ANCHOR}`;
export const AUDITOR_ARTICLE = '/learn?article=229';

const constitution = 'https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf';
const countyAudits = 'https://libraryir.parliament.go.ke/server/api/core/bitstreams/e13a8fad-5b91-4ca2-bfa5-4d1d767be980/content';

// The county executive opinion count and denominator come from the dated Table 8.
export const AUDITOR_GUIDE_STEPS = [
  { key: 'office', figure: 8, source: `${constitution}#page=135`, destination: '/learn/glossary#term-audit' },
  { key: 'reporting', figure: 6, source: `${constitution}#page=135`, destination: '/sources#sources-method' },
  { key: 'opinion', figure: 44, total: 47, source: `${countyAudits}#page=35`, destination: '/audits' },
  { key: 'action', figure: 3, source: `${constitution}#page=136`, destination: '/counties/nairobi?tab=audit' },
] as const;

export type AuditorGuideStep = typeof AUDITOR_GUIDE_STEPS[number];

export function findAuditorGuideStep(parameter?: string | string[]): AuditorGuideStep {
  return AUDITOR_GUIDE_STEPS.find(step => step.key === parameter) ?? AUDITOR_GUIDE_STEPS[0];
}

export function auditorGuideHref(step: AuditorGuideStep): string {
  return `${AUDITOR_GUIDE_PATH}?step=${step.key}`;
}

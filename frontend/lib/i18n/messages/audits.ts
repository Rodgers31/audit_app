import type { Lang, Translation } from '../messages';

export const AUDITS_MESSAGES = {
  'audits.all_findings': { en: 'All findings', sw: 'Matokeo yote', plain: 'All findings' },
  'audits.clear_filters': { en: 'Clear filters', sw: 'Ondoa vichujio', plain: 'Clear filters' },
  'audits.year': { en: 'Year', sw: 'Mwaka', plain: 'Year' },
  'audits.all_years': { en: 'All years', sw: 'Miaka yote', plain: 'All years' },
  'audits.section': { en: 'Section', sw: 'Sehemu ya ripoti', plain: 'Report section' },
  'audits.all_sections': { en: 'All sections', sw: 'Sehemu zote za ripoti', plain: 'All sections' },
  'audits.opinion': { en: 'Audit opinion', sw: 'Maoni ya ukaguzi', plain: 'Audit result' },
  'audits.severity': { en: 'Severity', sw: 'Uzito wa tatizo', plain: 'How serious' },
  'audits.status': { en: 'Status', sw: 'Hali', plain: 'Status' },
  'audits.all': { en: 'All', sw: 'Zote', plain: 'All' },
  'audits.financial_statements': { en: 'Financial statements', sw: 'Taarifa za fedha', plain: 'Financial statements' },
  'audits.public_resources': { en: 'Use of public resources', sw: 'Matumizi ya rasilimali za umma', plain: 'Use of public resources' },
  'audits.internal_controls': { en: 'Internal controls', sw: 'Udhibiti wa ndani', plain: 'Internal controls' },
  'audits.recurring_findings': { en: 'Problems reported in more than one year', sw: 'Matatizo yaliyoripotiwa kwa zaidi ya mwaka mmoja', plain: 'Problems reported in more than one year' },
  'audits.source_report': { en: 'Source report', sw: 'Ripoti ya chanzo', plain: 'Source report' },
  'audits.qualified_basis': { en: 'Basis for qualified opinion', sw: 'Msingi wa maoni yenye masharti', plain: 'Why the auditor raised concerns' },
} satisfies Record<string, Translation>;

export function auditSectionLabel(value: string, lang: Lang): string {
  switch (value) {
    case 'Report on the Financial Statements':
      return AUDITS_MESSAGES['audits.financial_statements'][lang];
    case 'Report on Lawfulness and Effectiveness in the Use of Public Resources':
      return AUDITS_MESSAGES['audits.public_resources'][lang];
    case 'Report on Effectiveness of Internal Controls, Risk Management and Governance':
      return AUDITS_MESSAGES['audits.internal_controls'][lang];
    default:
      return value;
  }
}

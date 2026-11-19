import type { Lang, Translation } from '../messages';

export const AUDITS_MESSAGES = {
  'audits.title': { en: 'Audit Findings', sw: 'Matokeo ya Ukaguzi', plain: 'Audit Findings' },
  'audits.intro': { en: 'Published findings from the Auditor-General’s reports available in AuditGava', sw: 'Matokeo yaliyochapishwa kutoka ripoti za Mkaguzi Mkuu wa Hesabu zinazopatikana AuditGava', plain: 'What the Auditor-General found in reports available in AuditGava' },
  'audits.headline': { en: 'Auditor-General findings in AuditGava', sw: 'Matokeo ya Mkaguzi Mkuu wa Hesabu katika AuditGava', plain: 'Auditor-General findings in AuditGava' },
  'audits.count_unavailable': { en: 'Finding count unavailable', sw: 'Idadi ya matokeo haipatikani', plain: 'Finding count unavailable' },
  'audits.loss_title': { en: 'Questioned ≠ confirmed loss', sw: 'Kilichohojiwa ≠ hasara iliyothibitishwa', plain: 'Questioned ≠ confirmed loss' },
  'audits.loss_note': { en: 'Amounts the Auditor-General could not confirm were properly spent or supported. The findings are queries to be resolved.', sw: 'Kiasi ambacho Mkaguzi Mkuu wa Hesabu hakuweza kuthibitisha kuwa kilitumika ipasavyo au kilikuwa na nyaraka. Matokeo haya yanahitaji majibu.', plain: 'Amounts the auditor could not confirm were properly spent or backed by records. These questions still need answers.' },
  'audits.recorded_years': { en: 'Recorded audit years {start}–{end}', sw: 'Miaka ya ukaguzi iliyorekodiwa {start}–{end}', plain: 'Recorded audit years {start}–{end}' },
  'audits.recorded_year': { en: 'Recorded audit year {year}', sw: 'Mwaka wa ukaguzi uliorekodiwa {year}', plain: 'Recorded audit year {year}' },
  'audits.source': { en: 'Source: Auditor-General', sw: 'Chanzo: Mkaguzi Mkuu wa Hesabu', plain: 'Source: Auditor-General' },
  'audits.source_title': { en: 'About these finding counts', sw: 'Kuhusu idadi hii ya matokeo', plain: 'About these finding counts' },
  'audits.source_scope': { en: 'Counts cover findings published in AuditGava across institutions and available periods. Each published finding has a linked document and page reference.', sw: 'Idadi inahusu matokeo yaliyochapishwa katika AuditGava kwa taasisi na vipindi vinavyopatikana. Kila tokeo lililochapishwa lina kiungo cha hati na rejea ya ukurasa.', plain: 'These counts include the findings published in AuditGava from the institutions and years available. Each finding links to a document and page.' },
  'audits.source_limits': { en: 'Report-extraction completeness and the number of reports read each year are unavailable. The year chart includes findings with a recorded audit year.', sw: 'Ukamilifu wa uchimbaji wa ripoti na idadi ya ripoti zilizosomwa kila mwaka havipatikani. Chati inajumuisha matokeo yenye mwaka wa ukaguzi uliorekodiwa.', plain: 'We cannot show whether every report was fully read, or how many reports were read each year. The chart includes findings that have a recorded audit year.' },
  'audits.withheld': { en: '{count} findings withheld by the publication checks.', sw: 'Matokeo {count} yamezuiwa na ukaguzi wa masharti ya uchapishaji.', plain: '{count} findings are left out by the publication checks.' },
  'audits.withheld_unknown': { en: 'The number of withheld findings is unavailable.', sw: 'Idadi ya matokeo yaliyozuiwa kuchapishwa haipatikani.', plain: 'We do not have a count of findings left out.' },
  'audits.view_sources': { en: 'View data sources', sw: 'Angalia vyanzo vya data', plain: 'View data sources' },
  'audits.view_findings': { en: 'Read the findings and their source pages', sw: 'Soma matokeo na kurasa zake za chanzo', plain: 'Read findings and their source pages' },
  'audits.years_title': { en: 'Findings by audit year', sw: 'Matokeo kwa mwaka wa ukaguzi', plain: 'Findings by audit year' },
  'audits.years_total': { en: '{count} published findings have a recorded audit year.', sw: 'Matokeo {count} yaliyochapishwa yana mwaka wa ukaguzi uliorekodiwa.', plain: '{count} published findings have a recorded audit year.' },
  'audits.years_partial': { en: 'Published findings with a recorded audit year', sw: 'Matokeo yaliyochapishwa yenye mwaka wa ukaguzi uliorekodiwa', plain: 'Published findings with a recorded audit year' },
  'audits.year_count': { en: 'Findings', sw: 'Matokeo', plain: 'Findings' },
  'audits.unavailable': { en: 'Unavailable', sw: 'Haipatikani', plain: 'Unavailable' },
  'audits.reports_unavailable': { en: 'Reports read per year unavailable', sw: 'Idadi ya ripoti zilizosomwa kwa mwaka haipatikani', plain: 'Reports read per year unavailable' },
  'audits.coverage_note': { en: 'Coverage can differ between audit years. A higher findings count can reflect more reports being read.', sw: 'Wigo wa ripoti unaweza kutofautiana kati ya miaka ya ukaguzi. Idadi kubwa ya matokeo inaweza kutokana na ripoti nyingi zaidi kusomwa.', plain: 'The reports available can differ by year. More findings can come from reading more reports.' },
  'audits.year_scroll': { en: 'Audit year bars', sw: 'Nguzo za miaka ya ukaguzi', plain: 'Audit year bars' },
  'audits.years_loading': { en: 'Loading findings by audit year…', sw: 'Inapakia matokeo kwa mwaka wa ukaguzi…', plain: 'Loading findings by audit year…' },
  'audits.years_error': { en: 'Findings by audit year could not be loaded.', sw: 'Matokeo kwa mwaka wa ukaguzi hayakuweza kupakiwa.', plain: 'Findings by audit year could not be loaded.' },
  'audits.retry': { en: 'Try again', sw: 'Jaribu tena', plain: 'Try again' },
  'audits.years_empty': { en: 'No published findings with a recorded audit year are available.', sw: 'Hakuna matokeo yaliyochapishwa yenye mwaka wa ukaguzi uliorekodiwa yanayopatikana.', plain: 'No published findings with a recorded audit year are available.' },
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
  'audits.finding_source': { en: 'Source: report', sw: 'Chanzo: ripoti', plain: 'Source: report' },
  'audits.finding_amount': { en: 'Amount', sw: 'Kiasi', plain: 'Amount' },
  'audits.amount_not_stated': { en: 'Amount: not stated', sw: 'Kiasi: hakijatajwa', plain: 'Amount: not stated' },
  'audits.institution_not_identified': { en: 'Audited institution not identified', sw: 'Taasisi iliyokaguliwa haijatambuliwa', plain: 'Audited institution unknown' },
  'audits.severity_critical': { en: 'Critical', sw: 'Tatizo kubwa sana', plain: 'Critical' },
  'audits.severity_warning': { en: 'Warning', sw: 'Onyo', plain: 'Warning' },
  'audits.severity_info': { en: 'Information', sw: 'Taarifa', plain: 'Information' },
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

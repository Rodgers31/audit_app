import type { AuditorGuideStep } from '@/app/learn/auditor-general-guide/auditorGuideData';
import type { Translation } from '../messages';

export const AUDITOR_GUIDE_MESSAGES = {
  title: {
    en: 'What the Auditor-General does',
    sw: 'Kazi ya Mkaguzi Mkuu wa Hesabu za Serikali',
    plain: 'What the Auditor-General does',
  },
  metadataDescription: {
    en: 'Learn who audits Kenya’s public money, when the Auditor-General reports and who acts on the findings.',
    sw: 'Jifunze nani hukagua fedha za umma nchini Kenya, ripoti hutolewa lini na nani huzishughulikia.',
    plain: 'See who checks Kenya’s public money, when they report and who acts on the reports.',
  },
  progress: { en: 'Step {step} of {total}', sw: 'Hatua ya {step} kati ya {total}', plain: 'Step {step} of {total}' },
  article: { en: 'Read Article 229', sw: 'Soma Ibara ya 229', plain: 'Read Article 229' },
  previous: { en: 'Previous', sw: 'Iliyotangulia', plain: 'Previous' },
  next: { en: 'Next', sw: 'Inayofuata', plain: 'Next' },
  back: { en: 'Back to Learn', sw: 'Rudi kwenye kujifunza', plain: 'Back to Learn' },
} as const satisfies Record<string, Translation>;

type StepCopy = Record<'title' | 'description' | 'measure' | 'value' | 'source' | 'destination', Translation> & {
  period?: Translation;
};

export const AUDITOR_GUIDE_STEP_COPY: Record<AuditorGuideStep['key'], StepCopy> = {
  office: {
    title: { en: 'Who does the auditing?', sw: 'Nani hukagua fedha za umma?', plain: 'Who checks public money?' },
    description: {
      en: 'The President appoints the Auditor-General after the National Assembly approves. Article 251 applies to the term, and the Auditor-General cannot be appointed again.',
      sw: 'Rais humteua Mkaguzi Mkuu wa Hesabu za Serikali baada ya Bunge la Kitaifa kuidhinisha uteuzi. Ibara ya 251 inatumika kwa muhula huo, na Mkaguzi Mkuu hawezi kuteuliwa tena.',
      plain: 'The President appoints the Auditor-General with the National Assembly’s approval. Article 251 applies, and the same person can serve only one term.',
    },
    measure: { en: 'Term of office', sw: 'Muda wa kuhudumu', plain: 'Time in office' },
    value: { en: '{figure} years', sw: 'Miaka {figure}', plain: '{figure} years' },
    source: { en: 'Constitution of Kenya · Article 229(1) and (3)', sw: 'Katiba ya Kenya · Ibara ya 229(1) na (3)', plain: 'Constitution of Kenya · Article 229(1) and (3)' },
    destination: { en: 'See what a government audit is', sw: 'Jifunze maana ya ukaguzi wa serikali', plain: 'See what a government audit is' },
  },
  reporting: {
    title: { en: 'When must the Auditor-General report?', sw: 'Mkaguzi Mkuu anapaswa kutoa ripoti lini?', plain: 'When is the audit report due?' },
    description: {
      en: 'The Auditor-General must audit and report on each financial year. The work covers national and county government accounts, public debt and the other accounts listed in Article 229(4).',
      sw: 'Mkaguzi Mkuu lazima akague na kutoa ripoti kuhusu kila mwaka wa fedha. Ukaguzi unahusu hesabu za serikali ya kitaifa na za kaunti, deni la umma na hesabu nyingine zilizoorodheshwa katika Ibara ya 229(4).',
      plain: 'The Auditor-General checks and reports on each financial year. That includes national and county accounts, public debt and other accounts listed in Article 229(4).',
    },
    measure: { en: 'Deadline after each financial year ends', sw: 'Makataa baada ya kila mwaka wa fedha kuisha', plain: 'Time to report after the financial year ends' },
    value: { en: '{figure} months', sw: 'Miezi {figure}', plain: '{figure} months' },
    source: { en: 'Constitution of Kenya · Article 229(4)', sw: 'Katiba ya Kenya · Ibara ya 229(4)', plain: 'Constitution of Kenya · Article 229(4)' },
    destination: { en: 'See where AuditGava gets its reports', sw: 'Angalia vyanzo vya ripoti za AuditGava', plain: 'See where AuditGava gets its reports' },
  },
  opinion: {
    title: { en: 'What does an audit report tell us?', sw: 'Ripoti ya ukaguzi inatuambia nini?', plain: 'What can I learn from an audit report?' },
    description: {
      en: 'Audit reports assess whether public money was used lawfully and effectively. A qualified opinion flags a significant problem in part of the financial statements or a significant gap in the evidence. An allegation about someone’s conduct is a separate claim.',
      sw: 'Ripoti za ukaguzi huangalia kama fedha za umma zilitumika kwa mujibu wa sheria na kwa ufanisi. Maoni yenye masharti yanaonyesha tatizo muhimu katika sehemu ya taarifa za fedha au pengo muhimu katika ushahidi wa ukaguzi. Tuhuma kuhusu mwenendo wa mtu ni dai tofauti.',
      plain: 'The report checks if public money was used legally and well. A qualified opinion flags a serious problem in part of the accounts or an important gap in the evidence needed to check them. A claim that a person did something wrong is a separate matter.',
    },
    measure: {
      en: 'County executive financial statements with a qualified opinion',
      sw: 'Taarifa za fedha za serikali tendaji za kaunti zilizopata maoni yenye masharti',
      plain: 'County executive accounts with a qualified opinion',
    },
    value: { en: '{figure} of {total}', sw: '{figure} kati ya {total}', plain: '{figure} out of {total}' },
    period: {
      en: 'Financial year ended 30 June 2025',
      sw: 'Mwaka wa fedha ulioisha tarehe 30 Juni 2025',
      plain: 'For the year that ended on 30 June 2025',
    },
    source: {
      en: 'Office of the Auditor-General · Summary Report on County Governments (PDF), table 8, p. 21',
      sw: 'Ofisi ya Mkaguzi Mkuu wa Hesabu za Serikali · Muhtasari wa Serikali za Kaunti (PDF), jedwali la 8, uk. 21',
      plain: 'Office of the Auditor-General · Summary Report on County Governments (PDF), table 8, page 21',
    },
    destination: { en: 'Read audit findings', sw: 'Soma matokeo ya ukaguzi', plain: 'Read audit findings' },
  },
  action: {
    title: { en: 'Who acts on the report?', sw: 'Nani huchukua hatua baada ya kupokea ripoti?', plain: 'Who acts on the audit report?' },
    description: {
      en: 'The Auditor-General submits reports to Parliament or the relevant county assembly. The institution that receives the report must debate and consider it and take appropriate action.',
      sw: 'Mkaguzi Mkuu huwasilisha ripoti kwa Bunge au bunge la kaunti husika. Taasisi inayopokea ripoti lazima iijadili, iizingatie na ichukue hatua inayofaa.',
      plain: 'The Auditor-General sends the report to Parliament or the relevant county assembly. The body that gets it must discuss it and take appropriate action.',
    },
    measure: { en: 'Deadline after the report is received', sw: 'Makataa baada ya ripoti kupokewa', plain: 'Time to act after receiving the report' },
    value: { en: '{figure} months', sw: 'Miezi {figure}', plain: '{figure} months' },
    source: { en: 'Constitution of Kenya · Article 229(7) and (8)', sw: 'Katiba ya Kenya · Ibara ya 229(7) na (8)', plain: 'Constitution of Kenya · Article 229(7) and (8)' },
    destination: { en: 'Open Nairobi’s audit tab', sw: 'Fungua sehemu ya ukaguzi ya Nairobi', plain: 'Open Nairobi’s audit tab' },
  },
};

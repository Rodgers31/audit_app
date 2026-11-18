import type { Translation } from '../messages';

export const COUNTY_COMPARE_MESSAGES = {
  placeholder: {
    en: 'Search county',
    sw: 'Tafuta kaunti',
    plain: 'Find a county',
  },
  add: {
    en: 'Add a county',
    sw: 'Ongeza kaunti',
    plain: 'Add a county',
  },
  suggestions: {
    en: 'Suggested pairs',
    sw: 'Jozi za kaunti zinazopendekezwa',
    plain: 'Try these counties',
  },
  pair: {
    en: '{first} vs {second}',
    sw: '{first} na {second}',
    plain: '{first} and {second}',
  },
  clear: {
    en: 'Clear county',
    sw: 'Ondoa chaguo',
    plain: 'Clear this county',
  },
  noMatches: {
    en: 'No counties match.',
    sw: 'Hakuna kaunti zinazolingana.',
    plain: 'No counties found.',
  },
  readingNote: {
    en: 'Tap or select a county name to open its page.',
    sw: 'Gusa au chagua jina la kaunti ili kufungua ukurasa wake.',
    plain: 'Tap or select a county name to open its page.',
  },
  subtitle: {
    en: 'Line up counties side by side to compare budgets, spending, debt and audit findings.',
    sw: 'Linganisha bajeti, matumizi, deni na matokeo ya ukaguzi ya kaunti mbili au tatu.',
    plain: 'Compare what counties budgeted, what they spent, their debt and audit findings.',
  },
  table: { en: 'County comparison', sw: 'Ulinganisho wa kaunti', plain: 'County comparison' },
  measure: { en: 'Measure', sw: 'Kipimo', plain: 'Measure' },
  budget: { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  spentRate: { en: 'Spent (%)', sw: 'Iliyotumika (%)', plain: 'Spent (%)' },
  findings: { en: 'Published findings', sw: 'Matokeo yaliyochapishwa', plain: 'Published findings' },
  seriousFindings: { en: 'Serious findings', sw: 'Matokeo mazito', plain: 'Serious findings' },
  missing: { en: 'Unavailable', sw: 'Haipatikani', plain: 'Unavailable' },
  findingsScope: {
    en: 'Published findings count records from the Office of the Auditor-General in the available audits. A total for serious findings is unavailable.',
    sw: 'Jumla ya matokeo yaliyochapishwa inahesabu rekodi za Ofisi ya Mkaguzi Mkuu wa Hesabu katika ripoti za ukaguzi zinazopatikana. Jumla ya matokeo mazito haipatikani.',
    plain: 'Published findings counts what we have from the Auditor-General. A count of serious findings is unavailable.',
  },
  highest: { en: 'Highest', sw: 'Ya juu zaidi', plain: 'Highest' },
  lowest: { en: 'Lowest', sw: 'Ya chini zaidi', plain: 'Lowest' },
  moreMeasures: { en: 'More measures', sw: 'Vipimo zaidi', plain: 'More figures' },
  debtTitle: { en: 'Debt and pending bills', sw: 'Deni na bili ambazo hazijalipwa', plain: 'Debt and unpaid bills' },
  debtContext: {
    en: 'County borrowing covers selected eligible instruments. Pending bills are separate trade payables as reported by county treasuries to the Controller of Budget.',
    sw: 'Mikopo ya kaunti inahusu mikataba maalum inayokidhi masharti. Bili ambazo hazijalipwa ni madeni tofauti kwa wasambazaji ambayo hazina za kaunti ziliripoti kwa Mdhibiti wa Bajeti.',
    plain: 'The debt row covers borrowing from specific eligible contracts. Unpaid bills are what counties said they owed suppliers and reported to the Controller of Budget.',
  },
  debtDate: {
    en: 'Borrowing balance at {date}',
    sw: 'Salio la mikopo tarehe {date}',
    plain: 'Borrowing balance on {date}',
  },
  share: { en: 'Share this comparison', sw: 'Shiriki ulinganisho huu', plain: 'Share this comparison' },
  link: { en: 'Comparison link', sw: 'Kiungo cha ulinganisho', plain: 'Comparison link' },
  copy: { en: 'Copy link', sw: 'Nakili kiungo', plain: 'Copy link' },
  copied: { en: 'Link copied.', sw: 'Kiungo kimenakiliwa.', plain: 'Link copied.' },
  copyManually: {
    en: 'Select and copy the link above.',
    sw: 'Chagua kisha unakili kiungo kilicho hapo juu.',
    plain: 'Select and copy the link above.',
  },
} as const satisfies Record<string, Translation>;

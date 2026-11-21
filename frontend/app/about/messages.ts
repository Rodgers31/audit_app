import type { Translation } from '@/lib/i18n/messages';

export const ABOUT_MESSAGES = {
  title: { en: 'About AuditGava', sw: 'Kuhusu AuditGava', plain: 'About AuditGava' },
  intro: {
    en: 'AuditGava operates independently of government. We trace Kenya’s public money to the official record and publish data on budgets, spending, debt and audit findings.',
    sw: 'AuditGava inafanya kazi kwa uhuru bila kusimamiwa na serikali. Tunafuatilia fedha za umma nchini Kenya kupitia rekodi rasmi na kuchapisha data kuhusu bajeti, matumizi, madeni na matokeo ya ukaguzi.',
    plain: 'AuditGava operates independently of government. We use official records to show Kenya’s budgets, spending, debt and what auditors found.',
  },
  practices: { en: 'How we work', sw: 'Jinsi tunavyofanya kazi', plain: 'How we work' },
  figures: {
    en: 'Figures link to their sources',
    sw: 'Takwimu zina viungo vya vyanzo vyake',
    plain: 'See where figures come from',
  },
  figuresDetail: {
    en: 'Source links show the report, table or page behind a figure when those details are available.',
    sw: 'Viungo vya vyanzo vinaonyesha ripoti, jedwali au ukurasa wenye takwimu zinapopatikana.',
    plain: 'A source link can show you the report, table or page a figure came from.',
  },
  findings: {
    en: 'Findings in the Auditor-General’s words',
    sw: 'Matokeo ya ukaguzi kwa maneno ya Mkaguzi Mkuu wa Hesabu za Serikali',
    plain: 'Read what the Auditor-General found',
  },
  findingsDetail: {
    en: 'We quote audit findings and link to the official report so you can read them in context.',
    sw: 'Tunanukuu matokeo ya ukaguzi na kutoa kiungo cha ripoti rasmi ili uweze kusoma maelezo yote.',
    plain: 'We show what the report says and link to it so you can read the finding for yourself.',
  },
  modelled: {
    en: 'Modelled figures say so',
    sw: 'Takwimu zilizokadiriwa zina alama',
    plain: 'Estimates have a label',
  },
  modelledDetail: {
    en: 'Look for the “modelled” label on estimates such as some county budget breakdowns.',
    sw: 'Tafuta alama ya “imekadiriwa” kwenye makadirio kama vile baadhi ya migawanyo ya bajeti za kaunti.',
    plain: 'Some figures, such as parts of county budgets, are estimates. Look for the “modelled” label.',
  },
  sources: { en: 'Sources', sw: 'Vyanzo', plain: 'Sources' },
  cbk: { en: 'Central Bank of Kenya', sw: 'Benki Kuu ya Kenya', plain: 'Central Bank of Kenya' },
  cbkReports: { en: 'Statistical bulletins and the bond register', sw: 'Majarida ya takwimu na rejista ya hatifungani', plain: 'Statistical bulletins and the list of government bonds' },
  treasury: { en: 'National Treasury', sw: 'Hazina ya Taifa', plain: 'National Treasury' },
  treasuryReports: { en: 'Budget documents and public debt records', sw: 'Nyaraka za bajeti na rekodi za deni la umma', plain: 'Budget documents and public debt records' },
  oag: { en: 'Office of the Auditor-General', sw: 'Ofisi ya Mkaguzi Mkuu wa Hesabu za Serikali', plain: 'Office of the Auditor-General' },
  oagReports: { en: 'National and county audit reports', sw: 'Ripoti za ukaguzi wa serikali ya kitaifa na kaunti', plain: 'National and county audit reports' },
  cob: { en: 'Controller of Budget', sw: 'Mdhibiti wa Bajeti', plain: 'Controller of Budget' },
  cobReports: { en: 'Budget implementation reviews', sw: 'Ripoti za mapitio ya utekelezaji wa bajeti', plain: 'Reports on how budgets were spent' },
  viewSources: { en: 'View all sources', sw: 'Tazama vyanzo vyote', plain: 'View all sources' },
  contact: { en: 'Contact', sw: 'Mawasiliano', plain: 'Contact' },
  contactDetail: {
    en: 'To report an error or reply to a finding, email the page link and the details.',
    sw: 'Ili kuripoti kosa au kujibu hoja ya ukaguzi, tuma kiungo cha ukurasa na maelezo kwa barua pepe.',
    plain: 'If you spot an error or want to reply to a finding, email us the page link and explain what you want us to know.',
  },
  name: {
    en: 'Gava is Kenyan Kiswahili slang for government.',
    sw: 'Gava ni neno la mtaani nchini Kenya linalomaanisha serikali.',
    plain: 'In Kenya, people use “Gava” as an informal word for government.',
  },
  policies: { en: 'About policies', sw: 'Sera za AuditGava', plain: 'Privacy and terms' },
  privacy: { en: 'Privacy policy', sw: 'Sera ya faragha', plain: 'Privacy policy' },
  terms: { en: 'Terms of use', sw: 'Masharti ya matumizi', plain: 'Terms of use' },
} satisfies Record<string, Translation>;

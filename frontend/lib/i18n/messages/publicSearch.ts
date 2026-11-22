export const PUBLIC_SEARCH_MESSAGES = {
  label: { en: 'Search AuditGava', sw: 'Tafuta kwenye AuditGava', plain: 'Search AuditGava' },
  close: { en: 'Close search', sw: 'Funga utafutaji', plain: 'Close search' },
  placeholder: {
    en: 'Search counties, findings, terms',
    sw: 'Tafuta kaunti, matokeo ya ukaguzi au istilahi',
    plain: 'Search counties, audit findings, terms',
  },
  help: {
    en: 'Search counties, audit findings, Constitution articles, glossary terms and lenders.',
    sw: 'Tafuta kaunti, matokeo ya ukaguzi, ibara za Katiba, istilahi na wakopeshaji.',
    plain: 'Look up a county, an audit finding, a Constitution article, a glossary term or a lender.',
  },
  clear: { en: 'Clear search', sw: 'Futa utafutaji', plain: 'Clear search' },
  counties: { en: 'Counties', sw: 'Kaunti', plain: 'Counties' },
  findings: { en: 'Audit findings', sw: 'Matokeo ya ukaguzi', plain: 'Audit findings' },
  articles: { en: 'Constitution articles', sw: 'Ibara za Katiba', plain: 'Constitution articles' },
  glossary: { en: 'Glossary terms', sw: 'Istilahi', plain: 'Glossary terms' },
  lenders: { en: 'Lenders', sw: 'Wakopeshaji', plain: 'Lenders' },
  openReportPage: {
    en: 'Open cited report page',
    sw: 'Fungua ukurasa uliotajwa katika ripoti',
    plain: 'Read the finding on the cited report page',
  },
  openLoanRegister: {
    en: 'Open loan register',
    sw: 'Fungua rejesta ya mikopo',
    plain: 'View this lender in the loan register',
  },
  findingsCoverage: {
    en: 'Audit search checks up to {limit} of the newest published findings and shows matches with cited report pages.',
    sw: 'Utafutaji wa ukaguzi hukagua hadi matokeo {limit} yaliyochapishwa karibuni zaidi na kuonyesha yanayolingana yenye kurasa zilizotajwa katika ripoti.',
    plain: 'We search up to {limit} of the newest published audit findings. A match must have a link to its report page.',
  },
  article: { en: 'Article {number}', sw: 'Ibara ya {number}', plain: 'Article {number}' },
  short: {
    en: 'Enter three or more characters to search all groups, or enter an article number.',
    sw: 'Andika angalau herufi tatu ili kutafuta katika makundi yote, au andika nambari ya ibara.',
    plain: 'Type at least three characters to look in all groups, or type an article number.',
  },
  loading: {
    en: 'Searching…',
    sw: 'Inatafuta…',
    plain: 'Searching…',
  },
  empty: {
    en: 'No matches in the sources searched.',
    sw: 'Hakuna matokeo yanayolingana katika vyanzo vilivyotafutwa.',
    plain: 'We found no matches in the sources we searched.',
  },
  one: { en: 'One result shown.', sw: 'Tokeo moja limeonyeshwa.', plain: 'One result shown.' },
  many: { en: '{count} results shown.', sw: 'Matokeo {count} yameonyeshwa.', plain: '{count} results shown.' },
  partial: {
    en: 'Some Constitution article text is unavailable.',
    sw: 'Maandishi ya baadhi ya ibara za Katiba hayapatikani.',
    plain: 'We could only search some Constitution articles.',
  },
  unavailable: {
    en: 'Constitution article search is unavailable. Try an article number.',
    sw: 'Utafutaji wa ibara za Katiba haupatikani. Jaribu nambari ya ibara.',
    plain: 'We could not search the Constitution text. Try an article number.',
  },
  findingsUnavailable: {
    en: 'Audit findings search is unavailable.',
    sw: 'Utafutaji wa matokeo ya ukaguzi haupatikani.',
    plain: 'We could not search audit findings.',
  },
  lendersUnavailable: {
    en: 'Lender search is unavailable.',
    sw: 'Utafutaji wa wakopeshaji haupatikani.',
    plain: 'We could not search lenders.',
  },
} as const;

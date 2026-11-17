import type { Translation } from '../messages';

export const HOME_TOPICS_MESSAGES = {
  'home.topics.hero_title': {
    en: 'Where does Kenya’s money go?',
    sw: 'Pesa za Kenya zinaenda wapi?',
    plain: 'Where does Kenya’s money go?',
  },
  'home.topics.hero_description': {
    en: 'Budgets, debt and audits from official records.',
    sw: 'Bajeti, madeni na ukaguzi kutoka rekodi rasmi.',
    plain: 'Official records show how Kenya spends money, what it owes and what auditors found.',
  },
  'home.topics.heading': {
    en: 'What do you want to know?',
    sw: 'Unataka kujua nini?',
    plain: 'What do you want to know?',
  },
  'home.topics.debt': {
    en: 'How much does Kenya owe?',
    sw: 'Kenya inadaiwa kiasi gani?',
    plain: 'How much money does Kenya owe?',
  },
  'home.topics.budget': {
    en: 'Where do my taxes go?',
    sw: 'Kodi ninazolipa zinaenda wapi?',
    plain: 'Where do my taxes go?',
  },
  'home.topics.counties': {
    en: 'How is my county doing?',
    sw: 'Kaunti yangu inaendeleaje?',
    plain: 'How is my county doing?',
  },
  'home.topics.audits': {
    en: 'What did the Auditor-General find?',
    sw: 'Mkaguzi Mkuu wa Hesabu za Serikali aligundua nini?',
    plain: 'What did the Auditor-General find?',
  },
  'home.topics.publishers': {
    en: 'Data from the Central Bank, Treasury, Auditor-General and Controller of Budget.',
    sw: 'Takwimu kutoka Benki Kuu ya Kenya, Hazina ya Taifa, Mkaguzi Mkuu wa Hesabu za Serikali na Mdhibiti wa Bajeti.',
    plain: 'Data from the Central Bank, Treasury, Auditor-General and Controller of Budget.',
  },
  'home.county_search.label': {
    en: 'Find your county',
    sw: 'Tafuta kaunti yako',
    plain: 'Find your county',
  },
  'home.county_search.placeholder': {
    en: 'Type your county, e.g. Kisumu',
    sw: 'Andika jina la kaunti, k.m. Kisumu',
    plain: 'Type your county name, for example Kisumu',
  },
  'home.county_search.clear': {
    en: 'Clear county search',
    sw: 'Futa utafutaji wa kaunti',
    plain: 'Clear county search',
  },
  'home.county_search.no_matches': {
    en: 'No counties found.',
    sw: 'Hakuna kaunti iliyopatikana.',
    plain: 'No counties match that name.',
  },
} satisfies Record<string, Translation>;

/**
 * Hand-curated list of the key county officials users most often want
 * when a county shows up in the news: Governor, Deputy Governor, CEC
 * for Finance, and County Assembly Speaker. Sourced from each county's
 * official website / IEBC filings at the time of the 2022 general
 * election cycle (term running through 2027).
 *
 * Keyed by 3-digit county code. Coverage is intentionally tiered:
 *   • Governor & Deputy Governor: all 47 counties (elected pair —
 *     stable and publicly verifiable).
 *   • CEC Finance & Assembly Speaker: only where verified from the
 *     county's own website. These roles rotate more often and vary
 *     by source, so we prefer silence to misattribution. The UI
 *     renders "Not yet published" placeholders for the missing ones
 *     so this file can grow incrementally without breaking the page.
 */

export interface CountyOfficials {
  governor?: { name: string; party?: string; term_start?: string };
  deputy_governor?: { name: string };
  cec_finance?: { name: string; title?: string };
  assembly_speaker?: { name: string };
  /** Official county government website */
  website?: string;
}

export const COUNTY_OFFICIALS: Record<string, CountyOfficials> = {
  '001': {
    governor: { name: 'Johnson Sakaja', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Njoroge Muchiri' },
    cec_finance: { name: 'Charles Kerich', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'Kennedy Ng’ondi' },
    website: 'https://nairobi.go.ke',
  },
  '002': {
    governor: { name: 'Fatuma Achani', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Chirema Kombo' },
    website: 'https://kwalecountygov.com',
  },
  '003': {
    governor: { name: 'Gideon Mung’aro', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Flora Chibule' },
    website: 'https://www.kilifi.go.ke',
  },
  '004': {
    governor: { name: 'Dhadho Godhana', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Mahmoud Mohamed' },
    website: 'https://www.tanariver.go.ke',
  },
  '005': {
    governor: { name: 'Issa Timamy', party: 'Jubilee', term_start: '2022' },
    deputy_governor: { name: 'Raphael Munyua' },
    website: 'https://www.lamu.go.ke',
  },
  '006': {
    governor: { name: 'Andrew Mwadime', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Christine Kilalo' },
    website: 'https://www.taitataveta.go.ke',
  },
  '007': {
    governor: { name: 'Nathif Jama Adam', party: 'UDM', term_start: '2022' },
    deputy_governor: { name: 'Abdi Aden Dagane' },
    website: 'https://www.garissa.go.ke',
  },
  '008': {
    governor: { name: 'Ahmed Abdullahi', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Ahmed Muktar' },
    website: 'https://www.wajir.go.ke',
  },
  '009': {
    governor: { name: 'Mohamed Adan Khalif', party: 'PAA', term_start: '2022' },
    deputy_governor: { name: 'Ali Maalim Mohamed' },
    website: 'https://www.mandera.go.ke',
  },
  '010': {
    governor: { name: 'Mohamud Ali', party: 'Jubilee', term_start: '2022' },
    deputy_governor: { name: 'Solomon Riwe' },
    website: 'https://marsabit.go.ke',
  },
  '011': {
    governor: { name: 'Abdi Hassan Guyo', party: 'Jubilee', term_start: '2022' },
    deputy_governor: { name: 'James Lowasa' },
    website: 'https://isiolo.go.ke',
  },
  '012': {
    governor: { name: 'Kawira Mwangaza', party: 'Independent', term_start: '2022' },
    deputy_governor: { name: 'Isaac Mutuma' },
    website: 'https://meru.go.ke',
  },
  '013': {
    governor: { name: 'Muthomi Njuki', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Nyamu Mugambi' },
    website: 'https://tharakanithi.go.ke',
  },
  '014': {
    governor: { name: 'Cecily Mbarire', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Kinyua Njeru' },
    website: 'https://embu.go.ke',
  },
  '015': {
    governor: { name: 'Julius Malombe', party: 'WDM-K', term_start: '2022' },
    deputy_governor: { name: 'Wathe Nzau' },
    website: 'https://kitui.go.ke',
  },
  '016': {
    governor: { name: 'Wavinya Ndeti', party: 'WDM-K', term_start: '2022' },
    deputy_governor: { name: 'Francis Mwangangi' },
    website: 'https://machakosgovernment.com',
  },
  '017': {
    governor: { name: 'Mutula Kilonzo Jr', party: 'WDM-K', term_start: '2022' },
    deputy_governor: { name: 'Lucy Mulili' },
    website: 'https://makueni.go.ke',
  },
  '018': {
    governor: { name: 'Moses Kiarie Badilisha', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'John Kimemia' },
    website: 'https://nyandarua.go.ke',
  },
  '019': {
    governor: { name: 'Mutahi Kahiga', party: 'UDA', term_start: '2017' },
    deputy_governor: { name: 'David Kinyua' },
    website: 'https://nyeri.go.ke',
  },
  '020': {
    governor: { name: 'Anne Waiguru', party: 'UDA', term_start: '2017' },
    deputy_governor: { name: 'Peter Ndambiri' },
    website: 'https://kirinyaga.go.ke',
  },
  '021': {
    governor: { name: 'Irungu Kang’ata', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Stephen Munania' },
    website: 'https://muranga.go.ke',
  },
  '022': {
    governor: { name: 'Kimani Wamatangi', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Rosemary Njeri' },
    cec_finance: { name: 'Nancy Kirumba', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'Cecilia Mbugua' },
    website: 'https://kiambu.go.ke',
  },
  '023': {
    governor: { name: 'Jeremiah Lomorukai', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'John Erus Losiakou' },
    website: 'https://turkana.go.ke',
  },
  '024': {
    governor: { name: 'Simon Kachapin', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Robert Komol' },
    website: 'https://westpokot.go.ke',
  },
  '025': {
    governor: { name: 'Lati Lelelit', party: 'Jubilee', term_start: '2022' },
    deputy_governor: { name: 'Julius Leseeto' },
    website: 'https://samburu.go.ke',
  },
  '026': {
    governor: { name: 'George Natembeya', party: 'DAP-K', term_start: '2022' },
    deputy_governor: { name: 'Phylis Kaittany' },
    website: 'https://transnzoia.go.ke',
  },
  '027': {
    governor: { name: 'Jonathan Bii', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'John Barorot' },
    cec_finance: { name: 'Bernard Rop', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'David Kiplagat' },
    website: 'https://uasingishu.go.ke',
  },
  '028': {
    governor: { name: 'Wisley Rotich', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Grace Cheserek' },
    website: 'https://elgeyomarakwet.go.ke',
  },
  '029': {
    governor: { name: 'Stephen Sang', party: 'UDA', term_start: '2017' },
    deputy_governor: { name: 'Yulita Cheruiyot Mitei' },
    website: 'https://nandi.go.ke',
  },
  '030': {
    governor: { name: 'Benjamin Cheboi', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Jacob Chepkwony' },
    website: 'https://baringo.go.ke',
  },
  '031': {
    governor: { name: 'Joshua Irungu', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Reuben Kamuri' },
    website: 'https://laikipia.go.ke',
  },
  '032': {
    governor: { name: 'Susan Kihika', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'David Kones' },
    cec_finance: { name: 'Roselyn Mungai', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'Risper Soi' },
    website: 'https://nakuru.go.ke',
  },
  '033': {
    governor: { name: 'Patrick Ole Ntutu', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Tamalinye Koech' },
    website: 'https://narok.go.ke',
  },
  '034': {
    governor: { name: 'Joseph Ole Lenku', party: 'ODM', term_start: '2017' },
    deputy_governor: { name: 'Martin Moshisho' },
    website: 'https://kajiado.go.ke',
  },
  '035': {
    governor: { name: 'Erick Mutai', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Fred Kirui' },
    website: 'https://kericho.go.ke',
  },
  '036': {
    governor: { name: 'Hillary Barchok', party: 'UDA', term_start: '2020' },
    deputy_governor: { name: 'Shadrack Rotich' },
    website: 'https://bomet.go.ke',
  },
  '037': {
    governor: { name: 'Fernandes Barasa', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Ayub Savula' },
    website: 'https://kakamega.go.ke',
  },
  '038': {
    governor: { name: 'Wilber Ottichilo', party: 'ODM', term_start: '2017' },
    deputy_governor: { name: 'Patrick Saisi' },
    website: 'https://vihiga.go.ke',
  },
  '039': {
    governor: { name: 'Ken Lusaka', party: 'UDA', term_start: '2022' },
    deputy_governor: { name: 'Jennifer Mbatiany' },
    website: 'https://bungoma.go.ke',
  },
  '040': {
    governor: { name: 'Paul Otuoma', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Arthur Odera' },
    website: 'https://busia.go.ke',
  },
  '041': {
    governor: { name: 'James Orengo', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'William Oduol' },
    website: 'https://siaya.go.ke',
  },
  '042': {
    governor: { name: 'Anyang’ Nyong’o', party: 'ODM', term_start: '2017' },
    deputy_governor: { name: 'Mathews Owili' },
    cec_finance: { name: 'George Okong’o', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'Elisha Oraro' },
    website: 'https://kisumu.go.ke',
  },
  '043': {
    governor: { name: 'Gladys Wanga', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Oyugi Magwanga' },
    website: 'https://homabay.go.ke',
  },
  '044': {
    governor: { name: 'Ochillo Ayacko', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Joseph Mahero' },
    website: 'https://migori.go.ke',
  },
  '045': {
    governor: { name: 'Simba Arati', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Robert Monda' },
    website: 'https://kisii.go.ke',
  },
  '046': {
    governor: { name: 'Amos Nyaribo', party: 'UDA', term_start: '2020' },
    deputy_governor: { name: 'Emmanuel Okerio' },
    website: 'https://nyamira.go.ke',
  },
  '047': {
    governor: { name: 'Abdulswamad Shariff Nassir', party: 'ODM', term_start: '2022' },
    deputy_governor: { name: 'Francis Foleni' },
    cec_finance: { name: 'Mbarak Abdalla', title: 'CEC Finance & Economic Planning' },
    assembly_speaker: { name: 'Aharub Khatri' },
    website: 'https://mombasa.go.ke',
  },
};

export const ROLE_DESCRIPTIONS: Record<string, string> = {
  governor:
    'Chief executive of the county government. Elected directly by voters every five years.',
  deputy_governor:
    'Deputy to the Governor, elected on the same ticket. Steps in when the Governor is away or vacates office.',
  cec_finance:
    'County Executive Committee member for Finance — the county-level equivalent of a finance minister. Prepares the budget and oversees spending.',
  assembly_speaker:
    'Presides over the County Assembly (the legislative body). Elected by Assembly members.',
};

/** Returns officials for a county id (3-digit padded). Never throws — callers
 * can safely destructure even when the county has no entry. */
export function getCountyOfficials(countyId: string): CountyOfficials {
  const padded = countyId.padStart(3, '0');
  return COUNTY_OFFICIALS[padded] || {};
}

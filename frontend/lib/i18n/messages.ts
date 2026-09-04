/**
 * Translation dictionary.
 *
 * - `en`: Neutral, slightly formal English (default, used everywhere today)
 * - `sw`: Kiswahili — official Kenyan language, broadest reach
 * - `plain`: Simplified English for readers who don't work in finance —
 *   shorter words, no jargon. A wheelchair accessibility pattern applied
 *   to language: lower the bar and more people get in.
 *
 * Keys are dotted strings grouped by feature/page. Missing strings fall
 * back to English automatically (see LangProvider.t).
 *
 * Coverage target: the high-traffic pages are translated fully —
 * Dashboard, Counties list, County detail, Sectors, Compare. Other
 * pages keep English until a reader requests translation.
 */

export type Lang = 'en' | 'sw' | 'plain';

export interface Translation {
  en: string;
  sw: string;
  plain: string;
}

export const MESSAGES = {
  // ══════════════════════════════════════════════════
  // Language switcher + global
  // ══════════════════════════════════════════════════
  'lang.english': { en: 'English', sw: 'Kiingereza', plain: 'English' },
  'lang.swahili': { en: 'Kiswahili', sw: 'Kiswahili', plain: 'Swahili' },
  'lang.plain': { en: 'Plain English', sw: 'Kiingereza Rahisi', plain: 'Simple Words' },
  'lang.label': { en: 'Language', sw: 'Lugha', plain: 'Language' },

  // Nav items
  'nav.dashboard': { en: 'Dashboard', sw: 'Dashibodi', plain: 'Home' },
  'nav.debt': { en: 'National Debt', sw: 'Deni la Taifa', plain: 'Money Kenya Owes' },
  'nav.budget': { en: 'Budget & Spending', sw: 'Bajeti na Matumizi', plain: 'The Budget' },
  'nav.counties': { en: 'County Explorer', sw: 'Kaunti', plain: 'Counties' },
  'nav.transparency': { en: 'Follow the Money', sw: 'Fuatilia Pesa', plain: 'Where Money Goes' },
  'nav.learn': { en: 'Learn', sw: 'Jifunze', plain: 'Learn' },
  'nav.sign_in': { en: 'Sign In', sw: 'Ingia', plain: 'Sign In' },
  'nav.sign_out': { en: 'Sign Out', sw: 'Toka', plain: 'Sign Out' },
  'nav.my_account': { en: 'My Account', sw: 'Akaunti Yangu', plain: 'My Profile' },
  'nav.account_settings': { en: 'Account & Settings', sw: 'Akaunti na Mipangilio', plain: 'Account Settings' },
  'nav.watchlist': { en: 'My Watchlist', sw: 'Orodha Yangu', plain: 'My Watchlist' },
  'nav.alerts': { en: 'Alerts', sw: 'Arifa', plain: 'Alerts' },
  'nav.user_menu': { en: 'User menu', sw: 'Menyu ya mtumiaji', plain: 'User menu' },
  'nav.mobile_menu': { en: 'Mobile navigation', sw: 'Urambazaji wa simu', plain: 'Mobile menu' },
  'nav.open_menu': { en: 'Open navigation menu', sw: 'Fungua menyu', plain: 'Open menu' },
  'nav.close_menu': { en: 'Close navigation menu', sw: 'Funga menyu', plain: 'Close menu' },
  'nav.kenya_public_money': { en: 'Kenya Public Money', sw: 'Pesa za Umma Kenya', plain: 'Kenya’s Money' },
  'nav.republic_kenya': { en: 'Republic of Kenya', sw: 'Jamhuri ya Kenya', plain: 'Republic of Kenya' },
  'nav.citizen': { en: 'Citizen', sw: 'Raia', plain: 'Citizen' },
  'nav.register': { en: 'Sign In / Register', sw: 'Ingia / Jisajili', plain: 'Sign In / Create Account' },

  // Common small labels (reused across pages)
  'common.loading': { en: 'Loading…', sw: 'Inapakia…', plain: 'Loading…' },
  'common.error': { en: 'Something went wrong', sw: 'Hitilafu imetokea', plain: 'Something went wrong' },
  'common.refresh': { en: 'Please refresh', sw: 'Tafadhali onyesha upya', plain: 'Please reload' },
  'common.learn_more': { en: 'Learn more', sw: 'Jifunze zaidi', plain: 'Tell me more' },
  'common.home': { en: 'Home', sw: 'Nyumbani', plain: 'Home' },
  'common.back': { en: 'Back', sw: 'Rudi', plain: 'Back' },
  'common.all_counties': { en: 'All counties', sw: 'Kaunti zote', plain: 'All counties' },
  'common.county': { en: 'County', sw: 'Kaunti', plain: 'County' },
  'common.counties': { en: 'counties', sw: 'kaunti', plain: 'counties' },
  'common.total': { en: 'Total', sw: 'Jumla', plain: 'Total' },
  'common.allocated': { en: 'Allocated', sw: 'Iliyotengwa', plain: 'Planned' },
  'common.spent': { en: 'Spent', sw: 'Iliyotumika', plain: 'Spent' },
  'common.utilization': { en: 'Utilization', sw: 'Matumizi', plain: 'How much was spent' },
  'common.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'common.debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'common.revenue': { en: 'Revenue', sw: 'Mapato', plain: 'Revenue' },
  'common.population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },
  'common.case': { en: 'case', sw: 'kesi', plain: 'case' },
  'common.cases': { en: 'cases', sw: 'kesi', plain: 'cases' },
  'common.metric': { en: 'Metric', sw: 'Kigezo', plain: 'What we measure' },
  'common.of': { en: 'of', sw: 'ya', plain: 'of' },

  // ══════════════════════════════════════════════════
  // Home / Dashboard
  // ══════════════════════════════════════════════════
  'home.hero.eyebrow': { en: 'Kenya Public Money', sw: 'Pesa za Umma Kenya', plain: 'Kenya’s Money' },
  'home.hero.title': {
    en: 'Kenya Public Money Tracker',
    sw: 'Kifuatilia Pesa za Umma Kenya',
    plain: 'See where Kenya’s money goes',
  },
  'home.hero.subtitle': {
    en: 'Where your taxes go — updated nightly from official sources',
    sw: 'Pesa zako za kodi zinakoenda — husasishwa kila usiku kutoka vyanzo rasmi',
    plain: 'See where your tax money goes — updated every night from official records',
  },

  // Hero summary strip
  'home.hero.total_debt_as_of': { en: 'Total Debt as of', sw: 'Jumla ya Deni kufikia', plain: 'Total money owed as of' },
  'home.hero.total_debt': { en: 'Total public debt', sw: 'Jumla ya deni la umma', plain: 'Total money the government owes' },
  'home.hero.risk_level': { en: 'Risk Level', sw: 'Kiwango cha Hatari', plain: 'How risky' },
  'home.hero.risk_high': { en: 'High Risk', sw: 'Hatari Kubwa', plain: 'High Risk' },
  'home.hero.risk_moderate': { en: 'Moderate Risk', sw: 'Hatari ya Wastani', plain: 'Medium Risk' },
  'home.hero.risk_low': { en: 'Low Risk', sw: 'Hatari Ndogo', plain: 'Low Risk' },
  'home.hero.risk_suffix': { en: 'Risk', sw: 'Hatari', plain: 'Risk' },
  'home.hero.risk_unassessed': { en: 'Risk not assessed', sw: 'Hatari haijatathminiwa', plain: 'Risk not rated yet' },
  'home.hero.risk_unassessed_value': { en: 'Not assessed', sw: 'Haijatathminiwa', plain: 'Not rated yet' },

  // KenyanGovCard
  'home.govcard.title': { en: 'Kenyan Government', sw: 'Serikali ya Kenya', plain: 'Kenya Government' },
  'home.govcard.fiscal_snapshot': { en: 'Fiscal Snapshot', sw: 'Muhtasari wa Fedha', plain: 'Money Summary' },
  'home.govcard.fiscal_health': { en: 'Fiscal Health', sw: 'Afya ya Fedha', plain: 'Money Health' },
  'home.govcard.under_strain': { en: 'Under Strain', sw: 'Chini ya Shinikizo', plain: 'Stressed' },
  'home.govcard.watch_list': { en: 'Watch List', sw: 'Orodha ya Kutazama', plain: 'Watch Closely' },
  'home.govcard.stable': { en: 'Stable', sw: 'Thabiti', plain: 'Stable' },
  'home.govcard.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'home.govcard.revenue': { en: 'Revenue', sw: 'Mapato', plain: 'Money In' },
  'home.govcard.revenue_sub': { en: 'Tax + non-tax', sw: 'Kodi + zisizo-kodi', plain: 'From taxes and other sources' },
  'home.govcard.borrowed': { en: 'Borrowed', sw: 'Iliyokopwa', plain: 'Borrowed' },
  'home.govcard.borrowed_sub_pct': { en: '% of budget', sw: '% ya bajeti', plain: '% of budget' },
  'home.govcard.debt_service': { en: 'Debt Service', sw: 'Huduma ya Deni', plain: 'Debt Payments' },
  'home.govcard.debt_service_sub': { en: 'Interest + principal', sw: 'Riba + mkopo mkuu', plain: 'Interest + loan payments' },
  'home.govcard.debt_ceiling': { en: 'Debt-to-GDP', sw: 'Deni kwa Pato la Taifa', plain: 'Debt vs Economy' },
  'home.govcard.ceiling_usage': { en: 'Usage', sw: 'Matumizi', plain: 'Used' },
  'home.govcard.ceiling_over': { en: 'Over the ceiling', sw: 'Juu ya kikomo', plain: 'Over the limit' },
  'home.govcard.view_full': { en: 'View full debt analysis', sw: 'Tazama uchambuzi kamili wa deni', plain: 'See full debt page' },
  'home.govcard.explore_debt': { en: 'Explore National Debt', sw: 'Chunguza Deni la Taifa', plain: 'See the debt page' },
  'home.govcard.where_money_goes': { en: 'Where the Money Goes', sw: 'Pesa Zinakoenda', plain: 'Where the Money Goes' },
  'home.govcard.seg_recurrent': { en: 'Recurrent', sw: 'Ya Kawaida', plain: 'Day-to-day' },
  'home.govcard.seg_debt_service': { en: 'Debt Service', sw: 'Huduma ya Deni', plain: 'Debt Payments' },
  'home.govcard.seg_development': { en: 'Development', sw: 'Maendeleo', plain: 'Projects' },
  'home.govcard.seg_counties': { en: 'Counties', sw: 'Kaunti', plain: 'Counties' },
  'home.govcard.seg_other': { en: 'Other', sw: 'Nyingine', plain: 'Other' },
  'home.govcard.ceiling_breached': { en: 'Above the 55%-of-GDP anchor on a nominal basis', sw: 'Juu ya nanga ya 55% ya Pato la Taifa kwa msingi wa kawaida', plain: 'Above the 55% safe limit, measured the simple way' },
  // The anchor is set in PRESENT-VALUE terms; the ratio charted against it is
  // nominal. Present value is lower than nominal for a portfolio with
  // concessional external debt, so a nominal reading overstates the breach.
  // /debt already carried this caveat; the homepage did not (audit F3).
  'home.govcard.anchor_caption': {
    en: 'PFM Act 2023 anchor: 55% of GDP measured in PRESENT-VALUE terms. The ratio shown is nominal, so it is not a like-for-like comparison. Former KES 10T ceiling repealed.',
    sw: 'Nanga ya Sheria ya PFM 2023: 55% ya Pato la Taifa kwa THAMANI YA SASA. Uwiano ulioonyeshwa ni wa kawaida (nominal), hivyo si ulinganisho wa moja kwa moja. Kikomo cha awali cha KES trilioni 10 kilifutwa.',
    plain: 'The safe limit is 55% of the economy, but it is measured a different way from the number shown here, so the two do not compare exactly. The old KES 10 trillion limit was scrapped.',
  },
  'home.govcard.stat_budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'home.govcard.stat_revenue': { en: 'Revenue', sw: 'Mapato', plain: 'Money In' },
  'home.govcard.stat_borrowed': { en: 'Borrowed', sw: 'Iliyokopwa', plain: 'Borrowed' },
  'home.govcard.stat_debt_service': { en: 'Debt Service', sw: 'Huduma ya Deni', plain: 'Debt Payments' },
  'home.govcard.tax_nontax': { en: 'Tax + non-tax', sw: 'Kodi + zisizo-kodi', plain: 'Taxes + other' },
  'home.govcard.pct_of_budget': { en: '{pct}% of budget', sw: '{pct}% ya bajeti', plain: '{pct}% of budget' },
  'home.govcard.cents_per_kes': { en: '{cents}¢/KES', sw: '{cents}¢/KES', plain: '{cents}¢ per KES' },
  'home.govcard.usage': { en: 'Usage', sw: 'Matumizi', plain: 'Used' },

  // Summary strip / NationalDebtCard
  'home.debt.title': { en: 'Kenya’s National Debt', sw: 'Deni la Taifa la Kenya', plain: 'What Kenya Owes' },
  'home.debt.subtitle': { en: 'Over time', sw: 'Kadri wakati unavyopita', plain: 'Over the years' },
  'home.debt.external': { en: 'External', sw: 'Nje', plain: 'Borrowed from abroad' },
  'home.debt.domestic': { en: 'Domestic', sw: 'Ndani', plain: 'Borrowed at home' },
  'home.debt.to_gdp': { en: 'Debt-to-GDP', sw: 'Deni kulingana na GDP', plain: 'Debt vs. economy' },
  'home.debt.per_citizen': { en: 'Per citizen', sw: 'Kwa kila raia', plain: 'Per person' },
  'home.debt.loading': { en: 'Loading debt timeline…', sw: 'Inapakia ratiba ya deni…', plain: 'Loading debt numbers…' },
  'home.debt.explore_full': { en: 'Explore full debt page', sw: 'Chunguza ukurasa kamili wa deni', plain: 'See the full debt page' },
  'home.debt.source_note': {
    en: '{range} · Source: Central Bank of Kenya & National Treasury',
    sw: '{range} · Chanzo: Benki Kuu ya Kenya & Hazina ya Taifa',
    plain: '{range} · From Central Bank and National Treasury',
  },
  'home.debt.total_public': { en: 'Total Public Debt', sw: 'Deni Jumla la Umma', plain: 'Total Kenya Owes' },
  'home.debt.external_label': { en: 'External Debt', sw: 'Deni la Nje', plain: 'Money owed abroad' },
  'home.debt.domestic_label': { en: 'Domestic Debt', sw: 'Deni la Ndani', plain: 'Money owed at home' },
  // The multiple is computed on the CBK debt timeline, while the headline
  // value beside it is the instrument-register sum. They are different series
  // and their ratio is not the headline's growth, so the label names the
  // series rather than implying the number above it grew by this much.
  'home.debt.growth_sub': {
    en: 'CBK timeline: {x}× since {year}',
    sw: 'Ratiba ya CBK: mara {x} tangu {year}',
    plain: 'On the CBK series: {x}× bigger than in {year}',
  },
  // Shown instead of a year-on-year comparison when the displayed ratio is the
  // IMF general-government figure: the timeline's own ratio is central
  // government over World Bank GDP, so the two are not points on one series.
  'home.debt.gdp_basis_imf': {
    en: 'IMF general government basis',
    sw: 'Msingi wa serikali kwa ujumla (IMF)',
    plain: 'Measured the IMF way (all of government)',
  },
  'home.debt.from_year_sub': { en: 'From {pct}% in {year}', sw: 'Kutoka {pct}% mwaka {year}', plain: 'From {pct}% in {year}' },
  'home.debt.pct_of_total': { en: '{pct}% of total', sw: '{pct}% ya jumla', plain: '{pct}% of total' },
  'home.debt.no_timeline': { en: 'No timeline data available', sw: 'Hakuna data ya ratiba', plain: 'No history available' },
  'home.debt.legend_domestic': { en: 'Domestic Debt', sw: 'Deni la Ndani', plain: 'At home' },
  'home.debt.legend_external': { en: 'External Debt', sw: 'Deni la Nje', plain: 'Abroad' },
  'home.debt.legend_gdp': { en: 'Debt-to-GDP %', sw: 'Deni-kwa-GDP %', plain: 'Debt vs. economy %' },
  'home.debt.tooltip_total': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },
  'home.debt.tooltip_gdp': { en: 'Debt-to-GDP', sw: 'Deni-kwa-GDP', plain: 'Debt vs. economy' },
  'home.debt.insight_service': {
    en: 'of every shilling of revenue goes to debt service',
    sw: 'ya kila shilingi ya mapato huenda kwa huduma ya deni',
    plain: 'of every shilling we earn goes to paying debt',
  },
  'home.debt.insight_split': {
    en: 'Domestic vs External debt split',
    sw: 'Mgawanyiko wa deni la ndani na nje',
    plain: 'Split between home and abroad',
  },
  'home.debt.insight_risk_desc': {
    en: 'IMF debt distress classification',
    sw: 'Uainishaji wa tatizo la deni wa IMF',
    plain: 'Ranked by the IMF',
  },
  'home.debt.insight_risk_label': { en: 'Risk: {level}', sw: 'Hatari: {level}', plain: 'Risk: {level}' },
  'home.debt.insight_risk_unassessed': { en: 'Risk: not assessed', sw: 'Hatari: haijatathminiwa', plain: 'Risk: we can\u2019t say yet' },
  'home.debt.insight_risk_unassessed_desc': { en: 'No debt-to-GDP reading is available, so no risk band can be stated. This is not a finding that the debt position is safe.', sw: 'Hakuna kipimo cha deni-kwa-Pato, hivyo hakuna kiwango cha hatari kinachoweza kutajwa. Hii si dalili kwamba hali ya deni ni salama.', plain: 'We don\u2019t have the debt-to-GDP number, so we can\u2019t rate the risk. That does not mean it is fine.' },
  'home.debt.cents_of_revenue': { en: 'KES {n} cents', sw: 'Senti {n} za KES', plain: 'KES {n} cents' },

  // Audit Reports Section
  'home.audits.title': { en: 'Latest Audit Reports', sw: 'Ripoti za Hivi Karibuni za Ukaguzi', plain: 'Latest Audit Reports' },
  'home.audits.subtitle': {
    en: 'Official findings from the Office of the Auditor-General',
    sw: 'Matokeo rasmi kutoka Ofisi ya Mkaguzi Mkuu',
    plain: 'What the Auditor-General found',
  },
  'home.audits.see_all': { en: 'See all reports', sw: 'Tazama ripoti zote', plain: 'See all reports' },
  'home.audits.clean': { en: 'Clean', sw: 'Safi', plain: 'Clean' },
  'home.audits.qualified': { en: 'Qualified', sw: 'Ya Kuhitimu', plain: 'Some Issues' },
  'home.audits.adverse': { en: 'Adverse', sw: 'Mbaya', plain: 'Bad' },
  'home.audits.disclaimer': { en: 'Disclaimer', sw: 'Kanusho', plain: 'Unable to audit' },
  'home.audits.no_reports': { en: 'No audit reports yet', sw: 'Hakuna ripoti za ukaguzi bado', plain: 'No audits yet' },
  'home.audits.loading': { en: 'Loading audits…', sw: 'Inapakia ukaguzi…', plain: 'Loading audits…' },
  'home.audits.report_title': { en: 'Auditor General’s Report', sw: 'Ripoti ya Mkaguzi Mkuu', plain: 'Auditor-General’s Report' },
  'home.audits.national_govt_fy': { en: 'National Government — {fy}', sw: 'Serikali Kuu — {fy}', plain: 'National Govt — {fy}' },
  'home.audits.unavailable': { en: 'Audit data unavailable', sw: 'Data ya ukaguzi haipatikani', plain: 'Audit data unavailable' },
  'home.audits.findings_label': { en: 'findings', sw: 'matokeo', plain: 'findings' },
  'home.audits.opinion_label': { en: 'Audit Opinion:', sw: 'Maoni ya Ukaguzi:', plain: 'Audit Result:' },
  'home.audits.default_basis': {
    en: 'Material misstatements identified across multiple ministries',
    sw: 'Makosa makubwa yamebainika katika wizara mbalimbali',
    plain: 'Big money errors found across many ministries',
  },
  'home.audits.signed_by': { en: 'Signed by {name}', sw: 'Imetiwa saini na {name}', plain: 'Signed by {name}' },
  'home.audits.stat_ministries': { en: 'Ministries Audited', sw: 'Wizara Zilizokaguliwa', plain: 'Ministries Checked' },
  'home.audits.stat_amount': { en: 'Amount Questioned', sw: 'Kiasi Kilichohojiwa', plain: 'Money in Question' },
  'home.audits.amount_partial': { en: 'KES {amount} stated across {n} of {total} findings', sw: 'KES {amount} imetajwa katika matokeo {n} kati ya {total}', plain: 'KES {amount} is named in {n} of the {total} findings' },
  'home.audits.amount_partial_note': { en: 'The Auditor-General\u2019s own questioned total is not stated in the machine-readable part of this report, so this is what the findings themselves add up to \u2014 not the report\u2019s headline figure.', sw: 'Jumla ya Mdhibiti na Mkaguzi Mkuu haijatajwa katika sehemu inayosomeka kwa mashine ya ripoti hii; hii ni jumla ya matokeo yenyewe, si kiasi kikuu cha ripoti.', plain: 'The Auditor-General\u2019s own total isn\u2019t in the part of the report we can read automatically. This is just what the listed findings add up to.' },
  'home.audits.stat_critical': { en: 'Critical Findings', sw: 'Matokeo Muhimu', plain: 'Serious Problems' },
  'home.audits.stat_recurring': { en: 'Recurring Issues', sw: 'Masuala Yanayojirudia', plain: 'Repeat Problems' },
  'home.audits.findings_overview': { en: 'Audit Findings Overview', sw: 'Muhtasari wa Matokeo ya Ukaguzi', plain: 'Audit Findings' },
  'home.audits.amount_prefix': { en: 'Amount:', sw: 'Kiasi:', plain: 'Amount:' },
  'home.audits.action_prefix': { en: 'Action:', sw: 'Hatua:', plain: 'Action:' },
  'home.audits.sev_critical': { en: 'Critical', sw: 'Muhimu Sana', plain: 'Serious' },
  'home.audits.sev_significant': { en: 'Significant', sw: 'Kubwa', plain: 'Significant' },
  'home.audits.sev_minor': { en: 'Minor', sw: 'Ndogo', plain: 'Small' },
  'home.audits.emphasis': { en: 'Emphasis of Matter', sw: 'Msisitizo wa Suala', plain: 'Also Note' },
  'home.audits.top_ministries': { en: 'Top Ministries Flagged', sw: 'Wizara Zilizoonywa Zaidi', plain: 'Most Problem Ministries' },
  'home.audits.view_all_findings': { en: 'View All Findings', sw: 'Tazama Matokeo Yote', plain: 'See All Findings' },
  // Empty state when the publication gate withholds every federal finding.
  // {…} placeholders are filled from the API's machine-readable
  // findings_reason / next_expected fields — never hand-written facts.
  'home.audits.empty_title': {
    en: 'No findings from the Auditor-General can be published yet',
    sw: 'Hakuna matokeo ya Mkaguzi Mkuu yanayoweza kuchapishwa bado',
    plain: 'No findings from the Auditor-General can be shown yet',
  },
  'home.audits.empty_withheld': {
    en: '{n} findings are held back because none of them can yet be traced to a page of a published report.',
    sw: 'Matokeo {n} yamezuiliwa kwa sababu hakuna linaloweza kufuatiliwa hadi ukurasa wa ripoti iliyochapishwa.',
    plain: '{n} findings are held back because we cannot yet point to the page of an official report they come from.',
  },
  'home.audits.empty_window': {
    en: 'The {publisher} publishes this report {cadence}, {lag} after the fiscal year ends. The next report is expected between {start} and {end}.',
    sw: '{publisher} huchapisha ripoti hii {cadence}, {lag} baada ya mwaka wa fedha kuisha. Ripoti ijayo inatarajiwa kati ya {start} na {end}.',
    plain: 'The {publisher} publishes this report {cadence}, {lag} after the money year ends. The next one is expected between {start} and {end}.',
  },
  'home.audits.empty_ministries': {
    en: 'No ministry can be listed until its findings trace to a published report.',
    sw: 'Hakuna wizara inayoweza kuorodheshwa hadi matokeo yake yafuatilike kwenye ripoti iliyochapishwa.',
    plain: 'No ministry can be listed until its findings come from a published report.',
  },
  'home.audits.source_page': {
    en: 'Source: report {page}',
    sw: 'Chanzo: ripoti {page}',
    plain: 'Source: report {page}',
  },
  'home.audits.cadence_annual': { en: 'annually', sw: 'kila mwaka', plain: 'once a year' },
  'home.audits.cadence_quarterly': { en: 'quarterly', sw: 'kila robo mwaka', plain: 'every three months' },
  'home.audits.cadence_monthly': { en: 'monthly', sw: 'kila mwezi', plain: 'every month' },
  'home.audits.lag_months': { en: '{lag} months', sw: 'miezi {lag}', plain: '{lag} months' },
  'home.audits.lag_days': { en: '{lag} days', sw: 'siku {lag}', plain: '{lag} days' },

  // Budget snapshot
  'home.budget.title': { en: 'National Budget Snapshot', sw: 'Muhtasari wa Bajeti ya Taifa', plain: 'The Budget Right Now' },
  'home.budget.subtitle': {
    en: 'What the government plans to spend this year',
    sw: 'Serikali inapanga kutumia nini mwaka huu',
    plain: 'What the government plans to spend this year',
  },
  'home.budget.total': { en: 'Total budget', sw: 'Bajeti jumla', plain: 'Total money planned' },
  'home.budget.sectors': { en: 'By sector', sw: 'Kwa sekta', plain: 'By area' },
  'home.budget.explore': { en: 'Explore the budget', sw: 'Chunguza bajeti', plain: 'See the full budget' },
  'home.budget.where_taxes_go': { en: 'Where Your Taxes Go', sw: 'Kodi Zako Zinakoenda', plain: 'Where Your Taxes Go' },
  'home.budget.allocation_by_sector': { en: 'National budget allocation by sector', sw: 'Mgao wa bajeti ya taifa kwa sekta', plain: 'Budget by area' },
  'home.budget.unavailable': { en: 'Budget data unavailable', sw: 'Data ya bajeti haipatikani', plain: 'Budget data unavailable' },
  'home.budget.total_label': { en: 'Total Budget', sw: 'Bajeti Jumla', plain: 'Total Budget' },
  'home.budget.execution_label': { en: 'Budget Execution', sw: 'Utekelezaji wa Bajeti', plain: 'How much was spent' },
  'home.budget.pct_spent': { en: '{pct}% spent', sw: '{pct}% imetumika', plain: '{pct}% spent' },
  'home.budget.more_sectors': { en: '+{n} more sectors', sw: '+{n} sekta zaidi', plain: '+{n} more areas' },
  'home.budget.view_full': { en: 'View Full Budget Breakdown →', sw: 'Tazama Uchambuzi Kamili wa Bajeti →', plain: 'See the full budget →' },

  // National loans
  'home.loans.title': { en: 'Who Kenya Owes', sw: 'Ambaye Kenya Inadaiwa', plain: 'Who Kenya Owes Money To' },
  'home.loans.subtitle': {
    en: 'Top creditors — where the debt came from',
    sw: 'Wadai wakuu — deni linatoka wapi',
    plain: 'Top lenders — where the money came from',
  },
  'home.loans.see_all': { en: 'See all loans', sw: 'Tazama mikopo yote', plain: 'See all loans' },
  'home.loans.lender': { en: 'Lender', sw: 'Mkopeshaji', plain: 'Who loaned the money' },
  'home.loans.amount': { en: 'Amount', sw: 'Kiasi', plain: 'Amount' },
  'home.loans.header_title': { en: 'National Government Loans', sw: 'Mikopo ya Serikali Kuu', plain: 'Kenya’s Loans' },
  'home.loans.header_sub': { en: '{n} active loans — {src}', sw: 'Mikopo hai {n} — {src}', plain: '{n} loans — {src}' },
  'home.loans.unavailable': { en: 'Loan data unavailable', sw: 'Data ya mikopo haipatikani', plain: 'Loan data unavailable' },
  'home.loans.outstanding': { en: 'Outstanding Debt', sw: 'Deni Lililobaki', plain: 'Still Owed' },
  'home.loans.annual_service': { en: 'Annual Service Cost', sw: 'Gharama ya Kila Mwaka', plain: 'Cost Per Year' },
  'home.loans.see_all_n': { en: 'See all {n} loans →', sw: 'Tazama mikopo yote {n} →', plain: 'See all {n} loans →' },
  'home.loans.type.multilateral': { en: 'Multilateral', sw: 'Ya Kimataifa', plain: 'Multi-country' },
  'home.loans.type.bilateral': { en: 'Bilateral', sw: 'Baina ya Nchi Mbili', plain: 'Country-to-country' },
  'home.loans.type.commercial': { en: 'Commercial', sw: 'Ya Kibiashara', plain: 'Commercial' },
  'home.loans.type.domestic': { en: 'Domestic', sw: 'Ya Ndani', plain: 'Local' },
  'home.loans.type.tbill': { en: 'T-Bill', sw: 'Hati ya Hazina', plain: 'T-Bill' },
  'home.loans.type.cbk': { en: 'CBK', sw: 'CBK', plain: 'Central Bank' },
  'home.loans.type.legacy': { en: 'Legacy', sw: 'Ya Zamani', plain: 'Older' },

  // County Details Panel (dashboard side panel)
  'home.county_panel.select_prompt': {
    en: 'Hover any county on the map',
    sw: 'Weka kipanya juu ya kaunti yoyote kwenye ramani',
    plain: 'Hover over a county on the map',
  },
  'home.county_panel.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'home.county_panel.spent': { en: 'Spent', sw: 'Iliyotumika', plain: 'Spent' },
  'home.county_panel.debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'home.county_panel.pending_bills': { en: 'Pending Bills', sw: 'Ankara Zilizokwama', plain: 'Unpaid Bills' },
  'home.county_panel.health_score': { en: 'Health Score', sw: 'Alama ya Afya', plain: 'Health Score' },
  'home.county_panel.view_profile': { en: 'View full profile', sw: 'Tazama wasifu kamili', plain: 'Open full profile' },
  'home.county_panel.governor': { en: 'Governor', sw: 'Gavana', plain: 'Governor' },
  'home.county_panel.county_govt': { en: 'County Government', sw: 'Serikali ya Kaunti', plain: 'County Government' },
  'home.county_panel.financial_health': { en: 'Financial Health', sw: 'Afya ya Kifedha', plain: 'Money Health' },
  'home.county_panel.total_debt': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },
  'home.county_panel.population_label': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },
  'home.county_panel.audit_rating': { en: 'Audit Rating', sw: 'Alama ya Ukaguzi', plain: 'Audit Rating' },
  'home.county_panel.fiscal_grade': { en: 'Fiscal Grade (est.)', sw: 'Daraja la Fedha (kadirio)', plain: 'Money Score (estimate)' },
  'home.county_panel.utilization': { en: 'Budget Utilisation', sw: 'Matumizi ya Bajeti', plain: 'How much was spent' },
  'home.county_panel.debt_ratio': { en: 'Debt Ratio', sw: 'Uwiano wa Deni', plain: 'Debt vs. Budget' },
  'home.county_panel.per_capita': { en: 'Budget per capita', sw: 'Bajeti kwa kila mtu', plain: 'Budget per person' },
  'home.county_panel.top_sectors': { en: 'Top Spending Sectors', sw: 'Sekta Kuu za Matumizi', plain: 'Top Spending Areas' },
  'home.county_panel.oag_findings': { en: 'OAG Audit Findings', sw: 'Matokeo ya Ukaguzi ya OAG', plain: 'Auditor findings' },
  'home.county_panel.view_all_findings': { en: 'View all {n} findings', sw: 'Tazama matokeo yote {n}', plain: 'See all {n} findings' },
  'home.county_panel.explore_name': { en: 'Explore {name}', sw: 'Chunguza {name}', plain: 'Open {name}' },
  'home.county_panel.empty_title': { en: 'Select a county', sw: 'Chagua kaunti', plain: 'Pick a county' },
  'home.county_panel.empty_body': {
    en: 'Hover over or click a county on the map to view its financial details and audit findings.',
    sw: 'Weka kipanya juu au bonyeza kaunti kwenye ramani kuona maelezo ya kifedha na matokeo ya ukaguzi.',
    plain: 'Hover or click a county on the map to see its money and audit info.',
  },
  'home.county_panel.audit_clean': { en: 'Clean', sw: 'Safi', plain: 'Clean' },
  'home.county_panel.audit_qualified': { en: 'Qualified', sw: 'Ya Kuhitimu', plain: 'Some Issues' },
  'home.county_panel.audit_adverse': { en: 'Adverse', sw: 'Mbaya', plain: 'Bad' },
  'home.county_panel.audit_disclaimer': { en: 'Disclaimer', sw: 'Kanusho', plain: 'Unable to audit' },
  'home.county_panel.audit_pending': { en: 'Pending', sw: 'Inasubiri', plain: 'Pending' },
  'home.county_panel.sev_critical': { en: 'Critical', sw: 'Muhimu Sana', plain: 'Serious' },
  'home.county_panel.sev_high': { en: 'High', sw: 'Kubwa', plain: 'High' },
  'home.county_panel.sev_warning': { en: 'Warning', sw: 'Onyo', plain: 'Warning' },
  'home.county_panel.sev_info': { en: 'Info', sw: 'Taarifa', plain: 'Info' },
  'home.county_panel.sector.health': { en: 'Health', sw: 'Afya', plain: 'Health' },
  'home.county_panel.sector.education': { en: 'Education', sw: 'Elimu', plain: 'Schools' },
  'home.county_panel.sector.roads': { en: 'Roads & Transport', sw: 'Barabara na Usafiri', plain: 'Roads' },
  'home.county_panel.sector.development': { en: 'Development', sw: 'Maendeleo', plain: 'Projects' },
  'home.county_panel.sector.recurrent': { en: 'Recurrent', sw: 'Ya Kawaida', plain: 'Day-to-day' },

  // Map legend + view toggles
  'home.map.title': { en: 'County Explorer', sw: 'Kivinjari cha Kaunti', plain: 'Kenya Map' },
  'home.map.subtitle_prefix': { en: 'counties', sw: 'kaunti', plain: 'counties' },
  'home.map.subtitle_suffix': {
    en: 'audit-status colour coded',
    sw: 'rangi kulingana na hali ya ukaguzi',
    plain: 'colour-coded by audit result',
  },
  'home.map.view_all': { en: 'All', sw: 'Zote', plain: 'All' },
  'home.map.view_focus': { en: 'Focus', sw: 'Lenga', plain: 'Focus' },
  'home.map.aria_label': {
    en: "Interactive map of Kenya's 47 counties. Hover to see county details, click to select a county. Counties are color-coded by audit status.",
    sw: 'Ramani ya kaunti 47 za Kenya. Weka kipanya kuona maelezo, bonyeza kuchagua kaunti. Kaunti zina rangi kulingana na hali ya ukaguzi.',
    plain: 'Kenya map with all 47 counties. Hover to see details, click to pick one. Colours show audit results.',
  },
  'home.map.legend.clean': { en: 'Clean / A+', sw: 'Safi / A+', plain: 'Clean / A+' },
  'home.map.legend.qualified': { en: 'Qualified / B', sw: 'Ya Kuhitimu / B', plain: 'Some Issues / B' },
  'home.map.legend.adverse': { en: 'Adverse / C', sw: 'Mbaya / C', plain: 'Bad / C' },
  'home.map.legend.disclaimer': { en: 'Disclaimer', sw: 'Kanusho', plain: 'Unable to audit' },
  'home.map.legend.pending': { en: 'Audit pending', sw: 'Ukaguzi unasubiri', plain: 'Audit pending' },

  // Feature nav cards
  'home.features.counties.title': { en: 'Browse all 47 counties', sw: 'Vinjari kaunti zote 47', plain: 'See all 47 counties' },
  'home.features.counties.desc': {
    en: 'Compare budgets, debt, and audit scores across the country.',
    sw: 'Linganisha bajeti, madeni, na alama za ukaguzi nchini kote.',
    plain: 'Compare budgets, debts, and audit scores nationwide.',
  },
  'home.features.sectors.title': { en: 'Where counties spend', sw: 'Pesa za kaunti zinakoenda', plain: 'Where counties spend' },
  'home.features.sectors.desc': {
    en: 'Roll up all 47 counties by sector — health, roads, water, education.',
    sw: 'Jumuisha kaunti zote 47 kwa sekta — afya, barabara, maji, elimu.',
    plain: 'All 47 counties grouped by area — health, roads, water, schools.',
  },
  'home.features.missing.title': { en: 'Missing funds tracker', sw: 'Kifuatilia Pesa Zilizopotea', plain: 'Missing money tracker' },
  'home.features.missing.desc': {
    en: 'Public money flagged as unaccounted-for by the Auditor-General.',
    sw: 'Pesa za umma zilizoripotiwa kutohesabiwa na Mkaguzi Mkuu.',
    plain: 'Public money the auditor says is missing.',
  },
  'home.features.sources.title': { en: 'Data sources', sw: 'Vyanzo vya Data', plain: 'Where numbers come from' },
  'home.features.sources.desc': {
    en: 'Every number on this site traces to a government publication.',
    sw: 'Kila nambari kwenye tovuti hii inatokana na chapisho la serikali.',
    plain: 'Every number here comes from a government document.',
  },
  'home.features.debt.title': { en: 'National Debt Overview', sw: 'Muhtasari wa Deni la Taifa', plain: 'Debt Overview' },
  'home.features.debt.sub': { en: 'Analyst Start', sw: 'Anza Uchambuzi', plain: 'Analyst view' },
  'home.features.budget.title': { en: 'Budget & Spending Insights', sw: 'Ufahamu wa Bajeti na Matumizi', plain: 'Budget Insights' },
  'home.features.budget.sub': { en: 'Budget Stars', sw: 'Nyota za Bajeti', plain: 'Budget highlights' },
  'home.features.explore.title': { en: 'Explore County Finances', sw: 'Chunguza Fedha za Kaunti', plain: 'See county money' },
  'home.features.explore.sub': { en: 'County Explorer', sw: 'Kivinjari cha Kaunti', plain: 'Counties' },
  'home.features.audits.title': { en: 'Audit Transparency Reports', sw: 'Ripoti za Uwazi wa Ukaguzi', plain: 'Audit reports' },
  'home.features.audits.sub': { en: 'Learning Hub', sw: 'Kituo cha Kujifunza', plain: 'Learn' },

  // Learning hub
  'home.learning.title': { en: 'New to public finance?', sw: 'Mpya kwa fedha za umma?', plain: 'New to this?' },
  'home.learning.subtitle': {
    en: 'We explain terms — absorption rate, debt-to-GDP, PFM — in plain language.',
    sw: 'Tunaeleza istilahi — kiwango cha matumizi, deni-kwa-GDP, PFM — kwa lugha rahisi.',
    plain: 'We explain every word — no jargon.',
  },
  'home.learning.cta': { en: 'Start with the basics', sw: 'Anza na misingi', plain: 'Start here' },
  'home.learning.heading': {
    en: 'Learn how Kenya manages your money',
    sw: 'Jifunze jinsi Kenya inavyosimamia pesa zako',
    plain: 'Learn how Kenya spends your money',
  },
  'home.learning.body_prefix': {
    en: 'Understand national debt, county budgets, and audit reports in an easy-to-follow',
    sw: 'Elewa deni la taifa, bajeti za kaunti, na ripoti za ukaguzi kwa njia rahisi',
    plain: 'Understand debt, budgets, and audits — no jargon',
  },
  'home.learning.hub_name': { en: 'Learning Hub', sw: 'Kituo cha Kujifunza', plain: 'Learning Hub' },
  'home.learning.visit': { en: 'Visit Learning Hub', sw: 'Tembelea Kituo cha Kujifunza', plain: 'Go to Learning Hub' },

  // Newsletter
  'home.newsletter.title': { en: 'Stay informed', sw: 'Endelea Kufahamu', plain: 'Stay in the loop' },
  'home.newsletter.subtitle': {
    en: 'Monthly round-up of what changed in Kenya’s public finances.',
    sw: 'Muhtasari wa kila mwezi wa mabadiliko katika fedha za umma za Kenya.',
    plain: 'One email a month. What’s new with Kenya’s money.',
  },
  'home.newsletter.email_placeholder': { en: 'Your email', sw: 'Barua pepe yako', plain: 'Your email' },
  'home.newsletter.subscribe': { en: 'Subscribe', sw: 'Jiandikishe', plain: 'Sign up' },
  'home.newsletter.body': {
    en: 'Get a concise weekly summary of new audits, budget changes, and county data — straight to your inbox. No account required.',
    sw: 'Pata muhtasari wa wiki wa ukaguzi mpya, mabadiliko ya bajeti, na data ya kaunti — moja kwa moja kwenye barua pepe yako. Hakuna akaunti inayohitajika.',
    plain: 'Get a weekly email with new audits, budget changes, and county news. No sign-up needed.',
  },
  'home.newsletter.placeholder': { en: 'your@email.com', sw: 'yako@barua.com', plain: 'your@email.com' },
  'home.newsletter.subscribed': { en: "You're subscribed! Check your email to confirm.", sw: 'Umejiandikisha! Angalia barua pepe yako kuthibitisha.', plain: 'You’re in! Check your email to confirm.' },
  'home.newsletter.resubscribed': { en: 'Welcome back! Your subscription has been reactivated.', sw: 'Karibu tena! Usajili wako umewashwa tena.', plain: 'Welcome back! You’re subscribed again.' },
  'home.newsletter.already': { en: 'This email is already subscribed to our newsletter.', sw: 'Barua pepe hii tayari imejiandikisha.', plain: 'This email is already signed up.' },
  'home.newsletter.generic_error': { en: 'Something went wrong. Please try again.', sw: 'Hitilafu imetokea. Jaribu tena.', plain: 'Something went wrong. Please try again.' },

  // ══════════════════════════════════════════════════
  // Counties list page
  // ══════════════════════════════════════════════════
  'counties.title': { en: 'County Explorer', sw: 'Kivinjari cha Kaunti', plain: 'Explore Counties' },
  'counties.modelled_estimate': {
    en: 'Modelled estimate — not official Controller of Budget figures. County budget allocations use the Commission on Revenue Allocation (CRA) equitable-share formula. The county debt and pending-bill figures are modelled: they are not county-reported actuals, and they are not yet traced to a page of a Controller of Budget or county publication. Audit findings are from the Office of the Auditor-General.',
    sw: 'Makadirio ya kielelezo — si takwimu rasmi za Mdhibiti wa Bajeti. Mgao wa bajeti ya kaunti unatumia fomula ya mgao sawa ya Tume ya Ugawaji wa Mapato (CRA). Takwimu za deni la kaunti na bili ambazo hazijalipwa ni za kielelezo: si takwimu halisi zilizoripotiwa na kaunti, na bado hazijafuatiliwa hadi ukurasa wa chapisho la Mdhibiti wa Bajeti au la kaunti. Matokeo ya ukaguzi yanatoka Ofisi ya Mkaguzi Mkuu wa Hesabu.',
    plain: 'These county money numbers are estimates, not official Controller of Budget figures. Budgets use the CRA sharing formula. The debt and unpaid-bill numbers are modelled — they are not what the county itself reported, and we cannot yet show you the page they came from. The audit findings are real, from the Auditor-General.',
  },
  'counties.subtitle': {
    en: 'Compare all 47 Kenyan counties on budget, execution, debt, and audit findings.',
    sw: 'Linganisha kaunti zote 47 za Kenya kwa bajeti, matumizi, deni, na matokeo ya ukaguzi.',
    plain: 'Compare all 47 counties — budgets, spending, debts, and audits.',
  },
  'counties.search.placeholder': {
    en: 'Search counties by name…',
    sw: 'Tafuta kaunti kwa jina…',
    plain: 'Type a county name…',
  },
  'counties.filter.all': { en: 'All counties', sw: 'Kaunti zote', plain: 'All' },
  'counties.filter.region': { en: 'Region', sw: 'Eneo', plain: 'Region' },
  'counties.filter.sort': { en: 'Sort by', sw: 'Panga kwa', plain: 'Sort by' },
  'counties.sort.name': { en: 'Name', sw: 'Jina', plain: 'Name' },
  'counties.sort.budget': { en: 'Budget (largest first)', sw: 'Bajeti (kubwa kwanza)', plain: 'Biggest budget first' },
  'counties.sort.utilization': { en: 'Execution rate', sw: 'Kiwango cha matumizi', plain: 'How much was spent' },
  'counties.sort.health': { en: 'Financial health', sw: 'Afya ya Kifedha', plain: 'Money health' },
  'counties.sort.debt': { en: 'Debt (largest first)', sw: 'Deni (kubwa kwanza)', plain: 'Biggest debt first' },
  'counties.sort.population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'Most people first' },
  'counties.view.grid': { en: 'Grid view', sw: 'Muonekano wa Gridi', plain: 'Cards view' },
  'counties.view.list': { en: 'List view', sw: 'Muonekano wa Orodha', plain: 'Table view' },
  'counties.view.map': { en: 'Map view', sw: 'Muonekano wa Ramani', plain: 'Map view' },
  'counties.compare_cta': { en: 'Compare counties', sw: 'Linganisha kaunti', plain: 'Compare counties' },
  'counties.results_count': { en: 'counties found', sw: 'kaunti zimepatikana', plain: 'counties found' },
  'counties.none_match': { en: 'No counties match your filter', sw: 'Hakuna kaunti zinazolingana', plain: 'No counties match' },
  'counties.clear_filters': { en: 'Clear filters', sw: 'Ondoa vichujio', plain: 'Clear filters' },
  'counties.budget_label': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'counties.spent_label': { en: 'Spent', sw: 'Imetumika', plain: 'Spent' },
  'counties.debt_label': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'counties.pop_label': { en: 'Pop.', sw: 'Watu', plain: 'People' },
  'counties.health_label': { en: 'Health', sw: 'Afya', plain: 'Health' },
  'counties.audit_label': { en: 'Audit', sw: 'Ukaguzi', plain: 'Audit' },
  'counties.view_county': { en: 'View county', sw: 'Tazama kaunti', plain: 'Open county' },
  'counties.error.title': { en: 'Failed to load counties', sw: 'Imeshindwa kupakia kaunti', plain: 'Could not load counties' },
  'counties.error.body': { en: 'Please refresh the page.', sw: 'Tafadhali onyesha ukurasa upya.', plain: 'Please reload.' },
  'counties.loading': { en: 'Loading counties…', sw: 'Inapakia kaunti…', plain: 'Loading counties…' },
  'counties.summary.total_counties': { en: 'Counties', sw: 'Kaunti', plain: 'Counties' },
  'counties.summary.total_budget': { en: 'Combined budget', sw: 'Bajeti ya pamoja', plain: 'Total budget' },
  'counties.summary.avg_utilization': { en: 'Avg. execution', sw: 'Wastani wa matumizi', plain: 'Average spent' },
  'counties.summary.total_debt': { en: 'Combined debt', sw: 'Deni la pamoja', plain: 'Total debt' },

  // Counties list — KPI cards
  'counties.kpi.total_budget': { en: 'Total Budget', sw: 'Bajeti Jumla', plain: 'Total Budget' },
  'counties.kpi.across_counties': { en: 'Across {n} counties', sw: 'Kutoka kaunti {n}', plain: 'From {n} counties' },
  'counties.kpi.total_debt': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },
  'counties.kpi.pending_bills_loans': { en: 'County debt (excl. pending bills)', sw: 'Deni la kaunti (bila ankara zilizokwama)', plain: 'County loans (not counting unpaid bills)' },
  'counties.kpi.audit_status_derived': { en: 'Status derived from finding severity — not an official OAG audit opinion.', sw: 'Hali imetokana na uzito wa matokeo — si maoni rasmi ya ukaguzi ya OAG.', plain: 'Based on how serious the findings are — not an official OAG opinion.' },
  'counties.kpi.avg_execution_rate': { en: 'Avg. Execution Rate', sw: 'Wastani wa Matumizi', plain: 'Average spent' },
  'counties.kpi.see_rankings': { en: 'See county rankings below', sw: 'Tazama orodha ya kaunti chini', plain: 'See county rankings below' },
  'counties.kpi.target_70': { en: 'Target: 70%', sw: 'Lengo: 70%', plain: 'Goal: 70%' },
  'counties.kpi.not_reported': { en: 'Not yet reported', sw: 'Bado haijaripotiwa', plain: 'Not reported yet' },
  'counties.kpi.audit_summary': { en: 'Audit Summary', sw: 'Muhtasari wa Ukaguzi', plain: 'Audit Summary' },
  'counties.kpi.no_audits_year': { en: 'No audits reported for this year yet.', sw: 'Hakuna ukaguzi uliopatikana kwa mwaka huu bado.', plain: 'No audits reported for this year yet.' },
  'counties.kpi.high_debt_counties': { en: 'High Debt Counties', sw: 'Kaunti zenye Deni Kubwa', plain: 'Counties with Most Debt' },

  // Counties list — Filters sidebar
  'counties.filters.title': { en: 'Filters', sw: 'Vichujio', plain: 'Filters' },
  'counties.filters.search_county': { en: 'Search County', sw: 'Tafuta Kaunti', plain: 'Find County' },
  'counties.filters.type_to_search': { en: 'Type to search…', sw: 'Andika kutafuta…', plain: 'Type a name…' },
  'counties.filters.all_regions': { en: 'All Regions', sw: 'Maeneo Yote', plain: 'All Regions' },
  'counties.filters.grade': { en: 'Grade', sw: 'Daraja', plain: 'Grade' },
  'counties.filters.audit_status': { en: 'Audit Status', sw: 'Hali ya Ukaguzi', plain: 'Audit Status' },
  'counties.filters.spending_range': { en: 'Spending Range', sw: 'Kiwango cha Matumizi', plain: 'Spending Range' },
  'counties.filters.apply': { en: 'Apply Filters', sw: 'Tumia Vichujio', plain: 'Apply Filters' },
  'counties.filters.reset': { en: 'Reset', sw: 'Weka Upya', plain: 'Reset' },

  // Regions
  'counties.region.central': { en: 'Central', sw: 'Kati', plain: 'Central' },
  'counties.region.coast': { en: 'Coast', sw: 'Pwani', plain: 'Coast' },
  'counties.region.eastern': { en: 'Eastern', sw: 'Mashariki', plain: 'Eastern' },
  'counties.region.nairobi': { en: 'Nairobi', sw: 'Nairobi', plain: 'Nairobi' },
  'counties.region.north_eastern': { en: 'North Eastern', sw: 'Kaskazini Mashariki', plain: 'North Eastern' },
  'counties.region.nyanza': { en: 'Nyanza', sw: 'Nyanza', plain: 'Nyanza' },
  'counties.region.rift_valley': { en: 'Rift Valley', sw: 'Bonde la Ufa', plain: 'Rift Valley' },
  'counties.region.western': { en: 'Western', sw: 'Magharibi', plain: 'Western' },

  // Counties list — Sort options
  'counties.sort.budget_high_low': { en: 'Budget (High → Low)', sw: 'Bajeti (Juu → Chini)', plain: 'Biggest budget first' },
  'counties.sort.budget_low_high': { en: 'Budget (Low → High)', sw: 'Bajeti (Chini → Juu)', plain: 'Smallest budget first' },
  'counties.sort.debt_high_low': { en: 'Debt (High → Low)', sw: 'Deni (Juu → Chini)', plain: 'Biggest debt first' },
  'counties.sort.population_high_low': { en: 'Population (High → Low)', sw: 'Idadi ya Watu (Juu → Chini)', plain: 'Most people first' },
  'counties.sort.grade_best_worst': { en: 'Grade (Best → Worst)', sw: 'Daraja (Bora → Mbaya)', plain: 'Best grade first' },
  'counties.sort.execution_high_low': { en: 'Execution (High → Low)', sw: 'Utekelezaji (Juu → Chini)', plain: 'Most spent first' },

  // Counties list — Map
  'counties.map.title': { en: 'County Performance Map', sw: 'Ramani ya Utendaji wa Kaunti', plain: 'How Counties Are Doing' },
  'counties.map.tooltip_grade': { en: 'Grade', sw: 'Daraja', plain: 'Grade' },
  'counties.map.tooltip_exec': { en: 'Exec', sw: 'Matumizi', plain: 'Spent' },
  'counties.map.tooltip_budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'counties.map.performance': { en: 'Performance', sw: 'Utendaji', plain: 'Performance' },
  'counties.map.clear': { en: 'clear', sw: 'futa', plain: 'clear' },

  // Counties list — Insights panel
  'counties.insights.no_match': { en: 'No counties match the current filters', sw: 'Hakuna kaunti zinazolingana na vichujio', plain: 'No counties match your filters' },
  'counties.insights.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'counties.insights.debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'counties.insights.avg_exec': { en: 'Avg Exec', sw: 'Wastani wa Matumizi', plain: 'Avg spent' },
  'counties.insights.avg_health': { en: 'Avg Health', sw: 'Wastani wa Afya', plain: 'Avg health' },
  'counties.insights.best_performers': { en: 'Best Performers', sw: 'Waliofanya Vizuri Zaidi', plain: 'Doing Best' },
  'counties.insights.needs_attention': { en: 'Needs Attention', sw: 'Zinahitaji Umakini', plain: 'Needs Attention' },
  'counties.insights.exec_short': { en: 'Exec', sw: 'Matumizi', plain: 'Spent' },
  'counties.insights.debt_short': { en: 'Debt', sw: 'Deni', plain: 'Debt' },

  // Counties list — Rankings table
  'counties.rankings.title': { en: 'County Rankings', sw: 'Orodha ya Kaunti', plain: 'County Rankings' },
  'counties.rankings.range_of': { en: '{from}–{to} of {total}', sw: '{from}–{to} kati ya {total}', plain: '{from}–{to} of {total}' },
  'counties.rankings.col_county': { en: 'County', sw: 'Kaunti', plain: 'County' },
  'counties.rankings.col_population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },
  'counties.rankings.col_health': { en: 'Health', sw: 'Afya', plain: 'Health' },
  'counties.rankings.col_budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'counties.rankings.col_execution': { en: 'Execution', sw: 'Matumizi', plain: 'Spent' },
  'counties.rankings.col_debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'counties.rankings.col_audit': { en: 'Audit', sw: 'Ukaguzi', plain: 'Audit' },
  'counties.rankings.no_match': { en: 'No counties match your filters', sw: 'Hakuna kaunti zinazolingana na vichujio vyako', plain: 'No counties match your filters' },
  'counties.rankings.showing_all': { en: 'Showing all {n} Counties', sw: 'Inaonyesha kaunti zote {n}', plain: 'Showing all {n} Counties' },
  'counties.rankings.showing_range': { en: 'Showing {from}–{to} of {total} Counties', sw: 'Inaonyesha {from}–{to} kati ya kaunti {total}', plain: 'Showing {from}–{to} of {total} Counties' },
  'counties.rankings.prev': { en: '< Prev', sw: '< Nyuma', plain: '< Back' },
  'counties.rankings.next': { en: 'Next >', sw: 'Mbele >', plain: 'Next >' },
  'counties.rankings.show_paginated': { en: 'Show Paginated', sw: 'Onyesha kwa Kurasa', plain: 'Show by pages' },
  'counties.rankings.view_all': { en: 'View All Counties', sw: 'Tazama Kaunti Zote', plain: 'See All Counties' },

  // Counties list — header extras
  'counties.header.subtitle_rich': { en: 'Compare {strong} · Budgets, Spending, Debts & Audit Outcomes', sw: 'Linganisha {strong} · Bajeti, Matumizi, Madeni na Matokeo ya Ukaguzi', plain: 'Compare {strong} · Budgets, Spending, Debts and Audit Results' },
  'counties.header.subtitle_strong': { en: '47 Counties', sw: 'Kaunti 47', plain: '47 Counties' },
  'counties.header.year': { en: 'Year', sw: 'Mwaka', plain: 'Year' },
  'counties.header.export': { en: 'Export', sw: 'Pakua', plain: 'Download' },
  'counties.header.retry': { en: 'Retry', sw: 'Jaribu Tena', plain: 'Try Again' },

  // Audit status labels (shared chips on counties list)
  'counties.audit_status.clean': { en: 'Clean', sw: 'Safi', plain: 'Clean' },
  'counties.audit_status.qualified': { en: 'Qualified', sw: 'Ya Kuhitimu', plain: 'Some Issues' },
  'counties.audit_status.adverse': { en: 'Adverse', sw: 'Mbaya', plain: 'Bad' },
  'counties.audit_status.disclaimer': { en: 'Disclaimer', sw: 'Kanusho', plain: 'Unable to audit' },
  'counties.audit_status.pending': { en: 'Pending', sw: 'Inasubiri', plain: 'Pending' },

  // ══════════════════════════════════════════════════
  // County detail page
  // ══════════════════════════════════════════════════
  'county.loading': { en: 'Loading county data…', sw: 'Inapakia data ya kaunti…', plain: 'Loading county…' },
  'county.error.title': { en: 'Failed to load county data', sw: 'Imeshindwa kupakia data', plain: 'Could not load this county' },
  'county.error.body': { en: 'This county may not exist, or the backend is unavailable.', sw: 'Kaunti hii huenda isipo, au mfumo haupatikani.', plain: 'We can’t find this county right now.' },
  'county.back_to_list': { en: 'Back to all counties', sw: 'Rudi kwa kaunti zote', plain: 'Back to all counties' },

  // Tabs
  'county.tab.overview': { en: 'Overview', sw: 'Muhtasari', plain: 'Overview' },
  'county.tab.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'county.tab.audit': { en: 'Audits & Accountability', sw: 'Ukaguzi na Uwajibikaji', plain: 'Audits' },
  'county.tab.projects': { en: 'Projects', sw: 'Miradi', plain: 'Projects' },
  'county.tab.officials': { en: 'Officials', sw: 'Viongozi', plain: 'Officials' },
  'county.tab.sources': { en: 'Data sources', sw: 'Vyanzo', plain: 'Sources' },

  // County profile card
  'county.profile.title': { en: 'County Profile', sw: 'Wasifu wa Kaunti', plain: 'About this County' },
  'county.profile.population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },
  'county.profile.population_year': { en: 'As of', sw: 'Kufikia', plain: 'As of' },
  'county.profile.governor': { en: 'Governor', sw: 'Gavana', plain: 'Governor' },
  'county.profile.headquarters': { en: 'Headquarters', sw: 'Makao Makuu', plain: 'Main town' },
  'county.profile.area_km2': { en: 'Area (km²)', sw: 'Eneo (km²)', plain: 'Area (km²)' },
  'county.profile.economic_base': { en: 'Economic base', sw: 'Msingi wa Kiuchumi', plain: 'Main income source' },

  // Health & audit grade badges
  'county.grade.health': { en: 'HEALTH', sw: 'AFYA', plain: 'HEALTH' },
  'county.grade.audit': { en: 'AUDIT', sw: 'UKAGUZI', plain: 'AUDIT' },
  'county.grade.trend_up': { en: 'trending up', sw: 'inapanda', plain: 'going up' },
  'county.grade.trend_down': { en: 'trending down', sw: 'inashuka', plain: 'going down' },

  // Budget card
  'county.budget.title': { en: 'Budget Overview', sw: 'Muhtasari wa Bajeti', plain: 'Budget Summary' },
  'county.budget.allocated': { en: 'Allocated', sw: 'Iliyotengwa', plain: 'Planned' },
  'county.budget.spent': { en: 'Actually spent', sw: 'Iliyotumika kweli', plain: 'Really spent' },
  'county.budget.utilization': { en: 'Execution rate', sw: 'Kiwango cha Matumizi', plain: 'How much was spent' },
  'county.budget.development': { en: 'Development', sw: 'Maendeleo', plain: 'Projects & building' },
  'county.budget.recurrent': { en: 'Recurrent', sw: 'Ya Kawaida', plain: 'Day-to-day costs' },
  'county.budget.per_capita': { en: 'Per-capita budget', sw: 'Bajeti kwa mtu', plain: 'Budget per person' },
  'county.budget.fy': { en: 'Fiscal year', sw: 'Mwaka wa Fedha', plain: 'Year' },
  'county.budget.sector_breakdown': { en: 'Spending by sector', sw: 'Matumizi kwa sekta', plain: 'Spending by area' },

  // Revenue & debt
  'county.revenue.title': { en: 'Revenue & Transfers', sw: 'Mapato na Uhamishaji', plain: 'Money Coming In' },
  'county.revenue.own_source': { en: 'Own-source revenue', sw: 'Mapato ya chenyewe', plain: 'Money the county raised' },
  'county.revenue.equitable_share': { en: 'Equitable share', sw: 'Sehemu Sawa', plain: 'From national govt' },
  'county.revenue.conditional_grants': { en: 'Conditional grants', sw: 'Ruzuku za Masharti', plain: 'Special grants' },
  'county.debt.title': { en: 'Debt & Pending Bills', sw: 'Deni na Ankara Zilizokwama', plain: 'What the County Owes' },
  'county.debt.total': { en: 'Total debt', sw: 'Deni jumla', plain: 'Total owed' },
  'county.debt.pending_bills': { en: 'Pending bills', sw: 'Ankara zilizokwama', plain: 'Unpaid bills' },
  'county.debt.pending_bills_sub': {
    en: 'Money owed to suppliers and contractors',
    sw: 'Pesa zinazodaiwa wauzaji na wakandarasi',
    plain: 'Money owed to suppliers',
  },

  // Audit card
  'county.audit.title': { en: 'Audit Findings', sw: 'Matokeo ya Ukaguzi', plain: 'Audit Findings' },
  'county.audit.subtitle': {
    en: 'From the Office of the Auditor-General',
    sw: 'Kutoka Ofisi ya Mkaguzi Mkuu',
    plain: 'From the Auditor-General',
  },
  'county.audit.opinion': { en: 'Audit opinion', sw: 'Maoni ya Ukaguzi', plain: 'Audit result' },
  'county.audit.severity': { en: 'Severity', sw: 'Ukubwa', plain: 'How serious' },
  'county.audit.info': { en: 'Info', sw: 'Taarifa', plain: 'Note' },
  'county.audit.warning': { en: 'Warning', sw: 'Onyo', plain: 'Warning' },
  'county.audit.critical': { en: 'Critical', sw: 'Muhimu Sana', plain: 'Serious' },
  'county.audit.no_findings': { en: 'No findings yet', sw: 'Hakuna matokeo bado', plain: 'No findings yet' },
  'county.audit.view_all': { en: 'View all findings', sw: 'Tazama matokeo yote', plain: 'See all findings' },

  // Officials card
  'county.officials.title': { en: 'Elected & Executive Officials', sw: 'Viongozi Waliochaguliwa', plain: 'Who Runs the County' },
  'county.officials.subtitle': {
    en: 'Key people in the county government',
    sw: 'Watu wakuu katika serikali ya kaunti',
    plain: 'Who the top people are',
  },
  'county.officials.governor': { en: 'Governor', sw: 'Gavana', plain: 'Governor' },
  'county.officials.deputy_governor': { en: 'Deputy Governor', sw: 'Naibu Gavana', plain: 'Deputy Governor' },
  'county.officials.cec_finance': { en: 'CEC Finance', sw: 'CEC wa Fedha', plain: 'Finance Chief' },
  'county.officials.speaker': { en: 'Assembly Speaker', sw: 'Spika wa Bunge', plain: 'Assembly Speaker' },
  'county.officials.not_published': { en: 'Not yet published', sw: 'Haijachapishwa bado', plain: 'Not listed yet' },
  'county.officials.term_since': { en: 'Since', sw: 'Tangu', plain: 'Since' },
  'county.officials.visit_website': { en: 'Official website', sw: 'Tovuti rasmi', plain: 'Official website' },
  'county.officials.role.governor': {
    en: 'Chief executive of the county government. Elected directly by voters every five years.',
    sw: 'Mkuu wa serikali ya kaunti. Anachaguliwa moja kwa moja na wapiga kura kila baada ya miaka mitano.',
    plain: 'Leader of the county. Elected every 5 years.',
  },
  'county.officials.role.deputy_governor': {
    en: 'Deputy to the Governor, elected on the same ticket. Steps in when the Governor is away or vacates office.',
    sw: 'Naibu wa Gavana, anachaguliwa pamoja naye. Huchukua nafasi pale Gavana hayupo.',
    plain: 'Second-in-command. Takes over if the Governor is away.',
  },
  'county.officials.role.cec_finance': {
    en: 'County Executive Committee member for Finance — the county-level equivalent of a finance minister.',
    sw: 'Mjumbe wa Kamati Tendaji ya Kaunti wa Fedha — sawa na waziri wa fedha wa kaunti.',
    plain: 'In charge of the county’s money — like a finance minister.',
  },
  'county.officials.role.assembly_speaker': {
    en: 'Presides over the County Assembly (the legislative body). Elected by Assembly members.',
    sw: 'Mwenyekiti wa Bunge la Kaunti. Huchaguliwa na wabunge.',
    plain: 'Leads the County Assembly. Chosen by assembly members.',
  },

  // Projects card
  'county.projects.title': { en: 'Stalled Projects', sw: 'Miradi Iliyokwama', plain: 'Stuck Projects' },
  'county.projects.none': { en: 'No stalled projects flagged', sw: 'Hakuna miradi iliyoripotiwa kukwama', plain: 'No stuck projects reported' },
  'county.projects.status': { en: 'Status', sw: 'Hali', plain: 'Status' },
  'county.projects.cost': { en: 'Cost', sw: 'Gharama', plain: 'Cost' },

  // Data sources card
  'county.sources.title': { en: 'Data sources for this county', sw: 'Vyanzo vya data kwa kaunti hii', plain: 'Where these numbers come from' },

  // Missing funds
  'county.missing.title': { en: 'Missing Funds', sw: 'Pesa Zilizopotea', plain: 'Missing Money' },
  'county.missing.none': { en: 'No missing-funds cases flagged.', sw: 'Hakuna kesi za pesa zilizopotea.', plain: 'No missing money reported.' },

  // Financial summary
  'county.summary.title': { en: 'Financial Summary', sw: 'Muhtasari wa Fedha', plain: 'Money Summary' },
  'county.summary.net_position': { en: 'Net position', sw: 'Nafasi halisi', plain: 'Net money' },

  // ══════════════════════════════════════════════════
  // Sectors page
  // ══════════════════════════════════════════════════
  'sectors.title': { en: 'Where counties actually spend', sw: 'Pesa za kaunti zinakoenda kweli', plain: 'Where counties really spend' },
  'sectors.subtitle': {
    en: 'Every county’s latest executed budget, rolled up by sector. Shows both allocation (what was planned) and execution (what actually got spent) — so you can see which sectors are delivering and which are stuck.',
    sw: 'Bajeti ya hivi karibuni ya kila kaunti, imepangwa kwa sekta. Inaonyesha zote mbili mipango (kilichopangwa) na utekelezaji (kilichotumika kweli) — ili uone sekta zinazofanya vizuri na zilizokwama.',
    plain: 'The latest budgets from all counties, grouped by area. Shows what was planned vs. what got spent — so you can see which areas are working and which are stuck.',
  },
  'sectors.total_allocated': { en: 'Total allocated', sw: 'Iliyotengwa jumla', plain: 'Total planned' },
  'sectors.total_allocated_sub': { en: 'Aggregated across {n} counties', sw: 'Imejumuishwa kutoka kaunti {n}', plain: 'Added from {n} counties' },
  'sectors.total_executed': { en: 'Total executed', sw: 'Iliyotumika jumla', plain: 'Total spent' },
  'sectors.total_executed_sub': { en: 'Modelled county spending — not final actuals', sw: 'Matumizi ya kaunti ya kielelezo — si takwimu za mwisho', plain: 'County spending (estimate, not final)' },
  'sectors.projected_note': {
    en: 'This fiscal year is still in progress — figures are projected/partial (National Treasury BPS), not final Controller of Budget actuals.',
    sw: 'Mwaka huu wa fedha bado unaendelea — takwimu ni makadirio/sehemu (BPS ya Hazina ya Taifa), si takwimu za mwisho za Mdhibiti wa Bajeti.',
    plain: 'This year is not finished yet — these numbers are estimates, not the final spending.',
  },
  'sectors.source_label': { en: 'Source', sw: 'Chanzo', plain: 'Source' },
  'sectors.execution_rate': { en: 'Overall execution rate', sw: 'Kiwango cha matumizi kwa jumla', plain: 'Overall spend rate' },
  'sectors.execution_rate_sub': { en: 'Of every KES planned', sw: 'Ya kila KES iliyopangwa', plain: 'Of every shilling planned' },
  'sectors.loading': { en: 'Loading sector roll-up…', sw: 'Inapakia muhtasari wa sekta…', plain: 'Loading sectors…' },
  'sectors.error': { en: 'Failed to load sector data. Please refresh.', sw: 'Imeshindwa kupakia data ya sekta. Tafadhali onyesha upya.', plain: 'Could not load sectors. Please reload.' },
  'sectors.counties_count': { en: 'counties', sw: 'kaunti', plain: 'counties' },
  'sectors.of_label': { en: 'of', sw: 'ya', plain: 'of' },
  'sectors.executed_suffix': { en: 'executed', sw: 'imetumika', plain: 'spent' },
  'sectors.top_counties': { en: 'Top counties by {sector} spending', sw: 'Kaunti kuu kwa matumizi ya {sector}', plain: 'Counties spending most on {sector}' },
  'sectors.methodology.title': { en: 'How we bucket sectors', sw: 'Jinsi tunavyopanga sekta', plain: 'How we group sectors' },
  'sectors.methodology.body': {
    en: 'Counties use slightly different labels (“Health Services”, “Health & Sanitation”, “Medical Services” all appear). We normalise them into 10 canonical sectors so cross-county comparison is apples-to-apples. For each county we use its latest fiscal period that has actual execution recorded — so the numbers reflect money already spent, not just allocated.',
    sw: 'Kaunti hutumia majina tofauti kidogo (“Huduma za Afya”, “Afya na Usafi”, “Huduma za Matibabu” zote huonekana). Tunazifanya ziwe sekta 10 zilizo sawa ili ulinganifu uwe wa haki. Kwa kila kaunti tunatumia kipindi cha hivi karibuni cha fedha kilicho na matumizi halisi — hivyo nambari zinaonyesha pesa zilizotumika kweli, si zilizotengwa tu.',
    plain: 'Counties use slightly different names for the same thing. We group them into 10 clean buckets so you can compare fairly. We use each county’s latest year that has real spending — not just planned money.',
  },

  // Sector names
  'sectors.health': { en: 'Health', sw: 'Afya', plain: 'Health' },
  'sectors.education': { en: 'Education', sw: 'Elimu', plain: 'Schools' },
  'sectors.roads': { en: 'Roads & Infrastructure', sw: 'Barabara na Miundombinu', plain: 'Roads & Buildings' },
  'sectors.water': { en: 'Water & Sanitation', sw: 'Maji na Usafi', plain: 'Water & Toilets' },
  'sectors.agriculture': { en: 'Agriculture', sw: 'Kilimo', plain: 'Farming' },
  'sectors.environment': { en: 'Environment', sw: 'Mazingira', plain: 'Environment' },
  'sectors.trade': { en: 'Trade & Industry', sw: 'Biashara na Viwanda', plain: 'Business' },
  'sectors.social': { en: 'Social Services', sw: 'Huduma za Jamii', plain: 'Social Services' },
  'sectors.admin': { en: 'Administration', sw: 'Utawala', plain: 'Running the office' },
  'sectors.other': { en: 'Other', sw: 'Nyingine', plain: 'Other' },

  // ══════════════════════════════════════════════════
  // Compare page
  // ══════════════════════════════════════════════════
  'compare.title': { en: 'Compare counties', sw: 'Linganisha Kaunti', plain: 'Compare counties' },
  'compare.subtitle': {
    en: 'Line up two or three counties side-by-side: budgets, execution, debt, sector mix. Useful when your county is in the news and you want to know — compared to whom, exactly?',
    sw: 'Panga kaunti mbili au tatu jirani: bajeti, matumizi, deni, mchanganyiko wa sekta. Inasaidia kaunti yako inapokuwa kwenye habari — ukitaka kujua, ukilinganishwa na nani hasa?',
    plain: 'Put two or three counties side-by-side: budgets, spending, debt, and areas. When your county is in the news, see how it compares.',
  },
  'compare.county_label': { en: 'County', sw: 'Kaunti', plain: 'County' },
  'compare.pick_prompt': { en: '— pick a county —', sw: '— chagua kaunti —', plain: '— pick a county —' },
  'compare.add_county': { en: 'Add county', sw: 'Ongeza kaunti', plain: 'Add county' },
  'compare.remove_county': { en: 'Remove county {n}', sw: 'Ondoa kaunti {n}', plain: 'Remove county {n}' },
  'compare.empty.title': { en: 'Pick at least two counties to compare', sw: 'Chagua angalau kaunti mbili kulinganisha', plain: 'Pick at least two counties' },
  'compare.empty.body': {
    en: 'Use the dropdowns above. Try pairing a big-budget county like Nairobi with a smaller neighbour to see per-capita differences pop out.',
    sw: 'Tumia menyu za juu. Jaribu kulinganisha kaunti ya bajeti kubwa kama Nairobi na kaunti ndogo ili uone tofauti za kwa mtu.',
    plain: 'Use the dropdowns above. Try comparing a big city like Nairobi to a smaller county to see how they differ per person.',
  },
  'compare.loading': { en: 'Loading counties…', sw: 'Inapakia kaunti…', plain: 'Loading…' },
  'compare.section.pop_budget': { en: 'Population & budget', sw: 'Idadi ya watu & bajeti', plain: 'People & budget' },
  'compare.section.execution': { en: 'Execution', sw: 'Utekelezaji', plain: 'Spending' },
  'compare.section.health': { en: 'Financial health', sw: 'Afya ya kifedha', plain: 'Money health' },
  'compare.section.sectors': { en: 'Sector spending (actual)', sw: 'Matumizi ya sekta (halisi)', plain: 'Spending by area' },
  'compare.row.population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },
  'compare.row.total_budget': { en: 'Total budget', sw: 'Bajeti jumla', plain: 'Total budget' },
  'compare.row.total_budget_sub': { en: 'Latest FY', sw: 'Mwaka wa hivi karibuni', plain: 'Latest year' },
  'compare.row.per_capita': { en: 'Per-capita budget', sw: 'Bajeti kwa mtu', plain: 'Budget per person' },
  'compare.row.per_capita_sub': { en: 'Budget ÷ population', sw: 'Bajeti ÷ idadi ya watu', plain: 'Budget ÷ people' },
  'compare.row.spent': { en: 'Actually spent', sw: 'Iliyotumika kweli', plain: 'Really spent' },
  'compare.row.utilization': { en: 'Utilization', sw: 'Matumizi', plain: 'How much was spent' },
  'compare.row.utilization_sub': { en: 'Spent ÷ allocated', sw: 'Iliyotumika ÷ iliyotengwa', plain: 'Spent ÷ planned' },
  'compare.row.dev_share': { en: 'Development share', sw: 'Sehemu ya maendeleo', plain: 'Projects share' },
  'compare.row.dev_share_sub': { en: 'Of total budget', sw: 'Ya jumla ya bajeti', plain: 'Of total budget' },
  'compare.row.pending_bills': { en: 'Pending bills', sw: 'Ankara zilizokwama', plain: 'Unpaid bills' },
  'compare.row.pending_bills_sub': { en: 'Money owed to suppliers', sw: 'Pesa zinazodaiwa wauzaji', plain: 'Money owed to suppliers' },
  'compare.row.debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'compare.row.health_score': { en: 'Financial health score', sw: 'Alama ya afya ya kifedha', plain: 'Money health score' },
  'compare.row.health_score_sub': { en: '0–100, higher is better', sw: '0–100, kubwa ni bora', plain: '0–100, higher is better' },
  'compare.footer.title': { en: 'Reading this table', sw: 'Kusoma jedwali hili', plain: 'How to read this' },
  'compare.footer.body': {
    en: 'Green numbers mark the best value in each row; red marks the worst. “Best” usually means higher (more budget, more execution, higher health score) — except for pending bills and debt, where lower is healthier. Hover any county name to open its full profile.',
    sw: 'Nambari za kijani zinaonyesha thamani bora katika kila safu; nyekundu inaonyesha mbaya zaidi. “Bora” kawaida maana yake juu (bajeti zaidi, matumizi zaidi, alama ya juu ya afya) — isipokuwa ankara zilizokwama na deni, ambapo chini ni bora zaidi. Bonyeza jina la kaunti yoyote kufungua wasifu kamili.',
    plain: 'Green = best in each row. Red = worst. "Best" usually means higher — except for unpaid bills and debt, where lower is better. Click any county name to open its page.',
  },

  // ══════════════════════════════════════════════════
  // County detail page — extras (detail page wiring)
  // ══════════════════════════════════════════════════

  // Page shell + loading / error
  'county.page.title_fallback': { en: 'County Details', sw: 'Maelezo ya Kaunti', plain: 'County Details' },
  'county.page.subtitle': { en: 'County government transparency report', sw: 'Ripoti ya uwazi ya serikali ya kaunti', plain: 'County transparency report' },
  'county.page.name_suffix': { en: 'County', sw: 'Kaunti', plain: 'County' },
  'county.page.failed_load': { en: 'Failed to load county data', sw: 'Imeshindwa kupakia data ya kaunti', plain: 'Could not load county data' },
  'county.page.back_follow_money': { en: 'Back to Follow the Money', sw: 'Rudi kwa Fuatilia Pesa', plain: 'Back to Follow the Money' },
  'county.page.back_county_explorer': { en: 'Back to County Explorer', sw: 'Rudi kwa Kivinjari cha Kaunti', plain: 'Back to Counties' },
  'county.page.follow_money_short': { en: 'Follow the Money', sw: 'Fuatilia Pesa', plain: 'Follow the Money' },
  'county.page.all_counties_short': { en: 'All Counties', sw: 'Kaunti Zote', plain: 'All Counties' },
  'county.page.back_to_home_map': { en: 'Back to map', sw: 'Rudi kwa ramani', plain: 'Back to map' },

  // Hero
  'county.hero.eyebrow': { en: 'County Government · Kenya', sw: 'Serikali ya Kaunti · Kenya', plain: 'County Government · Kenya' },
  'county.hero.residents': { en: 'residents', sw: 'wakazi', plain: 'residents' },
  'county.hero.economy_suffix': { en: 'economy', sw: 'uchumi', plain: 'economy' },
  'county.hero.governor_short': { en: 'Gov.', sw: 'Gav.', plain: 'Gov.' },
  'county.hero.fy_badge': { en: 'Financial data from', sw: 'Data ya kifedha kutoka', plain: 'Money data from' },

  // Quick KPI strip (hero glassy strip)
  'county.hero.kpi.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'county.hero.kpi.execution': { en: 'Execution', sw: 'Utekelezaji', plain: 'Spent' },
  'county.hero.kpi.total_debt': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },
  'county.hero.kpi.pending_bills': { en: 'Pending Bills', sw: 'Ankara Zilizokwama', plain: 'Unpaid Bills' },
  'county.hero.kpi.audit_issues': { en: 'Audit Issues', sw: 'Matatizo ya Ukaguzi', plain: 'Audit Issues' },
  'county.hero.kpi.stalled': { en: 'Stalled', sw: 'Iliyokwama', plain: 'Stuck' },

  // Tabs (extra)
  'county.tab.money': { en: 'Follow the Money', sw: 'Fuatilia Pesa', plain: 'Follow the Money' },
  'county.tab.budget_debt': { en: 'Budget & Debt', sw: 'Bajeti na Deni', plain: 'Budget & Debt' },
  'county.tab.audit_findings': { en: 'Audit Findings', sw: 'Matokeo ya Ukaguzi', plain: 'Audit Findings' },
  'county.tab.accountability': { en: 'Accountability', sw: 'Uwajibikaji', plain: 'Accountability' },

  // Budget execution hero (overview)
  'county.overview.budget_execution': { en: 'Budget Execution', sw: 'Utekelezaji wa Bajeti', plain: 'Money Spent' },
  'county.overview.utilized_suffix': { en: 'utilized', sw: 'imetumika', plain: 'spent' },
  'county.overview.spent_of': { en: 'spent of', sw: 'imetumika kati ya', plain: 'spent of' },
  'county.overview.allocated_suffix': { en: 'allocated', sw: 'iliyotengwa', plain: 'planned' },
  // This label sat ~200px below the page's own disclaimer saying these figures
  // are "Modelled estimate — NOT official Controller of Budget figures", and
  // Fallback only. The API now returns data_sources.budget describing the rows
  // it actually selected — CoB BIRR aggregates where the parse landed, CRA
  // model where it did not — and OverviewTab renders that. This string is used
  // only when the API omits the field, so it states the weaker case.
  'county.overview.source_cob': {
    en: 'Modelled from the CRA equitable-share formula',
    sw: 'Imekadiriwa kwa fomula ya mgao sawa ya CRA',
    plain: 'Worked out using the CRA sharing formula, not read from a report',
  },

  // Debt position card
  'county.overview.debt_position': { en: 'Debt Position', sw: 'Hali ya Deni', plain: 'What the County Owes' },
  'county.overview.debt_total': { en: 'Total debt', sw: 'Deni jumla', plain: 'Total owed' },
  'county.overview.debt_to_budget': { en: 'Debt-to-budget', sw: 'Deni-kwa-bajeti', plain: 'Debt vs. budget' },
  'county.overview.debt_pending': { en: 'Pending bills', sw: 'Ankara zilizokwama', plain: 'Unpaid bills' },
  'county.overview.sustain.sustainable': { en: 'Sustainable', sw: 'Endelevu', plain: 'Healthy' },
  'county.overview.sustain.moderate': { en: 'Moderate Risk', sw: 'Hatari ya Wastani', plain: 'Medium Risk' },
  'county.overview.sustain.at_risk': { en: 'At Risk', sw: 'Katika Hatari', plain: 'At Risk' },

  // Audit snapshot banner
  'county.overview.audit_snapshot': { en: 'Audit Snapshot', sw: 'Muhtasari wa Ukaguzi', plain: 'Audit Snapshot' },
  'county.overview.sev_critical_lower': { en: 'critical', sw: 'muhimu sana', plain: 'serious' },
  'county.overview.sev_warning_lower': { en: 'warning', sw: 'onyo', plain: 'warning' },
  'county.overview.sev_info_lower': { en: 'info', sw: 'taarifa', plain: 'note' },
  'county.overview.total_amount_involved': { en: 'Total amount involved', sw: 'Kiasi jumla kinachohusika', plain: 'Total money involved' },

  // Missing funds banner
  'county.overview.missing_unaccounted': { en: 'Unaccounted', sw: 'Haikuhesabika', plain: 'Missing' },
  'county.overview.cases_oag': { en: 'cases identified by OAG', sw: 'kesi zilizogunduliwa na Mkaguzi Mkuu', plain: 'cases the auditor flagged' },

  // Overview profile KPIs
  'county.overview.kpi.total_revenue': { en: 'Total Revenue', sw: 'Mapato Jumla', plain: 'Total Money In' },
  'county.overview.kpi.local_prefix': { en: 'Local:', sw: 'Ya ndani:', plain: 'Local:' },
  'county.overview.kpi.census': { en: 'Census', sw: 'Sensa', plain: 'Census' },
  'county.overview.kpi.na': { en: 'N/A', sw: 'Haipo', plain: 'None' },
  'county.overview.key_challenges': { en: 'Key Challenges', sw: 'Changamoto Kuu', plain: 'Main Problems' },
  'county.overview.challenges_generic_note': { en: "Representative challenges common across many counties — not derived from this county's specific records.", sw: 'Changamoto za kawaida katika kaunti nyingi — si kutoka kwa rekodi mahususi za kaunti hii.', plain: 'Common problems in many counties — not specific to this one.' },

  // Stalled projects summary (overview)
  'county.overview.stalled_n': { en: 'Stalled Project', sw: 'Mradi Uliokwama', plain: 'Stuck Project' },
  'county.overview.stalled_n_plural': { en: 'Stalled Projects', sw: 'Miradi Iliyokwama', plain: 'Stuck Projects' },
  'county.overview.contracted_total': { en: 'Total contracted', sw: 'Jumla ya mikataba', plain: 'Total promised' },
  'county.overview.paid': { en: 'Paid', sw: 'Imelipwa', plain: 'Paid' },
  'county.overview.disbursed': { en: 'disbursed', sw: 'iliyotolewa', plain: 'paid out' },
  'county.overview.see_projects_tab': { en: 'See the Projects tab for full details.', sw: 'Tazama kichupo cha Miradi kwa maelezo kamili.', plain: 'Open the Projects tab for more.' },

  // Budget tab
  'county.budget.summary': { en: 'Budget Summary', sw: 'Muhtasari wa Bajeti', plain: 'Budget Summary' },
  'county.budget.total_allocated': { en: 'Total Allocated', sw: 'Jumla Iliyotengwa', plain: 'Total Planned' },
  'county.budget.total_spent': { en: 'Total Spent', sw: 'Jumla Iliyotumika', plain: 'Total Spent' },
  'county.budget.execution_suffix': { en: 'execution', sw: 'utekelezaji', plain: 'spent' },
  'county.budget.unavailable': { en: 'Unavailable', sw: 'Haipatikani', plain: 'Not available' },
  'county.budget.not_classified': { en: 'Not classified in source data', sw: 'Haijaainishwa katika data ya chanzo', plain: 'Not split in the source' },

  // Sector spending section
  'county.budget.sector_spending': { en: 'Sector Spending', sw: 'Matumizi kwa Sekta', plain: 'Spending by Area' },
  'county.budget.sector_explore_hint': { en: 'Top {n} sectors · hover to explore allocation vs. spend', sw: 'Sekta {n} za juu · weka kipanya kuona mipango na matumizi', plain: 'Top {n} areas · hover to see planned vs. spent' },
  'county.budget.legend_allocated': { en: 'Allocated', sw: 'Iliyotengwa', plain: 'Planned' },
  'county.budget.legend_spent': { en: 'Spent', sw: 'Iliyotumika', plain: 'Spent' },
  'county.budget.top_10_sectors': { en: 'Top 10 Sectors', sw: 'Sekta 10 za Juu', plain: 'Top 10 Areas' },
  'county.budget.allocated_lower': { en: 'allocated', sw: 'iliyotengwa', plain: 'planned' },
  'county.budget.spent_lower': { en: 'spent', sw: 'iliyotumika', plain: 'spent' },
  'county.budget.of_top_10': { en: 'of top 10', sw: 'ya 10 za juu', plain: 'of top 10' },
  'county.budget.executed_suffix': { en: 'executed', sw: 'imetumika', plain: 'spent' },

  // Debt breakdown
  'county.budget.debt_breakdown': { en: 'Debt Breakdown', sw: 'Uchanganuzi wa Deni', plain: 'Debt Breakdown' },
  'county.budget.of_total_debt': { en: 'of total debt', sw: 'ya deni jumla', plain: 'of total debt' },
  'county.budget.total_debt_label': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },

  // Pending bills (budget tab)
  'county.budget.pending_bills_title': { en: 'Pending Bills', sw: 'Ankara Zilizokwama', plain: 'Unpaid Bills' },
  'county.budget.pending_by_type': { en: 'By Type', sw: 'Kwa Aina', plain: 'By Type' },
  'county.budget.pending_aging': { en: 'Aging', sw: 'Umri wa Deni', plain: 'How old' },
  'county.budget.pending_fallback': { en: 'This county has {amount} in pending bills. Detailed breakdown data will be available once the county reports are processed.', sw: 'Kaunti hii ina {amount} katika ankara zilizokwama. Maelezo zaidi yatapatikana mara tu ripoti zitakapochakatwa.', plain: 'This county has {amount} in unpaid bills. More details will show once the reports are processed.' },

  // Audit tab
  'county.audit.intro_title': { en: 'What are audit findings?', sw: 'Matokeo ya ukaguzi ni nini?', plain: 'What are audit findings?' },
  'county.audit.intro_body': {
    en: 'The Office of the Auditor-General examines how your county government spends public money. When they find problems — like missing funds, irregular spending, or poor record-keeping — they report them as "audit findings." Each finding below shows what went wrong, how much money is involved, and the current status of the issue.',
    sw: 'Ofisi ya Mkaguzi Mkuu huchunguza jinsi serikali ya kaunti inavyotumia pesa za umma. Wanapopata matatizo — kama pesa zilizopotea, matumizi yasiyo sahihi, au rekodi duni — huripoti kama "matokeo ya ukaguzi." Kila matokeo hapa chini yanaonyesha lililoenda vibaya, kiasi cha pesa, na hali ya sasa ya suala.',
    plain: 'The Auditor-General checks how your county spends public money. When they find problems — missing money, rule-breaking, or bad records — they call these "audit findings." Each one shows what went wrong, how much money is involved, and what\u2019s being done about it.',
  },
  'county.audit.kpi_total_findings': { en: 'Total Findings', sw: 'Jumla ya Matokeo', plain: 'Total Findings' },
  'county.audit.kpi_money_questioned': { en: 'Total Money Questioned', sw: 'Jumla ya Pesa Inayohojiwa', plain: 'Money Questioned' },
  'county.audit.kpi_critical_issues': { en: 'Critical Issues', sw: 'Matatizo Muhimu Sana', plain: 'Serious Issues' },
  'county.audit.kpi_resolved': { en: 'Resolved', sw: 'Yaliyoshughulikiwa', plain: 'Fixed' },
  'county.audit.findings_by_category': { en: 'Findings by Category', sw: 'Matokeo kwa Kategoria', plain: 'Findings by Type' },
  'county.audit.cat.financial_irregularity': { en: 'Financial Irregularity', sw: 'Ukiukaji wa Kifedha', plain: 'Rule-breaking with Money' },
  'county.audit.cat.asset_management': { en: 'Asset Management', sw: 'Usimamizi wa Mali', plain: 'Property Management' },
  'county.audit.cat.missing_funds': { en: 'Missing / Unaccounted Funds', sw: 'Pesa Zilizopotea / Zisizohesabika', plain: 'Missing Money' },
  'county.audit.cat.procurement': { en: 'Procurement Issues', sw: 'Matatizo ya Manunuzi', plain: 'Buying Problems' },
  'county.audit.cat.payroll': { en: 'Payroll Issues', sw: 'Matatizo ya Mshahara', plain: 'Payroll Problems' },
  'county.audit.cat.revenue_collection': { en: 'Revenue Collection', sw: 'Ukusanyaji wa Mapato', plain: 'Tax Collection' },
  'county.audit.cat.other': { en: 'Other', sw: 'Nyingine', plain: 'Other' },
  'county.audit.finding_singular': { en: 'finding', sw: 'matokeo', plain: 'finding' },
  'county.audit.finding_plural': { en: 'findings', sw: 'matokeo', plain: 'findings' },
  'county.audit.show_all_categories': { en: '← Show all categories', sw: '← Onyesha kategoria zote', plain: '← Show all types' },
  'county.audit.status.under_review': { en: 'Under Review', sw: 'Inachunguzwa', plain: 'Being Checked' },
  'county.audit.status.escalated': { en: 'Escalated', sw: 'Imepandishwa', plain: 'Raised Higher' },
  'county.audit.status.resolved': { en: 'Resolved', sw: 'Imeshughulikiwa', plain: 'Fixed' },
  'county.audit.status.pending': { en: 'Pending', sw: 'Inasubiri', plain: 'Waiting' },
  'county.audit.status.open': { en: 'Open', sw: 'Imefunguliwa', plain: 'Open' },
  'county.audit.missing_unaccounted': { en: 'Missing / Unaccounted', sw: 'Zimepotea / Hazihesabiki', plain: 'Missing Money' },
  'county.audit.cases_flagged': { en: 'case(s) flagged by the Auditor-General as money that cannot be accounted for.', sw: 'kesi zilizogunduliwa na Mkaguzi Mkuu kama pesa ambazo haziwezi kuthibitishwa.', plain: 'cases the auditor says cannot be explained.' },
  'county.audit.all_findings_title': { en: 'All Audit Findings', sw: 'Matokeo Yote ya Ukaguzi', plain: 'All Audit Findings' },
  'county.audit.category_findings_suffix': { en: 'Findings', sw: 'Matokeo', plain: 'Findings' },
  'county.audit.showing_of': { en: 'Showing 20 of {n} findings', sw: 'Inaonyesha 20 kati ya matokeo {n}', plain: 'Showing 20 of {n} findings' },
  'county.audit.what_means': { en: 'What does this mean?', sw: 'Hii inamaanisha nini?', plain: 'What does this mean?' },
  'county.audit.recommendation': { en: 'Auditor\u2019s Recommendation', sw: 'Pendekezo la Mkaguzi', plain: 'Auditor\u2019s Fix' },
  'county.audit.fy_prefix': { en: 'FY', sw: 'MF', plain: 'FY' },
  'county.audit.ref_prefix': { en: 'Ref:', sw: 'Rejea:', plain: 'Ref:' },

  // Explain blocks (status)
  'county.audit.status_explain.resolved': { en: '✅ This issue has been addressed by the county government.', sw: '✅ Suala hili limeshughulikiwa na serikali ya kaunti.', plain: '✅ The county fixed this.' },
  'county.audit.status_explain.escalated': { en: '⚠️ This issue has been escalated for further investigation or action.', sw: '⚠️ Suala hili limepandishwa kwa uchunguzi au hatua zaidi.', plain: '⚠️ This was sent up for more investigation.' },
  'county.audit.status_explain.under_review': { en: '🔍 This issue is currently being reviewed by the relevant authorities.', sw: '🔍 Suala hili linachunguzwa na mamlaka husika.', plain: '🔍 The authorities are looking into this.' },
  'county.audit.status_explain.pending': { en: '⏳ This issue is awaiting action from the county government.', sw: '⏳ Suala hili linasubiri hatua kutoka kwa serikali ya kaunti.', plain: '⏳ Waiting for the county to act.' },
  'county.audit.status_explain.default': { en: '📋 Status of this issue is being tracked.', sw: '📋 Hali ya suala hili inafuatiliwa.', plain: '📋 This is being tracked.' },

  // What-it-means explanations by category
  'county.audit.explain.missing_funds': { en: 'The auditors found KES {amount} that the county government cannot explain where it went. This money was meant for public services.', sw: 'Wakaguzi walipata KES {amount} ambazo serikali ya kaunti haiwezi kueleza zilikoenda. Pesa hizi zilikusudiwa huduma za umma.', plain: 'The auditors found KES {amount} the county cannot explain. This money was for public services.' },
  'county.audit.explain.financial_irregularity': { en: 'The county spent KES {amount} without proper documentation or following financial rules. This makes it impossible to verify the money was used correctly.', sw: 'Kaunti ilitumia KES {amount} bila nyaraka sahihi au kufuata sheria za kifedha. Hii inafanya isiwezekane kuthibitisha pesa zilitumika vizuri.', plain: 'The county spent KES {amount} without proper paperwork or following the rules. We can\u2019t tell if it was spent properly.' },
  'county.audit.explain.asset_management': { en: 'County assets worth KES {amount} are not being properly tracked, insured, or maintained — putting public property at risk.', sw: 'Mali za kaunti zenye thamani ya KES {amount} hazitunzwi, hazijabima, au hazitunzwi vizuri — zikiiweka mali ya umma katika hatari.', plain: 'County property worth KES {amount} is not tracked, insured, or cared for — putting it at risk.' },
  'county.audit.explain.procurement': { en: 'KES {amount} were spent on purchases that didn\u2019t follow proper procurement rules — potentially meaning taxpayers didn\u2019t get value for money.', sw: 'KES {amount} zilitumika kwa manunuzi yasiyofuata sheria za manunuzi — kumaanisha walipa kodi hawakupata thamani.', plain: 'KES {amount} was spent on buying things without following the rules — taxpayers may not have gotten a fair deal.' },
  'county.audit.explain.payroll': { en: 'There are irregularities in how county staff are paid, involving KES {amount}. This could mean ghost workers or unauthorized payments.', sw: 'Kuna makosa katika jinsi wafanyakazi wa kaunti wanavyolipwa, yanayohusisha KES {amount}. Inaweza kumaanisha wafanyakazi wa uongo au malipo yasiyoidhinishwa.', plain: 'Staff pay has problems, involving KES {amount}. It could mean fake workers or unapproved payments.' },
  'county.audit.explain.default': { en: 'The auditors flagged an issue with how public money was managed{amount_clause}. This requires attention to ensure taxpayer money is protected.', sw: 'Wakaguzi waligundua tatizo na jinsi pesa za umma zilivyosimamiwa{amount_clause}. Hii inahitaji umakini ili kulinda pesa za walipa kodi.', plain: 'The auditors flagged how public money was handled{amount_clause}. This needs attention to protect taxpayer money.' },
  'county.audit.explain.amount_clause': { en: ', involving KES {amount}', sw: ', inayohusisha KES {amount}', plain: ', involving KES {amount}' },
  'county.audit.explain.undisclosed_amount': { en: 'an undisclosed amount', sw: 'kiasi kisichojulikana', plain: 'an undisclosed amount' },
  'county.audit.explain.undisclosed_value': { en: 'an undisclosed value', sw: 'thamani isiyojulikana', plain: 'an undisclosed value' },
  'county.audit.explain.amount_fallback': { en: 'an amount', sw: 'kiasi', plain: 'an amount' },
  'county.audit.explain.funds_fallback': { en: 'Funds', sw: 'Pesa', plain: 'Money' },
  'county.audit.explain.undisclosed_amounts': { en: 'undisclosed amounts', sw: 'viwango visivyojulikana', plain: 'undisclosed amounts' },

  // Projects tab
  'county.projects.none_title': { en: 'No stalled or significantly delayed projects', sw: 'Hakuna miradi iliyokwama au kuchelewa kwa kiasi kikubwa', plain: 'No stuck or very late projects' },
  'county.projects.none_body': { en: 'All audited development projects are progressing within acceptable parameters.', sw: 'Miradi yote ya maendeleo iliyokaguliwa inaendelea ndani ya viwango vinavyokubalika.', plain: 'All checked projects are moving along fine.' },
  'county.projects.kpi_stalled': { en: 'Stalled / Delayed', sw: 'Iliyokwama / Iliyochelewa', plain: 'Stuck / Late' },
  'county.projects.kpi_contracted': { en: 'Contracted Value', sw: 'Thamani ya Mkataba', plain: 'Promised Value' },
  'county.projects.kpi_paid': { en: 'Already Paid', sw: 'Tayari Imelipwa', plain: 'Already Paid' },
  'county.projects.disbursed_suffix': { en: 'disbursed', sw: 'iliyotolewa', plain: 'paid out' },
  'county.projects.status_stalled': { en: 'Stalled', sw: 'Imekwama', plain: 'Stuck' },
  'county.projects.status_delayed': { en: 'Delayed', sw: 'Imechelewa', plain: 'Late' },
  'county.projects.complete_suffix': { en: 'complete', sw: 'imekamilika', plain: 'done' },
  'county.projects.started': { en: 'Started', sw: 'Ilianza', plain: 'Started' },
  'county.projects.expected': { en: 'Expected', sw: 'Inatarajiwa', plain: 'Expected' },

  // Accountability tab
  'county.acct.failed_load': { en: 'Failed to load accountability data', sw: 'Imeshindwa kupakia data ya uwajibikaji', plain: 'Could not load accountability data' },
  'county.acct.grade_label': { en: 'Accountability Grade', sw: 'Alama ya Uwajibikaji', plain: 'Accountability Grade' },
  'county.acct.grade_excellent': { en: 'Excellent', sw: 'Bora Sana', plain: 'Excellent' },
  'county.acct.grade_good': { en: 'Good', sw: 'Nzuri', plain: 'Good' },
  'county.acct.grade_fair': { en: 'Fair', sw: 'Wastani', plain: 'OK' },
  'county.acct.grade_needs_improvement': { en: 'Needs Improvement', sw: 'Inahitaji Kuboreshwa', plain: 'Needs Work' },
  'county.acct.grade_poor': { en: 'Poor', sw: 'Mbaya', plain: 'Poor' },
  // An ungraded county is NOT a C. Added after review on PR #135: the card
  // fell back to the C style and rendered "Fair" for a county whose findings
  // were all withheld for lack of a source document.
  'county.acct.grade_ungraded': { en: 'Not yet assessed', sw: 'Haijatathminiwa bado', plain: 'Not graded yet' },
  'county.acct.grade_ungraded_description': {
    en: 'No grade can be given yet: this county has no findings that trace to a source document a reader can open. An absent grade is not a low grade.',
    sw: 'Hakuna alama bado: kaunti hii haina matokeo yanayothibitishwa na hati chanzo. Kukosa alama si alama mbaya.',
    plain: 'We cannot grade this county yet — none of its findings link to a document you can open. No grade does not mean a bad grade.',
  },
  'county.acct.grade_description': {
    en: 'Scored out of 100 across five dimensions: audit opinions, finding volume & severity, recurring issues, unresolved items, flagged spend, and absorption. Grade bands: A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, else F.',
    sw: 'Inapimwa kati ya 100 katika vipimo vitano: maoni ya ukaguzi, idadi na uzito wa matokeo, matatizo yanayojirudia, masuala yasiyoshughulikiwa, matumizi yaliyogunduliwa, na utekelezaji. Alama: A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, vinginevyo F.',
    plain: 'Scored out of 100 on five things: audit results, how many and how bad the findings are, repeat problems, open issues, flagged money, and spending rate. Grades: A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, else F.',
  },
  'county.acct.how_calculated': { en: 'How this grade was calculated', sw: 'Jinsi alama hii ilihesabiwa', plain: 'How this grade was figured out' },
  'county.acct.how_calc_intro': { en: 'Starting from 100, we subtract points for each risk factor. Mouse-over each row for the specific threshold triggered.', sw: 'Kuanzia 100, tunapunguza pointi kwa kila sababu ya hatari. Weka kipanya juu ya kila mstari kuona kiwango kilichosababisha.', plain: 'We start at 100 and take away points for each problem. Hover any row to see what triggered it.' },
  'county.acct.score_label': { en: 'Score', sw: 'Alama', plain: 'Score' },
  'county.acct.no_penalties': { en: 'No penalty factors triggered — clean accountability record.', sw: 'Hakuna sababu za adhabu — rekodi safi ya uwajibikaji.', plain: 'No problems found — clean record.' },
  'county.acct.calc_footnote': { en: 'Penalties are derived from OAG audit records and COB budget implementation reports. "Unresolved" counts any finding not explicitly resolved, closed, dismissed, or settled — including items marked "Under Review" or "Escalated".', sw: 'Adhabu zinatokana na rekodi za ukaguzi wa OAG na ripoti za utekelezaji wa bajeti za COB. "Yasiyoshughulikiwa" inajumuisha matokeo yoyote ambayo hayajafungwa rasmi — pamoja na yale yaliyoandikwa "Inachunguzwa" au "Imepandishwa".', plain: 'Penalties come from the Auditor-General\u2019s records and the Controller of Budget\u2019s reports. "Unresolved" means any finding not clearly closed — including ones marked "Being Checked" or "Raised Higher".' },
  'county.acct.pt_suffix': { en: 'pt', sw: 'pt', plain: 'pt' },
  'county.acct.impact_positive': { en: 'Positive', sw: 'Chanya', plain: 'Good' },
  'county.acct.impact_minor': { en: 'Minor', sw: 'Ndogo', plain: 'Small' },
  'county.acct.impact_moderate': { en: 'Moderate', sw: 'Wastani', plain: 'Medium' },
  'county.acct.impact_major': { en: 'Major', sw: 'Kubwa', plain: 'Big' },

  // Accountability key metrics
  'county.acct.kpi.total_flagged': { en: 'Total Flagged', sw: 'Jumla Iliyogunduliwa', plain: 'Total Flagged' },
  'county.acct.kpi.pct_of_budget': { en: 'of budget', sw: 'ya bajeti', plain: 'of budget' },
  'county.acct.kpi.audit_findings': { en: 'Audit Findings', sw: 'Matokeo ya Ukaguzi', plain: 'Audit Findings' },
  'county.acct.kpi.critical_lower': { en: 'critical', sw: 'muhimu', plain: 'serious' },
  'county.acct.kpi.warning_lower': { en: 'warning', sw: 'onyo', plain: 'warning' },
  'county.acct.kpi.unresolved': { en: 'Unresolved', sw: 'Hazijashughulikiwa', plain: 'Not Fixed' },
  'county.acct.kpi.recurring': { en: 'recurring', sw: 'zinazojirudia', plain: 'repeat' },
  'county.acct.kpi.absorption_rate': { en: 'Absorption Rate', sw: 'Kiwango cha Matumizi', plain: 'Spending Rate' },
  'county.acct.kpi.absorption_sub': { en: 'Spent / allocated', sw: 'Iliyotumika / iliyotengwa', plain: 'Spent / planned' },

  // Opinion history table
  'county.acct.opinion_history': { en: 'Audit Opinion History', sw: 'Historia ya Maoni ya Ukaguzi', plain: 'Past Audit Results' },
  'county.acct.table.year': { en: 'Year', sw: 'Mwaka', plain: 'Year' },
  'county.acct.table.opinion': { en: 'Opinion', sw: 'Maoni', plain: 'Result' },
  'county.acct.opinion.unqualified': { en: 'Unqualified', sw: 'Safi', plain: 'Clean' },
  'county.acct.opinion.qualified': { en: 'Qualified', sw: 'Ya Kuhitimu', plain: 'Some Issues' },
  'county.acct.opinion.adverse': { en: 'Adverse', sw: 'Mbaya', plain: 'Bad' },
  'county.acct.opinion.disclaimer': { en: 'Disclaimer', sw: 'Kanusho', plain: 'Unable to Audit' },

  // Peer comparison
  'county.acct.peer.title': { en: 'Peer Comparison', sw: 'Ulinganisho wa Wenzao', plain: 'Compared to Similar Counties' },
  'county.acct.peer.vs_region': { en: 'vs {region} Average', sw: 'dhidi ya Wastani wa {region}', plain: 'vs {region} Average' },
  'county.acct.peer.vs_bracket': { en: 'vs {bracket} Average', sw: 'dhidi ya Wastani wa {bracket}', plain: 'vs {bracket} Average' },
  'county.acct.peer.above': { en: 'Above peer average', sw: 'Juu ya wastani wa wenzao', plain: 'Above average' },
  'county.acct.peer.below': { en: 'Below peer average', sw: 'Chini ya wastani wa wenzao', plain: 'Below average' },
  'county.acct.peer.above_bracket': { en: 'Above bracket average', sw: 'Juu ya wastani wa kundi', plain: 'Above group average' },
  'county.acct.peer.below_bracket': { en: 'Below bracket average', sw: 'Chini ya wastani wa kundi', plain: 'Below group average' },
  'county.acct.peer.this_county': { en: 'This county', sw: 'Kaunti hii', plain: 'This county' },
  'county.acct.peer.region_avg': { en: 'Region avg', sw: 'Wastani wa eneo', plain: 'Region average' },
  'county.acct.peer.region_avg_grade': { en: 'Region avg grade', sw: 'Alama ya wastani ya eneo', plain: 'Region average grade' },
  'county.acct.peer.bracket_avg': { en: 'Bracket avg', sw: 'Wastani wa kundi', plain: 'Group average' },
  'county.acct.peer.region_fallback': { en: 'Region', sw: 'Eneo', plain: 'Region' },
  'county.acct.peer.bracket_fallback': { en: 'Population Bracket', sw: 'Kundi la Idadi ya Watu', plain: 'Population Group' },
  'county.acct.peer.footer_note': { en: 'Higher flagged amounts indicate more audit issues. Lower is better.', sw: 'Kiasi kikubwa kilichogunduliwa kinaashiria matatizo zaidi ya ukaguzi. Chini ni bora.', plain: 'Bigger flagged amounts mean more audit problems. Lower is better.' },

  // Follow the money tab
  'county.money.header_prefix': { en: 'Follow the Money', sw: 'Fuatilia Pesa', plain: 'Follow the Money' },
  'county.money.subtitle': { en: 'Trace how public funds flow from allocation to expenditure', sw: 'Fuatilia jinsi pesa za umma zinavyosafiri kutoka zilivyotengwa hadi zilivyotumika', plain: 'See how public money moves from planned to spent' },

  // Sources footer
  'county.sources.prefix': { en: 'Sources:', sw: 'Vyanzo:', plain: 'Sources:' },
  'county.sources.budget': { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  'county.sources.audit': { en: 'Audit', sw: 'Ukaguzi', plain: 'Audit' },
  'county.sources.debt': { en: 'Debt', sw: 'Deni', plain: 'Debt' },
  'county.sources.population': { en: 'Population', sw: 'Idadi ya Watu', plain: 'People' },

  // Health score modal
  'county.healthmodal.title': { en: 'Financial Health Score', sw: 'Alama ya Afya ya Kifedha', plain: 'Money Health Score' },
  'county.healthmodal.how_calc': { en: 'How It\u2019s Calculated', sw: 'Jinsi Inavyohesabiwa', plain: 'How it\u2019s figured out' },
  'county.healthmodal.derived_from': { en: 'The health score is derived from the county\u2019s budget execution rate — how much of the allocated budget was actually spent in the fiscal year.', sw: 'Alama ya afya inatokana na kiwango cha utekelezaji wa bajeti ya kaunti — kiasi gani cha bajeti iliyotengwa kilitumika kweli mwaka huo wa fedha.', plain: 'The health score comes from how much of the planned budget the county really spent this year.' },
  'county.healthmodal.rule_1': { en: 'If utilization ≤ 95%:', sw: 'Ikiwa matumizi ≤ 95%:', plain: 'If spending ≤ 95%:' },
  'county.healthmodal.rule_1_body': { en: 'Score = utilization percentage', sw: 'Alama = asilimia ya matumizi', plain: 'Score = the spending percentage' },
  'county.healthmodal.rule_2': { en: 'If 95% < utilization ≤ 100%:', sw: 'Ikiwa 95% < matumizi ≤ 100%:', plain: 'If 95% < spending ≤ 100%:' },
  'county.healthmodal.rule_2_body': { en: 'Score = 90 (near-perfect execution)', sw: 'Alama = 90 (utekelezaji karibu kamili)', plain: 'Score = 90 (almost perfect)' },
  'county.healthmodal.rule_3': { en: 'If utilization > 100% (overspend):', sw: 'Ikiwa matumizi > 100% (matumizi ya ziada):', plain: 'If spending > 100% (overspend):' },
  'county.healthmodal.rule_3_body': { en: 'Score = 80 − overspend %, penalizing excess spending', sw: 'Alama = 80 − % ya matumizi ya ziada, kuadhibu matumizi ya ziada', plain: 'Score = 80 minus the overspend %, so going over the budget is penalized' },
  'county.healthmodal.max_note': { en: 'A score of 95 is the maximum — counties that spend close to their budget without overspending demonstrate the best fiscal discipline.', sw: 'Alama ya 95 ndiyo ya juu zaidi — kaunti zinazotumia karibu bajeti yao bila kupita kiasi zinaonyesha nidhamu bora ya kifedha.', plain: 'The highest possible score is 95 — counties that spend close to their budget without going over do best.' },
  'county.healthmodal.this_county_numbers': { en: 'This County\u2019s Numbers', sw: 'Nambari za Kaunti Hii', plain: 'This County\u2019s Numbers' },
  'county.healthmodal.row.budget_allocated': { en: 'Budget Allocated', sw: 'Bajeti Iliyotengwa', plain: 'Budget Planned' },
  'county.healthmodal.row.budget_spent': { en: 'Budget Spent', sw: 'Bajeti Iliyotumika', plain: 'Budget Spent' },
  'county.healthmodal.row.execution_rate': { en: 'Execution Rate', sw: 'Kiwango cha Utekelezaji', plain: 'Spending Rate' },
  'county.healthmodal.row.pending_bills': { en: 'Pending Bills', sw: 'Ankara Zilizokwama', plain: 'Unpaid Bills' },
  'county.healthmodal.row.total_debt': { en: 'Total Debt', sw: 'Deni Jumla', plain: 'Total Debt' },
  'county.healthmodal.row.audit_issues': { en: 'Audit Issues', sw: 'Matatizo ya Ukaguzi', plain: 'Audit Issues' },
  'county.healthmodal.row.stalled_projects': { en: 'Stalled Projects', sw: 'Miradi Iliyokwama', plain: 'Stuck Projects' },
  'county.healthmodal.grade_scale': { en: 'Grade Scale', sw: 'Kiwango cha Alama', plain: 'Grade Scale' },
  'county.healthmodal.current': { en: 'Current', sw: 'Ya Sasa', plain: 'Now' },
  'county.healthmodal.source_line': { en: 'Source: Office of the Auditor General · County financial statements', sw: 'Chanzo: Ofisi ya Mkaguzi Mkuu · Taarifa za kifedha za kaunti', plain: 'Source: Auditor-General · County money reports' },

  // Officials card (extras beyond county.officials.*)
  'county.officials.card_title': { en: 'Who Runs This County', sw: 'Nani Anaongoza Kaunti Hii', plain: 'Who Runs the County' },
  'county.officials.card_subtitle': { en: 'Elected and appointed offices with direct influence over county finances.', sw: 'Ofisi zilizochaguliwa na kuteuliwa zenye ushawishi wa moja kwa moja juu ya fedha za kaunti.', plain: 'The top people who decide how the county\u2019s money is used.' },
  'county.officials.official_site': { en: 'Official site', sw: 'Tovuti rasmi', plain: 'Official site' },
  'county.officials.directory_beta': { en: 'Officials directory in beta — coverage expanding across counties.', sw: 'Orodha ya viongozi bado inajaribiwa — tunaongeza kaunti zaidi.', plain: 'Officials list still growing — we add more counties each week.' },
  'county.officials.title.governor': { en: 'Governor', sw: 'Gavana', plain: 'Governor' },
  'county.officials.title.deputy_governor': { en: 'Deputy Governor', sw: 'Naibu Gavana', plain: 'Deputy Governor' },
  'county.officials.title.cec_finance': { en: 'CEC — Finance', sw: 'CEC — Fedha', plain: 'Finance Chief' },
  'county.officials.title.assembly_speaker': { en: 'Assembly Speaker', sw: 'Spika wa Bunge', plain: 'Assembly Speaker' },
  'county.officials.since_word': { en: 'since', sw: 'tangu', plain: 'since' },

  // Grade badge tooltips
  'county.grade.health_tooltip': { en: 'Financial health — budget execution, debt, pending bills. Click for methodology.', sw: 'Afya ya kifedha — utekelezaji wa bajeti, deni, ankara. Bonyeza kwa maelezo.', plain: 'Money health — budget, debt, unpaid bills. Click to see how it\u2019s scored.' },
  'county.grade.audit_tooltip': { en: 'Accountability — audit findings, unresolved items, flagged spend. Click to view breakdown.', sw: 'Uwajibikaji — matokeo ya ukaguzi, masuala yasiyoshughulikiwa, matumizi yaliyogunduliwa. Bonyeza kuona maelezo.', plain: 'Accountability — audit findings, open issues, flagged money. Click to see details.' },

  // PDF export
  'county.pdf.report_suffix': { en: 'County Report', sw: 'Ripoti ya Kaunti', plain: 'County Report' },

  // Role descriptions (full)
  'county.officials.desc.governor': { en: 'Chief executive of the county government. Elected directly by voters every five years.', sw: 'Mkuu wa serikali ya kaunti. Anachaguliwa moja kwa moja na wapiga kura kila baada ya miaka mitano.', plain: 'Leader of the county. Elected every 5 years.' },
  'county.officials.desc.deputy_governor': { en: 'Deputy to the Governor, elected on the same ticket. Steps in when the Governor is away or vacates office.', sw: 'Naibu wa Gavana, anachaguliwa pamoja naye. Huchukua nafasi pale Gavana hayupo.', plain: 'Second-in-command. Takes over if the Governor is away.' },
  'county.officials.desc.cec_finance': { en: 'County Executive Committee member for Finance — the county-level equivalent of a finance minister. Prepares the budget and oversees spending.', sw: 'Mjumbe wa Kamati Tendaji ya Kaunti wa Fedha — sawa na waziri wa fedha wa kaunti. Huandaa bajeti na husimamia matumizi.', plain: 'In charge of the county\u2019s money — like a finance minister. Writes the budget and watches spending.' },
  'county.officials.desc.assembly_speaker': { en: 'Presides over the County Assembly (the legislative body). Elected by Assembly members.', sw: 'Mwenyekiti wa Bunge la Kaunti. Huchaguliwa na wabunge.', plain: 'Leads the County Assembly. Chosen by assembly members.' },
} as const satisfies Record<string, Translation>;

export type TranslationKey = keyof typeof MESSAGES;

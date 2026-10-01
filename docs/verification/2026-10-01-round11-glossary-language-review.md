# Round 11 glossary language review packet — 2026-10-01

Status: **draft Swahili; competent review outstanding**. This packet prepares [#307](https://github.com/Rodgers31/audit_app/issues/307). The source implementation covers the active contextual InfoTip terms in [#372](https://github.com/Rodgers31/audit_app/issues/372), and safe lookup in [#373](https://github.com/Rodgers31/audit_app/issues/373). Language/render tests establish what readers receive, not fluency, legal equivalence, or language-review acceptance. Do not close #307 or claim full #372 acceptance until a competent Swahili reviewer signs off.

Base: `355c057a6138ed47212a5aab865f4bdf26a02177`. Source of the strings below: `frontend/lib/i18n/messages.ts` at this session's patch. All entries in the next table are new except the shared accessible-label template, financial-health body, and reused title. Inherited entries are unchanged and shown later so the review backlog cannot be mistaken for completed work.

## Intended meanings and review priorities

A fluent Kenyan Swahili reviewer familiar with public accounts should review these together with a competent audit/domain reviewer if needed. Review the complete title, body and rendered question as one unit. Preserve negation, conditional wording, source scope, institutions, dates, numbers and placeholders; propose wording corrections against the exact key, not just a glossary term.

| Term / keys under `glossary.` | Meaning that must survive | Specific terminology to decide |
| --- | --- | --- |
| `debt_to_gdp` | Debt divided by annual GDP; distinguish nominal and present-value measures; same-basis comparisons; ratio alone does not establish distress. | `Pato la Taifa`, `thamani ya kawaida`, `thamani ya sasa`, debt distress. |
| `external_debt`, `domestic_debt` | Use the cited source's classification, date and coverage; currency is not sufficient to classify external debt; a partial register is not the full stock. | Resident/foreign lenders, `wigo`, Treasury bonds vs bills, `hati fungani` / `hati za muda mfupi`. |
| `pending_bills` | Reported unpaid amounts at a date; not borrowed debt; claims may need verification or be disputed; absent is not zero; do not sum snapshots. | `bili` vs `ankara` vs trade payables; `hadi` for as-at; verification and dispute. |
| `budget_execution` | Spending / approved budget for the same body and period; 7 of 10 billion = 70%; low rate does not prove corruption; missing figures are not zero. | Execution/absorption vs implementation, approved allocation, institution/period, uncertainty. |
| `audit_clean` | Opinion is about financial statements of a body/period, with materiality; no guarantee of lawfulness or absence of fraud/theft/loss; findings and compliance conclusions separate. | `yasiyo na masharti` for unqualified/unmodified; `mambo yote muhimu` for materiality; `hoja` and compliance conclusion. Align with existing modified-opinion labels without implying absolution or a theft finding. |
| `outstanding` | Amount still owed at source date/basis; a register line may group creditor/instrument obligations; missing/incomplete is not zero debt. | Balance, creditor vs lender, instrument, row vs loan agreement. |
| `multilateral`, `bilateral`, `commercial` | Lender types; terms depend on agreement/instrument; rows may group agreements. No universal interest-rate or concessionality claim. | `Mkopeshaji wa Kimataifa wa Nchi Nyingi`, government lending agency, private lender, Eurobond. |
| `development_spending`, `recurrent_spending` | Source budget classifications; allocation vs actual; body/period; spending does not prove project completion/value or waste/efficiency. | Development vs recurrent spending, `ubadhirifu`, `ufanisi`, value and project completion. |
| `financial_health` and `county.healthmodal.*` | Site-made 0–100 composite; available inputs only; finding-severity signal, not official OAG opinion/rating; weight 3 equal to other three together when all exist; at least two for A–C; separate accountability score. | `kiashiria cha ukali wa hoja`, County Executive vs Assembly, missing/conflicting evidence, `uzito`, `daraja`. Do not reintroduce the superseded audit-opinion component description. |
| `info_label` | Button asks for the meaning of its displayed title in the selected language. | Grammar/capitalisation of `{title} ni nini?` for every title; retain `{title}` exactly. |

Audit basis consulted fresh on 2026-10-01: [Office of the Auditor-General: audit opinions](https://www.oagkenya.go.ke/faqs/what-do-the-various-audit-opinions-mean/). It describes opinions about accounts and supporting records. This packet distinguishes that accounting opinion from separate findings and legal conclusions. Source semantics also checked at `backend/services/audit_opinions.py`, `backend/services/publication_gate.py` (pending stock selection and absent/zero), `frontend/lib/debt/registerScope.ts` (register scope), and the actual county/debt/budget callers. No production database was queried.

## Exact active glossary strings

`glossary.<term>.title` / `.body` pairs are shown individually. The shared button template and existing financial-health keys are included. Swahili in this table is proposed copy, not reviewed copy.

| Key | English meaning / copy | Proposed Swahili | Plain English |
| --- | --- | --- | --- |
| `glossary.debt_to_gdp.title` | Debt-to-GDP Ratio | Uwiano wa Deni kwa Pato la Taifa | Debt compared with the economy |
| `glossary.debt_to_gdp.body` | Debt as a percentage of annual economic output (GDP), using the debt measure and period stated beside the figure. Nominal debt and present-value debt are different measures; compare ratios or benchmarks only on the same basis. A higher ratio alone does not establish debt distress. | Deni kama asilimia ya pato la uchumi kwa mwaka (GDP), kwa kipimo cha deni na kipindi kilichoelezwa karibu na takwimu. Deni la thamani ya kawaida na deni la thamani ya sasa ni vipimo tofauti; linganisha uwiano au viwango vya marejeo kwa msingi mmoja. Uwiano mkubwa pekee hauthibitishi matatizo ya ulipaji wa deni. | Debt compared with what the economy produces in a year. Check the date and how debt was measured. The amount owed today and the present value of future payments are different, so comparisons need the same measure. This ratio alone cannot tell us whether debts can be paid. |
| `glossary.external_debt.title` | External Debt | Deni la Nje | Debt to lenders abroad |
| `glossary.external_debt.body` | Government debt classified as external in the cited source, including international organisations, other governments and private lenders abroad. It is often in foreign currencies, but currency alone does not determine the classification. Read the source date and coverage before comparing totals. | Deni la serikali lililoainishwa kuwa la nje katika chanzo kilichotajwa, likijumuisha mashirika ya kimataifa, serikali nyingine na wakopeshaji binafsi wa nje. Mara nyingi ni la sarafu za kigeni, lakini sarafu pekee haiamui uainishaji. Angalia tarehe na wigo wa chanzo kabla ya kulinganisha jumla. | Money the government owes to lenders abroad, as grouped by the source. This can include international bodies, other governments and private lenders. It is often owed in foreign currencies. Check the date and what the source covers before comparing amounts. |
| `glossary.domestic_debt.title` | Domestic Debt | Deni la Ndani | Debt to lenders in Kenya |
| `glossary.domestic_debt.body` | Government debt classified as domestic in the cited source, mainly Treasury bonds and bills held through the domestic market. It is generally reported in Kenyan shillings. Use the stated source date and coverage; a partial register is not necessarily the full national debt stock. | Deni la serikali lililoainishwa kuwa la ndani katika chanzo kilichotajwa, hasa hati fungani na hati za muda mfupi za Hazina katika soko la ndani. Kwa kawaida huripotiwa kwa shilingi za Kenya. Tumia tarehe na wigo wa chanzo; rejista yenye sehemu ya taarifa si lazima iwe jumla ya deni la taifa. | Money the government borrows in Kenya, mainly through Treasury bonds and bills. Amounts are usually shown in Kenyan shillings. Check the date and what is included: a list covering only some debt is not the whole national total. |
| `glossary.pending_bills.title` | Pending Bills | Bili Ambazo Hazijalipwa | Unpaid bills |
| `glossary.pending_bills.body` | Unpaid amounts reported as pending bills at a stated date. These are separate from borrowed debt and may include claims still subject to verification or dispute. Check the source, institution, reporting date and notes. Missing information is not zero, and snapshots from different dates must not be added together. | Kiasi ambacho hakijalipwa na kimeripotiwa kama bili ambazo hazijalipwa hadi tarehe iliyotajwa. Hizi ni tofauti na deni la mikopo na zinaweza kujumuisha madai yanayosubiri uhakiki au yenye mgogoro. Angalia chanzo, taasisi, tarehe ya ripoti na maelezo. Taarifa kutopatikana si sawa na sifuri; usijumlishe takwimu za tarehe tofauti. | Bills reported as unpaid on a given date. They are separate from money borrowed. Some claims may still need checks or be disputed. Check who reported them, the date and any notes. Missing information is not zero. Do not add figures from different dates as if they were separate bills. |
| `glossary.budget_execution.title` | Budget Execution Rate | Kiwango cha Matumizi ya Bajeti | Share of the budget spent |
| `glossary.budget_execution.body` | Reported spending divided by the approved budget for the same institution and reporting period. If KES 7 billion is spent from a KES 10 billion budget, the rate is 70%. A low rate alone does not prove corruption; delays, funding shortfalls or incomplete reporting may affect it. Missing figures are not zero. | Matumizi yaliyoripotiwa yakigawanywa kwa bajeti iliyoidhinishwa kwa taasisi na kipindi kimoja cha ripoti. Matumizi ya KES bilioni 7 kutoka bajeti ya KES bilioni 10 ni 70%. Kiwango cha chini pekee hakithibitishi ufisadi; ucheleweshaji, upungufu wa fedha au taarifa zisizokamilika vinaweza kukiathiri. Takwimu kukosekana si sifuri. | How much of the approved budget was spent by the same body in the same period. Spending KES 7 billion from a KES 10 billion budget means 70%. A low rate does not by itself prove corruption. Delays, less funding or missing reports can affect it. Missing figures are not zero. |
| `glossary.audit_clean.title` | Clean Audit Opinion | Maoni ya Ukaguzi Yasiyo na Masharti | Clean audit opinion |
| `glossary.audit_clean.body` | An unqualified or unmodified opinion concerns the financial statements of the audited institution and period: they are fairly presented in all material respects under the applicable reporting framework. It is not a guarantee that every transaction was lawful or that no fraud, theft or loss occurred. Findings and compliance conclusions must be read separately. | Maoni ya ukaguzi yasiyo na masharti yanahusu taarifa za fedha za taasisi na kipindi kilichokaguliwa: zimewasilishwa kwa usahihi katika mambo yote muhimu kwa mfumo husika wa utoaji taarifa. Si hakikisho kwamba kila muamala ulikuwa halali au kwamba hakukuwa na udanganyifu, wizi au upotevu. Hoja za ukaguzi na hitimisho kuhusu uzingatiaji wa sheria zisomwe kando. | A clean opinion means the audited accounts fairly show the finances of that body for that period, allowing for what matters to the accounts. It does not promise that every payment followed the law or that there was no fraud, theft or loss. Read the findings and checks on legal compliance too. |
| `glossary.outstanding.title` | Outstanding Balance | Salio la Deni | Amount still owed |
| `glossary.outstanding.body` | The amount still owed at the source reporting date, on the basis used by that source. A register line may combine debt for a creditor or instrument type rather than represent one loan agreement. Missing balances or incomplete coverage are not zero debt. | Kiasi ambacho bado kinadaiwa hadi tarehe ya ripoti, kwa msingi unaotumiwa na chanzo hicho. Mstari wa rejista unaweza kuunganisha deni la wadai au aina ya hati badala ya kuwa mkataba mmoja wa mkopo. Salio kukosekana au taarifa kutokamilika si deni la sifuri. | How much is still owed on the date shown by the source. One row can group debt by creditor or type of borrowing, rather than show one loan agreement. Missing amounts or a list covering only some debt do not mean nothing is owed. |
| `glossary.multilateral.title` | Multilateral Lender | Mkopeshaji wa Kimataifa wa Nchi Nyingi | Lender backed by several countries |
| `glossary.multilateral.body` | An international institution backed by several countries, such as the World Bank, IMF or African Development Bank. Rates, repayment periods and conditions depend on the agreement. A creditor line may group several agreements. | Taasisi ya kimataifa inayoungwa mkono na nchi nyingi, kama Benki ya Dunia, IMF au Benki ya Maendeleo ya Afrika. Riba, muda wa ulipaji na masharti hutegemea mkataba. Mstari wa mdai unaweza kuunganisha mikataba kadhaa. | A body backed by several countries, such as the World Bank, IMF or African Development Bank. The agreement sets the interest, repayment dates and conditions. One creditor row may cover several agreements. |
| `glossary.bilateral.title` | Bilateral Lender | Mkopeshaji wa Nchi Moja | Lender from another government |
| `glossary.bilateral.body` | Another government lending to Kenya, directly or through its lending agencies. The agreement sets rates, repayment periods and any project conditions. A creditor-country line can group several loans; it is not necessarily one agreement. | Serikali nyingine inayoikopesha Kenya moja kwa moja au kupitia taasisi zake za mikopo. Mkataba huweka riba, muda wa ulipaji na masharti ya mradi. Mstari wa nchi mdai unaweza kuunganisha mikopo kadhaa; si lazima uwe mkataba mmoja. | Another government that lends to Kenya, itself or through its lending bodies. Each agreement sets the interest, repayment dates and conditions. A row for one country can cover several loans. |
| `glossary.commercial.title` | Commercial Lender | Mkopeshaji wa Kibiashara | Private lender |
| `glossary.commercial.body` | Private banks or investors lending on commercial terms, including holders of international bonds such as Eurobonds. Rates, repayment periods and conditions depend on the agreement or instrument. A register line may group several obligations. | Benki binafsi au wawekezaji wanaokopesha kwa masharti ya kibiashara, wakiwemo wenye hati fungani za kimataifa kama Eurobond. Riba, muda wa ulipaji na masharti hutegemea mkataba au hati. Mstari wa rejista unaweza kuunganisha madeni kadhaa. | Private banks or investors that lend money, including buyers of international bonds such as Eurobonds. The agreement or bond sets the interest, repayment dates and conditions. One row may group several debts. |
| `glossary.development_spending.title` | Development Spending | Matumizi ya Maendeleo | Spending on long-term projects |
| `glossary.development_spending.body` | Spending classified as development in the source budget, such as roads, hospitals or water systems. Check whether the figure is an allocation or actual spending and which institution and period it covers. Spending alone does not establish that a project was completed or delivered value. | Matumizi yaliyoainishwa kuwa ya maendeleo katika bajeti ya chanzo, kama barabara, hospitali au mifumo ya maji. Angalia kama takwimu ni fedha zilizotengwa au zilizotumika na taasisi na kipindi inachohusu. Matumizi pekee hayathibitishi kwamba miradi imekamilika au imetoa thamani. | Money classed in the budget as spending on long-term projects, such as roads, hospitals or water systems. Check whether it is planned money or money actually spent, and who and when it covers. Spending money does not by itself show that a project is finished or useful. |
| `glossary.recurrent_spending.title` | Recurrent Spending | Matumizi ya Kawaida | Day-to-day spending |
| `glossary.recurrent_spending.body` | Spending classified as recurrent in the source budget: running costs such as salaries, rent, fuel and supplies. Check whether the figure is an allocation or actual spending for the stated institution and period. This classification alone does not establish waste or efficiency. | Matumizi yaliyoainishwa kuwa ya kawaida katika bajeti ya chanzo: gharama za uendeshaji kama mishahara, kodi ya majengo, mafuta na vifaa. Angalia kama ni fedha zilizotengwa au zilizotumika kwa taasisi na kipindi kilichotajwa. Uainishaji huu pekee hauthibitishi ubadhirifu au ufanisi. | Day-to-day running costs such as salaries, rent, fuel and supplies, as grouped by the budget source. Check whether the money is planned or actually spent, and for which body and period. This label alone does not tell us whether the money was wasted or used well. |
| `glossary.info_label` | What is {title}? | {title} ni nini? | What does {title} mean? |
| `glossary.financial_health.body` | A site-made composite score (0–100) using available budget absorption, own-source revenue, pending bills, and a signal from publishable audit finding severity. When all four are available, the audit signal carries the same weight as the other three inputs combined. At least two inputs are required for a grade, from A to C. This is separate from the accountability score and is not an official OAG rating. | Alama ya pamoja (0–100) iliyoundwa na tovuti kutokana na matumizi ya bajeti, mapato ya ndani, bili ambazo hazijalipwa, na kiashiria cha ukali wa hoja za ukaguzi zinazoweza kuchapishwa. Vipengele vyote vinne vikipatikana, kiashiria cha ukaguzi kina uzito sawa na vipengele vingine vitatu kwa pamoja. Angalau vipengele viwili vinahitajika ili kutoa daraja la A hadi C. Alama hii ni tofauti na alama ya uwajibikaji na si alama rasmi ya Mkaguzi Mkuu. | This site gives each county a money-health score from 0 to 100 using available budget spending, local revenue, unpaid bills, and a signal from published audit findings. When all four are available, the audit signal counts as much as the other three together. We need at least two to give an A to C grade. The accountability score is separate. This is not an official Auditor-General rating. |
| `county.healthmodal.title` | Financial Health Score | Alama ya Afya ya Kifedha | Money Health Score |

## Inherited #307 backlog: review alongside the new terms

These are current catalog strings, **not changes or newly certified translations**. Scope derives from #307's current body and all comments read on 2026-10-01: audit headline/unaccounted and withholding; fiscal shares; county pending-bill notes; creditor/register lines; county cash-revenue basis/discrepancies; financial-health explanation/modal. The affected feature keys from earlier #246/#256/#279 remain part of #307 and are not exhausted by this targeted table.

Some older Swahili opinion/status labels conflict in terminology across surfaces: `Kanusho` vs `bila maoni`, `Qualified opinion` vs `yenye masharti`, and `Adverse opinion` vs `hasi`. The English qualified/adverse labels in Swahili are deliberate untranslated fallbacks pending review (#307); do not invent replacements or treat the retained English as a completed translation. The new clean-opinion wording needs a consistent terminology decision with these keys. This packet does not assert all status keys are currently reachable as official opinions; inspect each caller before changing its meaning.

| Current key | English | Current Swahili |
| --- | --- | --- |
| `home.govcard.pct_of_budget` | {pct}% of spending | {pct}% ya matumizi |
| `home.audits.title` | Latest Audit Reports | Ripoti za Hivi Karibuni za Ukaguzi |
| `home.audits.subtitle` | Official findings from the Office of the Auditor-General | Matokeo rasmi kutoka Ofisi ya Mkaguzi Mkuu |
| `home.audits.see_all` | See all reports | Tazama ripoti zote |
| `home.audits.clean` | Clean | Safi |
| `home.audits.qualified` | Qualified | Qualified opinion |
| `home.audits.adverse` | Adverse | Adverse opinion |
| `home.audits.disclaimer` | Disclaimer | Kanusho |
| `home.audits.no_reports` | No audit reports yet | Hakuna ripoti za ukaguzi bado |
| `home.audits.loading` | Loading audits… | Inapakia ukaguzi… |
| `home.audits.report_title` | Auditor General’s Report | Ripoti ya Mkaguzi Mkuu |
| `home.audits.national_govt_fy` | National Government — {fy} | Serikali Kuu — {fy} |
| `home.audits.unavailable` | Audit data unavailable | Data ya ukaguzi haipatikani |
| `home.audits.findings_label` | findings | matokeo |
| `home.audits.opinion_label` | Audit Opinion: | Maoni ya Ukaguzi: |
| `home.audits.default_basis` | Material misstatements identified across multiple ministries | Makosa makubwa yamebainika katika wizara mbalimbali |
| `home.audits.signed_by` | Signed by {name} | Imetiwa saini na {name} |
| `home.audits.stat_ministries` | Ministries Audited | Wizara Zilizokaguliwa |
| `home.audits.stat_amount` | Amount Questioned | Kiasi Kilichohojiwa |
| `home.audits.amount_partial` | KES {amount} stated across {n} of {total} findings | KES {amount} imetajwa katika matokeo {n} kati ya {total} |
| `home.audits.amount_partial_note` | The Auditor-General’s own questioned total is not stated in the machine-readable part of this report, so this is what the findings themselves add up to — not the report’s headline figure. | Jumla ya Mdhibiti na Mkaguzi Mkuu haijatajwa katika sehemu inayosomeka kwa mashine ya ripoti hii; hii ni jumla ya matokeo yenyewe, si kiasi kikuu cha ripoti. |
| `home.audits.stat_critical` | Critical Findings | Matokeo Muhimu |
| `home.audits.stat_recurring` | Recurring Issues | Masuala Yanayojirudia |
| `home.audits.findings_overview` | Audit Findings Overview | Muhtasari wa Matokeo ya Ukaguzi |
| `home.audits.amount_prefix` | Amount: | Kiasi: |
| `home.audits.amount_unavailable` | Unavailable pending verification | Haipatikani hadi ithibitishwe |
| `home.audits.amount_not_recorded` | No amount recorded | Hakuna kiasi kilichorekodiwa |
| `home.audits.action_prefix` | Action: | Hatua: |
| `home.audits.sev_critical` | Critical | Muhimu Sana |
| `home.audits.sev_significant` | Significant | Kubwa |
| `home.audits.sev_minor` | Minor | Ndogo |
| `home.audits.emphasis` | Emphasis of Matter | Msisitizo wa Suala |
| `home.audits.top_ministries` | Top Ministries Flagged | Wizara Zilizoonywa Zaidi |
| `home.audits.view_all_findings` | View All Findings | Tazama Matokeo Yote |
| `home.audits.empty_title` | No findings from the Auditor-General can be published yet | Hakuna matokeo ya Mkaguzi Mkuu yanayoweza kuchapishwa bado |
| `home.audits.empty_withheld` | {n} findings are held back because their publication checks could not be confirmed. | Matokeo {n} yamezuiliwa kwa sababu ukaguzi wa uchapishaji wake haukuweza kuthibitishwa. |
| `home.audits.empty_window` | The {publisher} publishes this report {cadence}, {lag} after the fiscal year ends. The next report is expected between {start} and {end}. | {publisher} huchapisha ripoti hii {cadence}, {lag} baada ya mwaka wa fedha kuisha. Ripoti ijayo inatarajiwa kati ya {start} na {end}. |
| `home.audits.empty_ministries` | No ministry can be listed until its findings trace to a published report. | Hakuna wizara inayoweza kuorodheshwa hadi matokeo yake yafuatilike kwenye ripoti iliyochapishwa. |
| `home.audits.source_page` | Source: report {page} | Chanzo: ripoti {page} |
| `home.audits.modified_title` | Modified audit opinions found in this report | Maoni ya ukaguzi yaliyorekebishwa yaliyopatikana katika ripoti hii |
| `home.audits.modified_none` | No “Basis for … Opinion” section was found among the {read} votes whose opinion could be read. | Hakuna sehemu ya “Msingi wa Maoni” iliyopatikana katika mafungu {read} ambayo maoni yake yangeweza kusomwa. |
| `home.audits.opinion_votes` | {n} vote(s) · {f} finding(s) | mafungu {n} · matokeo {f} |
| `home.audits.modified_coverage` | Read from the report’s own “Basis for … Opinion” sections. Each line means at least one account audited under that vote received that opinion; the page shows which. The opinion could be read for {read} of the {total} votes with extracted findings, and this site has not yet extracted every section of the report, so these counts are minimums. No vote is shown as clean: one vote covers several separately audited accounts. | Imesomwa kutoka sehemu za “Msingi wa Maoni” za ripoti yenyewe. Kila mstari unamaanisha angalau hesabu moja iliyokaguliwa chini ya fungu hilo ilipata maoni hayo; ukurasa unaonyesha ipi. Maoni yangeweza kusomwa kwa mafungu {read} kati ya {total} yenye matokeo yaliyotolewa, na tovuti hii bado haijatoa kila sehemu ya ripoti, kwa hiyo idadi hizi ni za chini kabisa. Hakuna fungu linaloonyeshwa kuwa safi: fungu moja linajumuisha hesabu kadhaa zinazokaguliwa kando. |
| `home.audits.stat_votes` | Votes With Extracted Findings | Mafungu Yenye Matokeo Yaliyotolewa |
| `home.audits.stat_unresolved` | Unresolved Prior-Year Matters | Masuala ya Awali Yasiyotatuliwa |
| `home.audits.unit_votes` | votes | mafungu |
| `home.audits.emphasis_summary` | Raised on {n} votes ({f} paragraphs). Most frequent: “{title}”, {c} times. | Imetajwa katika mafungu {n} (aya {f}). Linalojirudia zaidi: “{title}”, mara {c}. |
| `home.audits.withheld_source_document_has_no_url` | {n} finding(s) held back for lack of a traceable source document. | Matokeo {n} yamezuiliwa kwa kukosa hati ya chanzo inayofuatilika. |
| `home.audits.withheld_source_document_has_invalid_url` | {n} finding(s) held back because the source document link is invalid or unsafe. | Matokeo {n} yamezuiliwa kwa sababu kiungo cha hati ya chanzo si sahihi au si salama. |
| `home.audits.withheld_finding_text_unreadable_cid` | {n} finding(s) held back because the extracted text is unreadable. | Matokeo {n} yamezuiliwa kwa sababu maandishi yaliyotolewa hayasomeki. |
| `home.audits.withheld_no_page_reference` | {n} finding(s) held back because the page reference is missing or invalid. | Matokeo {n} yamezuiliwa kwa sababu rejeleo la ukurasa halipo au si sahihi. |
| `home.audits.withheld_other_publication_check` | {n} finding(s) held back because another publication check did not pass. | Matokeo {n} yamezuiliwa kwa sababu hayakupita ukaguzi mwingine wa uchapishaji. |
| `home.audits.cadence_annual` | annually | kila mwaka |
| `home.audits.cadence_quarterly` | quarterly | kila robo mwaka |
| `home.audits.cadence_monthly` | monthly | kila mwezi |
| `home.audits.lag_months` | {lag} months | miezi {lag} |
| `home.audits.lag_days` | {lag} days | siku {lag} |
| `home.loans.header_sub` | {n} creditor and instrument lines — {src} | Mistari {n} ya wadai na aina za deni — {src} |
| `home.loans.see_all_n` | See all {n} register lines → | Tazama mistari yote {n} ya deni → |
| `home.county_panel.audit_disclaimer` | Disclaimer | Kanusho |
| `home.map.legend.disclaimer` | Disclaimer | Kanusho |
| `home.features.missing.title` | Unaccounted funds | Pesa Zisizohesabika |
| `home.features.missing.desc` | Findings the Auditor-General headed as unaccounted for or a loss of funds, each linked to its page. | Matokeo ambayo Mkaguzi Mkuu aliyaita pesa zisizohesabika au hasara ya fedha, kila moja na ukurasa wake. |
| `counties.audit_status.disclaimer` | Disclaimer | Kanusho |
| `county.revenue.title` | Revenue & Transfers | Mapato na Uhamishaji |
| `county.revenue.own_source` | Own-source revenue | Mapato ya chenyewe |
| `county.revenue.equitable_share` | Equitable share | Sehemu Sawa |
| `county.revenue.conditional_grants` | Conditional grants | Ruzuku za Masharti |
| `county.unaccounted.heading` | {n} finding(s) the Auditor-General headed as unaccounted for or a loss of funds | Matokeo {n} ambayo Mkaguzi Mkuu aliyaita pesa zisizohesabika au hasara ya fedha |
| `county.unaccounted.no_total` | In the report’s own words, with the page each comes from. No total is shown: the sum involved is not extracted from these findings. | Kwa maneno ya ripoti yenyewe, pamoja na ukurasa wa kila moja. Hakuna jumla inayoonyeshwa: kiasi husika hakijatolewa kutoka matokeo haya. |
| `county.unaccounted.see_all` | See all counties and votes | Tazama kaunti na mafungu yote |
| `county.overview.pending_as_at` | As at {date} · Controller of Budget, {table} | Hadi {date} · Mdhibiti wa Bajeti, {table} |
| `county.overview.pending_absent.not_reported` | Not reported to the Controller of Budget as at {date} ({table}). | Haijaripotiwa kwa Mdhibiti wa Bajeti hadi {date} ({table}). |
| `county.overview.pending_absent.withheld` | Not shown: the Controller of Budget's row for this county ({table}, {date}) does not add up on its own terms. | Haionyeshwi: safu ya Mdhibiti wa Bajeti kwa kaunti hii ({table}, {date}) haijumliki yenyewe. |
| `county.overview.pending_note.cob_marked_inconsistent` | The Controller of Budget marks this figure as inconsistent with the county's own ageing analysis of the same bills ({table}). | Mdhibiti wa Bajeti anaonyesha kuwa takwimu hii haiwiani na uchambuzi wa kaunti yenyewe wa umri wa bili hizo hizo ({table}). |
| `county.overview.pending_note.assembly_not_printed` | County Executive only: the report prints no County Assembly figure for this county ({table}). | Serikali ya Kaunti pekee: ripoti haionyeshi takwimu ya Bunge la Kaunti kwa kaunti hii ({table}). |
| `county.overview.pending_note.chapter_table_differs` | The same report's county chapter prints {amount} ({chapter_table}); the figure shown is the one that adds up to the report's national total ({table}). | Sura ya kaunti katika ripoti hiyo hiyo inaonyesha {amount} ({chapter_table}); takwimu inayoonyeshwa ni ile inayojumlika kuwa jumla ya kitaifa ya ripoti ({table}). |
| `county.revenue.cash_receipts` | Own-source cash receipts | Mapato ya ndani yaliyopokelewa |
| `county.revenue.summary_actual_realised` | Summary table “Actual Realised” | Jedwali la muhtasari “Actual Realised” |
| `county.revenue.amount` | {label}: {amount} | {label}: {amount} |
| `county.revenue.summary_differs` | Summary table “Actual Realised”: {amount}; differs from cash receipts | Jedwali la muhtasari “Actual Realised”: {amount}; hutofautiana na fedha zilizopokelewa |
| `county.revenue.cash_and_opening_balance` | Cash receipts and opening balance | Fedha zilizopokelewa na salio la mwanzo |
| `county.acct.opinion.unqualified` | Unqualified | Safi |
| `county.acct.opinion.qualified` | Qualified | Qualified opinion |
| `county.acct.opinion.adverse` | Adverse | Adverse opinion |
| `county.acct.opinion.disclaimer` | Disclaimer | Kanusho |
| `county.healthmodal.title` | Financial Health Score | Alama ya Afya ya Kifedha |
| `county.healthmodal.how_calc` | How It’s Calculated | Jinsi Inavyohesabiwa |
| `county.healthmodal.derived_from` | This site-made financial-health index combines available budget absorption, own-source revenue, pending bills, and a signal derived from publishable audit findings. It is separate from the accountability score. | Faharasa hii ya afya ya kifedha iliyoundwa na tovuti inachanganya matumizi ya bajeti, mapato ya ndani, bili ambazo hazijalipwa, na kiashiria kilichotokana na hoja za ukaguzi zinazoweza kuchapishwa. Ni tofauti na alama ya uwajibikaji. |
| `county.healthmodal.rule_1` | Budget absorption: | Matumizi ya bajeti: |
| `county.healthmodal.rule_1_body` | Spending compared with allocation, scored around 100%; under- and overspending both lower this component. | Matumizi yanalinganishwa na bajeti iliyotengwa; matumizi chini au juu ya 100% hupunguza sehemu hii. |
| `county.healthmodal.rule_2` | Own-source revenue: | Mapato ya ndani: |
| `county.healthmodal.rule_2_body` | Amount collected against the reported target, capped at 100. | Kiasi kilichokusanywa dhidi ya lengo lililoripotiwa, hadi alama 100. |
| `county.healthmodal.rule_3` | Pending bills: | Bili ambazo hazijalipwa: |
| `county.healthmodal.rule_3_body` | Pending bills as a share of budget; this component reaches zero at 25% of the budget. | Bili ambazo hazijalipwa kama sehemu ya bajeti; sehemu hii huwa sifuri zikifikia 25% ya bajeti. |
| `county.healthmodal.rule_4` | Audit signal: | Kiashiria cha ukaguzi: |
| `county.healthmodal.rule_4_body` | The site uses the highest finding severity in the latest audited fiscal year with County Executive evidence: info 100, warning 60, critical 20. Assembly findings are excluded. Missing or conflicting period or institution evidence is disclosed. This is not an official OAG opinion. The chosen weight is 3. | Tovuti hutumia ukali wa juu zaidi wa hoja katika mwaka wa fedha wa hivi karibuni uliokaguliwa wenye ushahidi wa Serikali ya Utendaji ya Kaunti: taarifa 100, onyo 60, hatari kubwa 20. Hoja za Bunge la Kaunti hazijumuishwi. Ushahidi wa kipindi au taasisi unaokosekana au unaokinzana unaelezwa. Haya si maoni rasmi ya Mkaguzi Mkuu. Uzito uliochaguliwa ni 3. |
| `county.healthmodal.max_note` | At least two components are required. Missing components are omitted and the available weights are adjusted; no score means no grade. | Angalau sehemu mbili zinahitajika. Sehemu zisizopatikana hazihesabiwi na uzito wa zilizopo hurekebishwa; bila alama hakuna daraja. |
| `county.healthmodal.close` | Close financial health explanation | Funga maelezo ya afya ya kifedha |
| `county.healthmodal.components_title` | This county’s score components | Vipengele vya alama ya kaunti hii |
| `county.healthmodal.observed` | Observed | Kilichoripotiwa |
| `county.healthmodal.weight` | Weight used | Uzito uliotumika |
| `county.healthmodal.basis.cash_receipts` | Measured from cash receipts | Imepimwa kwa fedha taslimu zilizopokelewa |
| `county.healthmodal.basis.summary_actual` | Measured from the summary table’s actual realised | Imepimwa kwa kiasi halisi kilichofikiwa kwenye jedwali la muhtasari |
| `county.healthmodal.mixed_pending_periods` | The stored pending-bill amount spans multiple reporting dates; this component has no single source period: | Kiasi cha bili zilizohifadhiwa kinahusisha tarehe nyingi za kuripoti; sehemu hii haina kipindi kimoja cha chanzo: |
| `county.healthmodal.mixed_pending_sources` | The stored pending-bill amount spans multiple sources; no single report supports the component. | Kiasi cha bili zilizohifadhiwa kinatoka vyanzo vingi; hakuna ripoti moja inayothibitisha sehemu hii. |
| `county.healthmodal.period_unknown` | Period unavailable | Kipindi hakipatikani |
| `county.healthmodal.as_at` | as at | hadi |
| `county.healthmodal.source_link` | Source report | Ripoti chanzo |
| `county.healthmodal.no_breakdown` | No composite score is available. At least two sourced components are required. | Hakuna alama ya pamoja inayopatikana. Angalau vipengele viwili vyenye vyanzo vinahitajika. |
| `county.healthmodal.breakdown_unavailable` | The score breakdown is unavailable in this response. | Maelezo ya vipengele vya alama hayapatikani katika jibu hili. |
| `county.healthmodal.unavailable` | Unavailable inputs, excluded from the score | Vipengele visivyopatikana, havijahesabiwa kwenye alama |
| `county.healthmodal.status.clean` | clean | safi |
| `county.healthmodal.status.qualified` | qualified | yenye masharti |
| `county.healthmodal.status.adverse` | adverse | hasi |
| `county.healthmodal.status.disclaimer` | disclaimer | bila maoni |
| `county.healthmodal.this_county_numbers` | Related County Figures | Takwimu Husika za Kaunti |
| `county.healthmodal.row.budget_allocated` | Budget Allocated | Bajeti Iliyotengwa |
| `county.healthmodal.row.budget_spent` | Budget Spent | Bajeti Iliyotumika |
| `county.healthmodal.row.execution_rate` | Execution Rate | Kiwango cha Utekelezaji |
| `county.healthmodal.row.pending_bills` | Pending Bills | Ankara Zilizokwama |
| `county.healthmodal.row.total_debt` | Total Debt | Deni Jumla |
| `county.healthmodal.row.audit_issues` | Audit Issues | Matatizo ya Ukaguzi |
| `county.healthmodal.row.stalled_projects` | Stalled Projects | Miradi Iliyokwama |
| `county.healthmodal.grade_scale` | Grade Scale | Kiwango cha Alama |
| `county.healthmodal.current` | Current | Ya Sasa |
| `county.healthmodal.source_line` | Source periods and report links appear beside each included component when available. | Vipindi vya vyanzo na viungo vya ripoti vinaonekana karibu na kila kipengele kilichohesabiwa vinapopatikana. |

## Runtime review and sign-off procedure

1. Open the real LangProvider with `financial-health`, `budget-execution`, `audit-clean`, `debt-to-gdp`, `pending-bills`, the external/domestic split and creditor/instrument terms. Check each tooltip title/body and accessible question while switching English → Swahili → plain → English with the tooltip open. Read aloud the Swahili question with its substituted title.
2. Reload or remount after selecting a language: localStorage key is `auditgava-lang`. Confirm the selection returns. Invalid/blocked storage retains English. An English fallback such as `principal` remains English in both title and question; the uncalled fallback catalog is outside this incremental translation scope.
3. Check negations and units with a financial reviewer. Missing/withheld/conflicting is not zero; a reported zero is a value. Different dates/institutions/sources are not interchangeable. An opinion, finding, unaccounted amount and proven loss are different claims.
4. Record reviewer name/qualifications, date, reviewed key list, corrections, and any unresolved meanings below. Changes must preserve placeholder sets (`{title}`, `{n}`, `{src}`, and any figures in inherited entries). Re-run the focused language and domain wording tests after corrections; passing tests still do not replace this sign-off.

Reviewer: **pending**. Review date: **pending**. Reviewed keys: **none certified**. Corrections: **pending**. Remaining concerns: **all proposed Swahili and the inherited #307 backlog**.

## Engineering acceptance and limits

Actual Jest/JSDOM tests run with the real InfoTip and language provider, not source-text assertions: the final focused fixture is red on pinned InfoTip/catalog (21 failures, 4 coherent controls pass) and green after this patch (25 pass). Seven related suites pass (73 tests total) covering debt-card absence/split, loan interest, register scope, pending notes and opinion wording. This evidence covers rendering/persistence and fixed prop lookup; it does not certify native-language accuracy, browser layout or screen-reader announcements.

Both glossary maps now require an own property. `toString`, `constructor`, `__proto__`, `hasOwnProperty`, `valueOf`, ordinary missing terms and empty terms produce no help control. Current application callers select known literal terms (including fixed lender/budget branches); this remains a latent component defect, not a claim of a demonstrated user-controlled security exploit. Existing principal/other unused English fallback entries remain available.

This session does not redesign the UI or change the LangProvider, production data, configuration or financial inventory. The coordinator should consolidate the local commit, retain Actions disabled, and arrange competent review; there are no production writes or release commands in this packet.

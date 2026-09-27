"""Real pages of the Treasury's Budget Review and Outlook Paper, as pdfplumber reads them.

Generated with ``pdfplumber.open(path).pages[n - 1].extract_text()`` (the call
``brop_parser`` makes); the PDFs themselves are not committed.

* 2026 BROP (cover "AUGUST 2026"; PDF created 2026-09-07),
  https://www.treasury.go.ke/sites/default/files/BROP%20-%20Budget%20Review%20Outlook%20Paper/2026%20Budget%20Review%20and%20Outlook%20Paper....pdf
  sha256 39c2e290ecdb6be0d8768344514711a5b0c6a350f0416ed81e529cded60def24, 76 pages.
  p.18 carries para 20, the national pending bills at 30th June 2026
  (475.5 = 365.6 State Corporations + 109.9 MDAs). The paragraph was para 19
  in the draft (the comments matrix says so) and para 18 in the 2025 paper.
  pp.33-34 carry Table 11, the counties at 31st March 2026 (not read: counties
  come from the Controller of Budget's year-end report, #238).
* 2025 BROP (cover "SEPTEMBER 2025"; PDF created 2025-10-08),
  https://www.treasury.go.ke/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf
  sha256 e0479eca5a318aa97d6daf11672880433b7d6a4686a09fa3d4895e09d93cf1f4, 75 pages.
  p.18 carries para 18 (525.9 = 404.3 + 121.6 at 30th June 2025).

TREASURY_LISTING_ANCHORS are every PDF link on
https://www.treasury.go.ke/budget-review-and-outlook-paper/ as fetched on
2026-09-26, whitespace collapsed, in page order.
"""

BROP_2026_URL = (
    "https://www.treasury.go.ke/sites/default/files/"
    "BROP%20-%20Budget%20Review%20Outlook%20Paper/"
    "2026%20Budget%20Review%20and%20Outlook%20Paper....pdf"
)
BROP_2025_URL = (
    "https://www.treasury.go.ke/sites/default/files/"
    "2025-Budget-Review-and-Outlook-Paper-1.pdf"
)
TREASURY_LISTING_URL = "https://www.treasury.go.ke/budget-review-and-outlook-paper/"

BROP_2026_PAGES = {1: 'REPUBLIC OF KENYA\n'
    'THE NATIONAL TREASURY\n'
    '2026 BUDGET REVIEW\n'
    'AND OUTLOOK PAPER\n'
    'AUGUST 2026\n'
    '1',
 18: 'billion Project Loans-Cash; and KSh 475.1 billion Commercial Financing. The external\n'
     'repayments (outflows) of principal debt amounted to KSh 504.3 billion. The amount comprised\n'
     'of principal repayments due to commercial institutions; bilateral sources; and multilateral\n'
     'sources amounting to, KSh 278.1 billion, KSh 132.8 billion and KSh 93.4 billion '
     'respectively.\n'
     'Pending Bills\n'
     '20. The total outstanding National Government pending bills as of 30th June 2026 amounted\n'
     'to KSh 475.5 billion comprising of KSh 365.6 billion (76.9 percent) and KSh. 109.9 billion\n'
     '(23.1 percent) for the State Corporations (SCs) and Ministries/State Departments/other\n'
     'government entities respectively. The State Corporations pending bills include payment to\n'
     'contractors/projects, suppliers, unremitted statutory and other deductions, pension arrears '
     'for\n'
     'Local Authorities Pension Trust, and others. The highest percentage of the SCs pending '
     'bills\n'
     'are related to Development expenditure (53.3 percent) with recurrent expenditure pending '
     'bills\n'
     'accounting for 46.7 percent of the total State Corporations pending bills. Ministries/State\n'
     'Departments and other government entities pending bills constitutes mainly of the '
     'historical\n'
     'ones.\n'
     '21. The National Government policy on clearance of pending bills continues to be in force.\n'
     'All MDAs are therefore expected to continue prioritizing the payment of the pending bills '
     'by\n'
     'settling them as a first charge in the current financial year budget, in line with the '
     'Treasury\n'
     'guidelines for implementation of the financial year 2025/26 and the medium-term budget and\n'
     'Treasury Circular No. 7/2023. In addition, the National Treasury has developed a\n'
     'comprehensive strategy to clear outstanding stock of verified pending bills of the National\n'
     'Government over the medium term. The strategy will address deficiencies and lapses that '
     'have\n'
     'led to accumulation of pending bills.\n'
     'Tax Expenditures\n'
     '22. The Government continued to make progress in rationalizing tax expenditures as part of\n'
     'efforts to strengthen domestic revenue mobilization and create fiscal space. The 2025 Tax\n'
     'Expenditure Report estimates total revenue forgone through tax expenditures at KSh 286.5\n'
     'billion in 2024, equivalent to 1.77 percent of GDP, compared to KSh 368.4 billion, or 2.45\n'
     'percent of GDP, in 2023 (Table 5). The decrease reflects adjustments introduced under the\n'
     'Medium-Term Revenue Strategy and recent legislative changes affecting exemptions,\n'
     'preferential rates, and zero rating.\n'
     'Table 5: Tax Expenditures by Categories\n'
     '+Revised\n'
     'Source of Data: Kenya Revenue Authority\n'
     '18',
 33: '62. As of 31st March, 2026, County Governments reported outstanding pending bills totalling\n'
     'KSh 156.84 billion. This amount includes KSh 116.50 billion for recurrent activities and '
     'KSh\n'
     '40.34 billion for development activities. The pending bills for the County Executive as of '
     'this\n'
     'date were KSh 151.49 billion, while the amount for the County Assemblies was KSh 5.35\n'
     "billion. Table 11 below provides a breakdown of the County Governments' pending bills as of\n"
     '31st March 2026. Nairobi City County accounts for 52.1 percent of the total stock of County\n'
     'Governments’ pending bills. This is approximately 183 percent of its approved budget in the\n'
     'year under review holding the highest pending bills to budget ratio. Other counties with '
     'high\n'
     'pending bills as a percentage of their approved budget include; Machakos (36 percent), '
     'Kilifi\n'
     '(32 percent), Narok (26 percent), Turkana (24 percent) and Elgeyo-Marakwet (24 percent). '
     'This\n'
     'is largely attributed to non-adherence to the counties’ scheduled payment plans for '
     'outstanding\n'
     'pending bills, contrary to Regulation 55(2)(b) of the Public Finance Management (County\n'
     'Governments) Regulations, 2015 which requires County Governments to prioritise the\n'
     'settlement of all eligible pending bills as a first charge.\n'
     'Table 11: Pending Bills for the Counties as of 31st March 2026\n'
     'County County Executive (KSh Million) County Assembly (KSh Million) Grand Total FY 2025/26 % '
     'of\n'
     '(KSh Million) Budget (KSh Pending\n'
     'Rec Dev Sub-Total Rec Dev Sub-Total Million) Bill to\n'
     'Budget\n'
     'Baringo 151.87 95.61 247.48 23.89 0.00 23.89 271.37 9,542.03 3\n'
     'Bomet 229.87 352.85 582.71 7.21 10.85 18.06 600.78 10,815.78 6\n'
     'Bungoma 1,576.69 1,801.31 3,378.00 0.01 - 0.01 3,378.01 17,433.19 19\n'
     'Busia 1,174.30 937.57 2,111.86 548.34 0.00 548.34 2,660.20 11,248.15 24\n'
     'Elgeyo- Marakwet 6.31 2.41 8.72 0.00 0.00 0.00 8.72 8,849.61 0\n'
     'Embu 662.82 611.83 1,274.64 0.00 0.00 0.00 1,274.64 8,990.25 14\n'
     'Garissa 731.47 814.44 1,545.91 57.89 26.74 84.63 1,630.54 12,694.63 13\n'
     'Homa Bay 182.63 520.43 703.06 83.87 157.17 241.04 944.10 13,601.45 7\n'
     'Isiolo 645.12 180.35 825.46 121.21 106.36 227.57 1,053.03 7,555.84 14\n'
     'Kajiado 1,101.62 1,246.53 2,348.16 33.65 8.69 42.34 2,390.49 13,775.47 17\n'
     'Kakamega 1,739.09 826.94 2,566.03 503.78 163.84 667.62 3,233.65 17,047.86 19\n'
     'Kericho 247.83 776.14 1,023.97 0.00 13.21 13.21 1,037.18 10,034.96 10\n'
     'Kiambu 3,059.85 2,283.83 5,343.67 175.30 31.21 206.51 5,550.18 26,831.32 21\n'
     'Kilifi 2,786.36 3,317.43 6,103.79 287.24 4.29 291.53 6,395.32 19,876.51 32\n'
     'Kirinyaga 363.85 373.98 737.83 0.00 0.00 0.00 737.83 8,541.37 9\n'
     'Kisii 444.33 116.44 560.77 1.85 28.43 30.28 591.05 20,047.93 3\n'
     'Kisumu 1,499.06 1,120.08 2,619.14 12.08 0.00 12.08 2,631.22 16,331.52 16\n'
     'Kitui 11.73 103.33 115.06 9.22 0.00 9.22 124.29 14,745.36 1\n'
     'Kwale 179.38 161.86 341.24 0.00 207.95 207.95 549.19 15,827.56 3\n'
     'Laikipia 384.16 922.98 1,307.14 20.77 3.99 24.76 1,331.90 9,217.14 14\n'
     'Lamu 17.92 0.00 17.92 0.00 0.00 0.00 17.92 5,592.56 0\n'
     'Machakos 2,932.85 2,307.37 5,240.23 221.99 1.94 223.93 5,464.16 15,193.59 36\n'
     'Makueni 93.10 17.09 110.20 113.52 0.00 113.52 223.72 13,106.07 2\n'
     'Mandera 722.16 958.98 1,681.14 0.00 0.00 0.00 1,681.14 15,011.67 11\n'
     'Marsabit 0.00 143.08 143.08 3.43 72.33 75.76 218.84 10,329.94 2\n'
     'Meru 315.42 311.92 627.34 0.00 0.00 0.00 627.34 16,018.83 4\n'
     'Migori 336.64 280.01 616.65 629.57 0.30 629.87 1,246.51 11,777.35 11\n'
     'Mombasa 700.02 1,270.60 1,970.62 14.38 0.00 14.38 1,985.00 14,630.00 14\n'
     'Murang’a 1,002.81 143.45 1,146.26 36.12 0.00 36.12 1,182.39 11,716.75 10\n'
     'Nairobi 74,517.63 6,619.17 81,136.80 650.60 0.00 650.60 81,787.40 44,620.89 18\n'
     '3\n'
     'Nakuru 1,473.17 438.23 1,911.40 63.43 0.00 63.43 1,974.83 22,397.40 9\n'
     'Nandi 222.46 216.09 438.54 0.00 0.00 0.00 438.54 10,641.18 4\n'
     'Narok 2,786.50 1,592.52 4,379.02 21.80 0.00 21.80 4,400.82 17,231.06 26\n'
     'Nyamira 386.19 322.92 709.11 3.70 10.07 13.77 722.88 8,646.30 8\n'
     'Nyandarua 297.53 630.62 928.15 50.97 0.05 51.02 979.17 9,426.48 10\n'
     'Nyeri 218.52 12.45 230.97 0.00 0.00 0.00 230.97 9,441.73 2\n'
     'Samburu 6.27 53.74 60.01 24.11 0.00 24.11 84.12 8,109.38 1\n'
     'Siaya 759.30 601.47 1,360.77 72.58 0.00 72.58 1,433.35 12,793.34 11\n'
     'Taita-Taveta 1,331.45 480.54 1,811.99 84.95 0.00 84.95 1,896.94 8,335.02 23\n'
     '33',
 34: 'County County Executive (KSh Million) County Assembly (KSh Million) Grand Total FY 2025/26 % '
     'of\n'
     '(KSh Million) Budget (KSh Pending\n'
     'Rec Dev Sub-Total Rec Dev Sub-Total Million) Bill to\n'
     'Budget\n'
     'Tana River 1,167.19 905.38 2,072.56 0.00 0.00 0.00 2,072.56 9,964.87 21\n'
     'Tharaka-Nithi 244.74 109.80 354.54 101.12 3.92 105.04 459.58 7,510.56 6\n'
     'Trans Nzoia 806.33 947.06 1,753.39 0.00 0.00 0.00 1,753.39 9,917.66 18\n'
     'Turkana 2,520.86 2,034.42 4,555.28 39.67 213.20 252.87 4,808.15 19,906.29 24\n'
     'Uasin Gishu 818.14 109.95 928.09 134.23 0.00 134.23 1,062.32 17,427.22 6\n'
     'Vihiga 319.25 552.26 871.51 0.00 0.00 0.00 871.51 7,926.22 11\n'
     'Wajir 861.99 1,569.28 2,431.27 129.81 0.00 129.81 2,561.08 13,638.52 19\n'
     'West Pokot 183.25 77.49 260.74 0.00 0.00 0.00 260.74 8,985.06 3\n'
     'Total 112,220.01 39,272.20 151,492.21 4,282.31 1,064.54 5,346.85 156,839.06 633,303.84 25\n'
     '63. In efforts to address the threat of the ballooning pending bills owed by National and\n'
     'County Governments, the Government is in the process of strictly enforcing automated\n'
     'Integrated Financial Management Information System (IFMIS) Invoice Twinning, fully\n'
     'integrated with an end-to-end Electronic Government Procurement (e-GP) platform. Invoice\n'
     'Twinning ensures that every supplier invoice is electronically matched to an approved\n'
     'procurement plan, a valid purchase order, evidence of goods or services received, and a\n'
     'corresponding budget allocation before payment processing can commence. This eliminates\n'
     'duplicate, fraudulent, or unsupported payment claims while strengthening expenditure '
     'controls.\n'
     '64. When integrated with an end-to-end e-GP platform, the system creates a seamless digital\n'
     'procurement and payment lifecycle, from procurement planning and budget approval to\n'
     'tendering, contract award, contract execution, invoicing, and final payment. Such '
     'integration\n'
     'prevents MDAs from initiating procurement activities that are not supported by approved\n'
     'budgets or available cash, effectively blocking unbudgeted commitments at the source rather\n'
     'than addressing them after liabilities have already accumulated.\n'
     'E. Status of Equalisation Fund Disbursements and Project Implementation\n'
     "65. The Equalisation Fund's cumulative constitutional entitlement, equivalent to one-half\n"
     'percent (0.5 percent) of the most recent audited National Government revenue as approved by\n'
     'the National Assembly under Article 204(1) of the Constitution stood at KSh 80.09 billion. '
     'To\n'
     'date, a cumulative KSh 39.5 billion has been appropriated through three Appropriation Acts,\n'
     'namely Equalisation Fund Appropriation Act, 2018 (KSh 12.4 billion), Equalisation Fund\n'
     'Appropriation Act, 2023 (KSh 10.3 billion) and Equalisation Fund Appropriation Act, 2026\n'
     '(KSh 16.8 billion). The Equalisation Fund Appropriation Act, 2026 was, however, enacted\n'
     'towards the close of FY 2025/26 (assented to by the President on 29th May 2026) and falls '
     'for\n'
     'implementation in the current FY 2026/27; the operative appropriation for the period under\n'
     'review was therefore KSh 22.7 billion under the 2018 and 2023 Acts.\n'
     '66. Against this operative appropriation, the Fund has received KSh 22.42 billion for '
     'financing\n'
     'basic services; water, roads, health facilities and electricity in the marginalised areas, '
     'reflecting\n'
     'near-full funding of the appropriations then due. Of the amount received, the Fund '
     'disbursed\n'
     'KSh 10.98 billion to Ministries, Departments and Agencies under the First Marginalisation\n'
     'Policy, an absorption rate of about 93 percent of the 2018 appropriation and KSh 6.92 '
     'billion\n'
     'to beneficiary County Governments under the Second Marginalisation Policy representing\n'
     'about 69 percent of the 2023 appropriation for the implementation of 1,984 projects (360 '
     'under\n'
     'the First Policy and 1,624 under the Second).\n'
     '34'}

BROP_2025_PAGES = {1: 'REPUBLIC OF KENYA\n'
    'THE NATIONAL TREASURY\n'
    '2025 BUDGET REVIEW\n'
    'AND OUTLOOK PAPER\n'
    'SEPTEMBER 2025\n'
    '1',
 18: '17. The fiscal deficit in FY 2024/25 was financed through net domestic financing of KSh\n'
     '854.5 billion (5.0 percent of GDP) which was above target by KSh 28.7 billion. The net '
     'external\n'
     'financing amounted to KSh 179.7 billion (1.0 percent of GDP), representing a shortfall of '
     'KSh\n'
     '6.8 billion from target. Total disbursements (inflows) including AiA amounted to KSh 527.0\n'
     'billion for the period ending 30th June 2025 against a target of KSh 548.0 billion. The '
     'total\n'
     'disbursements included: KSh 113.7 billion Program Loans; KSh 85.8 billion Project Cash\n'
     'Loans; KSh 65.6 billion Project Loans AiA; KSh 8.8 billion OPEC Funds; and KSh 253.1\n'
     'billion Commercial Financing. The external repayments (outflows) of principal debt amounted\n'
     'to KSh 347.3 billion. The amount comprised of principal repayments due to commercial\n'
     'institutions; bilateral sources; and multilateral sources.\n'
     'Pending Bills\n'
     '18. The total outstanding National Government pending bills as at 30th June 2025 amounted\n'
     'to KSh 525.9 billion. These comprise of KSh 404.3 billion (76.9 percent) and KSh 121.6 '
     'billion\n'
     '(23.1 percent) for the State Corporations and MDAs, respectively. The State Corporations\n'
     'pending bills include payment to contractors/projects, suppliers, unremitted statutory and '
     'other\n'
     'deductions, pension arrears for Local Authorities Pension Trust, and others. The highest\n'
     'percentage of the State Corporations pending bills (52.0 percent) are related to '
     'development\n'
     'expenditure. MDAs’ pending bills are largely historical.\n'
     '19. The National Government policy on clearance of pending bills is in force. The National\n'
     'Treasury is currently developing a comprehensive strategy to clear outstanding stock of '
     'verified\n'
     'pending bills of the National Government over the medium term. In this strategy, '
     'deficiencies\n'
     'and lapses that led to accumulation of pending bills will be addressed.\n'
     'Fiscal Performance for the FY 2024/25 in relation to Financial Objectives\n'
     '20. To enhance financial management in FY 2024/25, the following financial objectives were\n'
     'adopted:\n'
     'i) To enhance revenue collection in FY 2024/25\n'
     '21. To enhance revenue collection to at least 17.1 percent of GDP, the Government broadened\n'
     'the tax base, enhanced digitization and improved tax compliance. In FY 2024/25, total '
     'revenue\n'
     'was at 17.0 percent of GDP. This was below target due to the withdrawal of the Finance Bill\n'
     '2024 and protests that disrupted economic activities.\n'
     'ii) To reduce the fiscal deficit to 5.8 percent of GDP in FY 2024/25\n'
     '22. The fiscal deficit including grants for FY 2024/25 was 5.9 percent of GDP which was\n'
     'largely within target. This was achieved through enhanced revenue mobilization and\n'
     'expenditure rationalization.\n'
     'iii) To ensure effective, efficient and economic use of public resources allocated in FY\n'
     '2024/25\n'
     '23. The Government implemented several targeted measures to control public expenditure and\n'
     'enhance fiscal discipline. Key measures included: reduction of non-essential expenditure,\n'
     'migration from cash basis to accrual, operationalization of Treasury Single Account,\n'
     'digitalization of public services, continued use of Public-Private Partnerships financing '
     'strategy\n'
     'and State Owned Enterprises reforms.\n'
     'iv) To reduce the cost borrowing in FY 2024/25\n'
     '24. In order to reduce the cost of borrowing, the government employed the following\n'
     'strategies: lengthening debt maturity, deepening domestic debt markets, and balancing\n'
     '18'}

TREASURY_LISTING_ANCHORS = ['<a '
 'href="/sites/default/files/BROP%20-%20Budget%20Review%20Outlook%20Paper/2026%20Budget%20Review%20and%20Outlook%20Paper....pdf" '
 'target="_blank" rel="noopener">2026 Budget Review and Outlook Paper (BROP)</a>',
 '<a href="/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf" target="_blank" '
 'rel="noopener">2025 Budget Review and Outlook Paper&nbsp;</a>',
 '<a href="/sites/default/files/BBB/2024-Budget-Review-and-Outlook-Paper.pdf" target="_blank" '
 'rel="noopener">2024 Budget Review and Outlook Paper</a>',
 '<a href="/sites/default/files/BBB/2023-Budget-Review-and-Outlook-Paper_f.pdf" target="_blank" '
 'rel="noopener">2023 Budget Review and Outlook Paper (BROP)</a>',
 '<a href="/sites/default/files/BBB/Draft-2023-Budget-Review-and-Outlook-Paper_F.pdf" '
 'target="_blank" rel="noopener">Draft 2023 Budget Review and Outlook Paper</a>',
 '<a href="/wp-content/uploads/2022/12/2022-Budget-Review-and-Outlook-Paper.pdf" target="_blank" '
 'rel="noopener">2022 Budget Review and Outlook Paper</a>',
 '<a href="/sites/default/files/BBB/Press-Release-on-the-Draft-2022-BROP.pdf" target="_blank" '
 'rel="noopener">Press Release on the Draft 2022 BROP</a>',
 '<a href="/sites/default/files/BBB/Draft-2022-Budget-Review-and-Outlook-Paper.pdf" '
 'target="_blank" rel="noopener">Draft 2022 Budget Review and Outlook Paper</a>',
 '<a href="/sites/default/files/BBB/2021-Budget-Review-and-Outlook-Paper.pdf" target="_blank" '
 'rel="noopener">2021 Budget Review and Outlook Paper</a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/Press-Release-on_Draft-2020-BROP.pdf">Press '
 'Release on_Draft 2020 BROP</a>',
 '<a '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/Final-2020-Budget-Review-and-Outlook-Paper.pdf"><span '
 'style="color: #0000ff;">Final 2020 Budget Review and Outlook Paper</span></a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/17.09.2019_Press-Release-on_Draft-2019-BROP_PS.pdf">17.09.2019_Press '
 'Release on_Draft 2019 BROP PS</a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/2018-BUDGET-REVIEW-AND-OUTLOOK-PAPER.pdf">2018 '
 '</a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/Draft-2018-Budget-Review-and-Outlook-Paper.pdf">Draft '
 '</a>',
 '<a '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/Draft-2018-Budget-Review-and-Outlook-Paper.pdf">&ndash;<span '
 'style="color: #0000ff;"> Budget Review and Outlook Paper</span></a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/Draft-2018-Budget-Review-and-Outlook-Paper.pdf">2018 '
 'Budget Review and Outlook Paper</a>',
 '<a '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/2017-Budget-Review-and-Outlook-Paper.pdf"><span '
 'style="color: #0000ff;">2017 Budget Review and Outlook Paper</span></a>',
 '<a href="/sites/default/files/BBB/2016-Budget-Review-and-Outlook-Paper.pdf" target="_blank" '
 'rel="noopener"><span style="color: #0000ff;">2016 Budget Review and Outlook Paper</span></a>',
 '<a '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/2014-Budget-Outlook-and-Review-Paper-BROP.pdf"><span '
 'style="color: #0000ff;">2014 Budget Outlook and Review Paper BROP</span></a>',
 '<a style="color: #0000ff;" '
 'href="http://ntnt.treasury.go.ke/wp-content/uploads/2020/11/2014-Budget-Outlook-and-Review-Paper-BROP.pdf">2014 '
 'Budget Outlook and Review Paper BROP</a>',
 '<a style="color: #0000ff;" '
 'href="/sites/default/files/BBB/2012-BROP-Presentation-Jan-17-2012-1.pdf">2012 BROP Presentation '
 'Jan 17 2012</a>',
 '<a href="/sites/default/files/BBB/BOP-2011-12-to-2013-14-Final.pdf" target="_blank" '
 'rel="noopener"><span style="color: #0000ff;">BOP 2011-12 to 2013-14- Final</span></a>',
 '<a style="color: #0000ff;" href="/sites/default/files/BBB/BOP-Jan-2009-10-to-2011-12.pdf" '
 'target="_blank" rel="noopener">Budget Outlook Paper Jan 2009-10 to 2011-12</a>',
 '<a href="/sites/default/files/BBB/BUDGET-OUTLOOK-PAPER-2008-2009-to-2010-2011.pdf" '
 'target="_blank" rel="noopener"><span style="color: #0000ff;">BUDGET OUTLOOK PAPER 2008-2009 to '
 '2010-2011</span></a>',
 '<a style="color: #0000ff;" href="/sites/default/files/BOP-Jan-2009-10-to-2011-12.pdf" '
 'target="_blank" rel="noopener">Budget Outlook Paper Jan 2009-10 to 2011-12</a>',
 '<a href="/sites/default/files/BUDGET-OUTLOOK-PAPER-2008-2009-to-2010-2011.pdf" target="_blank" '
 'rel="noopener"><span style="color: #0000ff;">BUDGET OUTLOOK PAPER 2008-2009 to '
 '2010-2011</span></a>',
 '<a '
 'href="https://www.treasury.go.ke/sites/default/files/TNT-%20Expenditure%20Requisition%20Form%20Amended%20Final.pdf" '
 'target="_blank">Expenditure Requisition Form</a>']

TREASURY_LISTING_HTML = "\n".join(TREASURY_LISTING_ANCHORS)

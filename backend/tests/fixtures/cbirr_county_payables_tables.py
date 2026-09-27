"""Real pages of the Controller of Budget's county trade-payables tables, as pdfplumber reads them.

Sources (Controller of Budget, County Governments Budget Implementation Review Report):

* FY 2025/26 full year (August 2026),
  https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482
  ("CGBIRR FY 2025_26 August 2026 Final 5.pdf",
  sha256 5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3).
  Table 2.10 "Trade Payables for the Counties as of 30 June 2026", PDF pp.51-53
  (p.53 also carries Table 2.11, the ageing analysis, which must not be read).
  Printed Grand Total KSh 172,526.69m; Nandi prints "-" across its row.
* FY 2024/25 full year (August 2025),
  https://cob.go.ke/download/county-governments-budget-implementation-review-report-fy-2024-25/?wpdmdl=16263
  Table 2.9 "Pending Bills for the Counties as of 30th June 2025", PDF pp.58-59.
  Page 58 splits the budget column in two (11 columns). Printed Grand Total
  KSh 183,028.75m, Narok 6,151.50m — the row the Treasury's BROP 2025 left blank.

*_TABLE_PAGES are [(pdf_page, table), ...] from page.extract_tables().
FY2526_TOC_LINES are the payables entries of the List of Tables (PDF pp.9-20)
from page.extract_text(). *_CHAPTER_BLOCKS run from a county table's
caption to its "Source:" line, over its page and the next.
"""

FY2526_TABLE_PAGES = [(51,
  [['County',
    'Budget (Kshs.\nMillion)',
    'Expenditure (Kshs.\nMillion)',
    'Absorption (%)',
    'No. of MCAs &\nSpeaker',
    'Average monthly\nsitting allowances\nper MCA (Kshs.)'],
   [None, 'A', 'B', 'C=B/A100', 'D', 'E=B/D/12'],
   ['Mombasa', '35.88', '32.56', '90.75', '43', '63,101'],
   ['Murang’a', '36.65', '33.98', '92.71', '48', '58,993'],
   ['Nairobi', '70.00', '47.39', '67.70', '125', '31,593'],
   ['Nakuru', '44.45', '41.35', '93.03', '76', '45,340'],
   ['Nandi', '13.07', '16.76', '128.23', '45', '31,037'],
   ['Narok', '33.21', '32.80', '98.77', '50', '54,667'],
   ['Nyamira', '41.18', '31.56', '76.64', '36', '73,056'],
   ['Nyandarua', '26.02', '26.02', '100.00', '42', '51,627'],
   ['Nyeri', '20.97', '15.70', '74.87', '43', '30,426'],
   ['Samburu', '40.97', '40.96', '99.98', '26', '131,282'],
   ['Siaya', '25.21', '25.21', '100.00', '45', '46,685'],
   ['Taita-Taveta', '27.80', '23.68', '85.18', '33', '59,798'],
   ['Tana River', '34.61', '30.78', '88.93', '27', '95,000'],
   ['Tharaka-Nithi', '27.90', '26.96', '96.63', '24', '93,611'],
   ['Trans Nzoia', '21.00', '21.00', '100.00', '34', '51,471'],
   ['Turkana', '30.16', '18.87', '62.57', '48', '32,760'],
   ['Uasin Gishu', '39.92', '29.48', '73.85', '45', '54,593'],
   ['Vihiga', '30.68', '30.05', '97.95', '38', '65,899'],
   ['Wajir', '40.68', '40.68', '100.00', '46', '73,696'],
   ['West Pokot', '33.56', '33.56', '100.00', '33', '84,747'],
   ['Total', '1,815.22', '1,613.72', '4,227.91', '2,231', '60,276']]),
 (51,
  [['County',
    'County Executive (Kshs. Million)',
    None,
    None,
    'County Assembly (Kshs. Million)',
    None,
    None,
    'Grand Total\n(Kshs. Mil-\nlion)',
    'FY 2025/26\nBudget',
    '% of\nPending\nBill to\nBudget'],
   [None,
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    'Recur-\nrent',
    'Develop-\nment',
    'Sub-Total',
    None,
    None,
    None],
   ['Baringo', '475.43', '330.10', '805.53', '64.70', '-', '64.70', '870.23', '10,075.96', '8.64'],
   ['Bomet*',
    '603.41',
    '787.98',
    '1,391.39',
    '-',
    '40.00',
    '40.00',
    '1,431.39',
    '10,853.28',
    '13.19'],
   ['Bungoma*',
    '1,500.81',
    '1,620.43',
    '3,121.24',
    '4.50',
    '-',
    '4.50',
    '3,125.74',
    '17,433.20',
    '17.93'],
   ['Busia',
    '1,169.76',
    '901.17',
    '2,070.93',
    '523.44',
    '-',
    '523.44',
    '2,594.37',
    '11,159.48',
    '23.25'],
   ['Elgeyo-Marakwet', '186.17', '52.54', '238.71', '-', '-', '-', '238.71', '9,144.87', '2.61'],
   ['Embu',
    '811.70',
    '735.84',
    '1,547.54',
    '77.44',
    '-',
    '77.44',
    '1,624.98',
    '9,395.13',
    '17.3']]),
 (52,
  [['County',
    'County Executive (Kshs. Million)',
    None,
    None,
    'County Assembly (Kshs. Million)',
    None,
    None,
    'Grand Total\n(Kshs. Mil-\nlion)',
    'FY 2025/26\nBudget',
    '% of\nPending\nBill to\nBudget'],
   [None,
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    'Recur-\nrent',
    'Develop-\nment',
    'Sub-Total',
    None,
    None,
    None],
   ['Garissa',
    '304.57',
    '1,081.98',
    '1,386.55',
    '40.39',
    '58.71',
    '99.10',
    '1,485.65',
    '13,536.09',
    '10.98'],
   ['Homa Bay',
    '667.99',
    '145.97',
    '813.96',
    '152.61',
    '151.44',
    '304.05',
    '1,118.01',
    '13,601.46',
    '8.22'],
   ['Isiolo',
    '948.68',
    '531.24',
    '1,479.92',
    '89.82',
    '102.72',
    '192.54',
    '1,672.46',
    '7,202.84',
    '23.22'],
   ['Kajiado',
    '1,526.43',
    '958.65',
    '2,485.08',
    '66.41',
    '3.94',
    '70.35',
    '2,555.43',
    '13,546.89',
    '18.86'],
   ['Kakamega',
    '1,412.75',
    '803.86',
    '2,216.61',
    '382.80',
    '209.40',
    '592.20',
    '2,808.81',
    '17,497.11',
    '16.05'],
   ['Kericho',
    '565.23',
    '871.96',
    '1,437.19',
    '0.99',
    '44.86',
    '45.85',
    '1,483.04',
    '10,491.81',
    '14.14'],
   ['Kiambu',
    '3,400.96',
    '2,201.60',
    '5,602.56',
    '173.28',
    '24.29',
    '197.57',
    '5,800.13',
    '27,202.74',
    '21.32'],
   ['Kilifi*',
    '3,928.16',
    '3,889.24',
    '7,817.40',
    '237.54',
    '36.58',
    '274.12',
    '8,091.52',
    '20,480.85',
    '39.51'],
   ['Kirinyaga', '301.17', '263.30', '564.47', '-', '-', '-', '564.47', '8,541.37', '6.61'],
   ['Kisii',
    '727.21',
    '498.52',
    '1,225.73',
    '13.54',
    '8.43',
    '21.97',
    '1,247.70',
    '20,160.90',
    '6.19'],
   ['Kisumu*', '569.50', '280.97', '850.47', '-', '-', '-', '850.47', '16,982.00', '5.01'],
   ['Kitui', '80.67', '368.83', '449.50', '45.46', '-', '45.46', '494.96', '14,753.53', '3.35'],
   ['Kwale', '176.76', '62.75', '239.51', '-', '71.43', '71.43', '310.94', '16,710.18', '1.86'],
   ['Laikipia*',
    '506.41',
    '380.01',
    '886.42',
    '93.08',
    '3.64',
    '96.72',
    '983.14',
    '9,768.88',
    '10.06'],
   ['Lamu', '1.30', '-', '1.30', '-', '-', '-', '1.30', '5,592.56', '0.02'],
   ['Machakos',
    '2,742.80',
    '1,543.70',
    '4,286.50',
    '207.00',
    '-',
    '207.00',
    '4,493.50',
    '15,193.59',
    '29.57'],
   ['Makueni*', '78.90', '194.90', '273.80', '150.45', '-', '150.45', '424.25', '12,862.92', '3.3'],
   ['Mandera',
    '1,708.90',
    '2,090.10',
    '3,799.00',
    '26.00',
    '-',
    '26.00',
    '3,825.00',
    '15,092.73',
    '25.34'],
   ['Marsabit*',
    '338.80',
    '998.40',
    '1,337.20',
    '8.90',
    '81.50',
    '90.40',
    '1,427.60',
    '11,033.90',
    '12.94'],
   ['Meru',
    '1,216.70',
    '640.90',
    '1,857.60',
    '30.60',
    '13.60',
    '44.20',
    '1,901.80',
    '15,124.98',
    '12.57'],
   ['Migori*',
    '147.40',
    '208.90',
    '356.30',
    '673.36',
    '0.30',
    '673.66',
    '1,029.96',
    '11,972.11',
    '8.82'],
   ['Mombasa',
    '2,542.53',
    '1,248.92',
    '3,791.45',
    '-',
    '53.14',
    '53.14',
    '3,844.59',
    '18,725.00',
    '20.53'],
   ['Murang’a*',
    '1,294.13',
    '110.87',
    '1,405.00',
    '74.90',
    '-',
    '74.90',
    '1,479.90',
    '12,130.58',
    '12.2'],
   ['Nairobi City',
    '77,694.65',
    '8,087.72',
    '85,782.37',
    '962.78',
    '154.23',
    '1,117.01',
    '86,899.38',
    '44,620.89',
    '194.75'],
   ['Nakuru*',
    '2,508.54',
    '496.98',
    '3,005.52',
    '132.15',
    '-',
    '132.15',
    '3,137.67',
    '25,649.10',
    '12.23'],
   ['Nandi', '-', '-', '-', '-', '-', '-', '-', '11,404.54', '0'],
   ['Narok*',
    '2,578.26',
    '1,592.51',
    '4,170.78',
    '74.92',
    '',
    '74.92',
    '4,245.69',
    '17,231.06',
    '24.64'],
   ['Nyamira', '267.97', '89.71', '357.68', '-', '-', '-', '357.68', '8,646.30', '4.14'],
   ['Nyandarua',
    '574.39',
    '1,479.48',
    '2,053.87',
    '70.85',
    '65.78',
    '136.63',
    '2,190.50',
    '9,698.26',
    '22.59'],
   ['Nyeri*', '349.55', '158.16', '507.71', '64.12', '0.23', '64.35', '572.06', '9,441.73', '6.06'],
   ['Samburu', '77.08', '40.17', '117.25', '-', '-', '-', '117.25', '8,105.18', '1.45'],
   ['Siaya',
    '607.23',
    '563.98',
    '1,171.21',
    '105.68',
    '-',
    '105.68',
    '1,276.89',
    '13,377.98',
    '9.54'],
   ['Taita-Taveta',
    '1,475.33',
    '780.39',
    '2,255.72',
    '40.99',
    '-',
    '40.99',
    '2,296.71',
    '8,297.52',
    '27.68'],
   ['Tana River', '1,084.67', '686.61', '1,771.28', '-', '-', '-', '1,771.28', '10,237.38', '17.3'],
   ['Tharaka-Nithi*',
    '554.18',
    '203.11',
    '757.28',
    '97.38',
    '3.92',
    '101.29',
    '858.58',
    '7,777.00',
    '11.04'],
   ['Trans Nzoia',
    '950.00',
    '1,333.99',
    '2,283.99',
    '19.08',
    '71.00',
    '90.08',
    '2,374.07',
    '10,266.19',
    '23.13'],
   ['Turkana*',
    '894.92',
    '1,929.70',
    '2,824.62',
    '39.67',
    '213.20',
    '252.87',
    '3,077.49',
    '19,236.19',
    '16'],
   ['Uasin Gishu', '708.56', '445.16', '1,153.72', '-', '-', '-', '1,153.72', '17,427.22', '6.62'],
   ['Vihiga', '304.46', '486.11', '790.57', '-', '20.67', '20.67', '811.24', '7,926.21', '10.23'],
   ['Wajir',
    '876.72',
    '2,230.60',
    '3,107.32',
    '-',
    '197.52',
    '197.52',
    '3,304.84',
    '13,638.52',
    '24.23'],
   ['West Pokot', '188.63', '112.96', '301.59', '-', '-', '-', '301.59', '8,986.20', '3.36']]),
 (53,
  [['County',
    'County Executive (Kshs. Million)',
    None,
    None,
    'County Assembly (Kshs. Million)',
    None,
    None,
    'Grand Total\n(Kshs. Mil-\nlion)',
    'FY 2025/26\nBudget',
    '% of\nPending\nBill to\nBudget'],
   [None,
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    'Recur-\nrent',
    'Develop-\nment',
    'Sub-Total',
    None,
    None,
    None],
   ['Total',
    '121,630.38',
    '44,520.96',
    '166,151.34',
    '4,744.82',
    '1,630.53',
    '6,375.35',
    '172,526.69',
    '648,234.41',
    '26.61']]),
 (53,
  [['County',
    'County Executives Ageing analysis (Amount in Kshs.Millions)',
    None,
    None,
    None,
    'Total (Kshs.\nMillions)'],
   [None, 'Under one year', '1-2 years', '2-3 years', 'Over 3 years', None],
   ['Baringo', '558.05', '247.48', '-', '-', '805.54'],
   ['Bomet*', '1,107.00', '174.29', '22.65', '87.45', '1,391.39'],
   ['Bungoma*', '803.49', '965.71', '438.69', '913.34', '3,121.24'],
   ['Busia', '1,129.65', '673.75', '207.55', '59.98', '2,070.93'],
   ['Elgeyo-Marakwet', '236.30', '0.21', '2.20', '-', '238.71'],
   ['Embu', '449.18', '273.03', '2.99', '822.34', '1,547.54'],
   ['Garissa', '909.00', '294.57', '-', '182.98', '1,386.55'],
   ['Homa Bay', '416.55', '230.80', '88.30', '78.31', '813.96'],
   ['Isiolo', '500.61', '408.65', '60.99', '509.32', '1,479.58'],
   ['Kajiado', '144.18', '1,178.77', '475.29', '686.84', '2,485.08'],
   ['Kakamega', '1,239.48', '918.12', '59.02', '-', '2,216.61'],
   ['Kericho', '252.18', '840.79', '284.67', '59.55', '1,437.19'],
   ['Kiambu', '1,473.32', '686.92', '236.84', '3,205.49', '5,602.56'],
   ['Kilifi*', '1,680.43', '2,897.13', '1,640.17', '1,599.67', '7,817.40'],
   ['Kirinyaga', '149.18', '126.93', '5.38', '282.99', '564.47'],
   ['Kisii', '1,065.36', '153.13', '5.57', '1.67', '1,225.73'],
   ['Kisumu*', '251.57', '156.19', '52.98', '389.72', '850.47'],
   ['Kitui', '377.74', '57.65', '8.07', '6.04', '449.50'],
   ['Kwale', '43.05', '196.33', '0.14', '-', '239.51'],
   ['Laikipia*', '341.31', '124.63', '126.97', '293.51', '886.42'],
   ['Lamu', '1.31', '0.00', '0.00', '0.00', '1.31'],
   ['Machakos', '1,846.50', '483.10', '558.50', '1,398.40', '4,286.50'],
   ['Makueni*', '267.30', '5.60', '0.90', '0.00', '273.80'],
   ['Mandera', '2,202.80', '0.00', '778.00', '817.40', '3,798.20'],
   ['Marsabit*', '579.10', '29.70', '353.50', '374.90', '1,337.20'],
   ['Meru', '1,448.00', '137.80', '212.40', '59.40', '1,857.60'],
   ['Migori*', '37.30', '62.10', '248.70', '8.00', '356.10']])]

FY2425_TABLE_PAGES = [(58,
  [['County',
    'Budget (Kshs.)',
    'Expenditure (Kshs.)',
    'Absorption (%)',
    'No. of MCAs',
    'Average monthly\nsitting allowances\nper MCA (Kshs.)'],
   [None, 'A', 'B', 'C=B/A100', 'D', 'E=B/D/12'],
   ['Mombasa', '27,559,700', '27,488,200', '100', '43', '53,272'],
   ['Murang’a', '38,937,600', '38,936,016', '100', '48', '67,597'],
   ['Nairobi', '70,000,000', '45,686,200', '65', '124', '30,703'],
   ['Nakuru', '53,000,000', '44,616,190', '84', '76', '48,921'],
   ['Nandi', '27,456,000', '27,455,999', '100', '45', '50,844'],
   ['Narok', '41,113,760', '40,613,200', '99', '50', '67,689'],
   ['Nyamira', '41,184,012', '33,179,773', '81', '36', '76,805'],
   ['Nyandarua', '32,603,498', '30,741,700', '94', '42', '60,995'],
   ['Nyeri', '20,200,000', '18,838,300', '93', '43', '36,508'],
   ['Samburu', '26,000,000', '25,789,100', '99', '25', '85,964'],
   ['Siaya', '30,235,119', '29,745,100', '98', '42', '59,018'],
   ['Taita-Taveta', '36,000,000', '23,238,700', '65', '32', '60,517'],
   ['Tana River', '34,611,200', '29,849,600', '86', '27', '92,128'],
   ['Tharaka-Nithi', '31,200,000', '31,200,000', '100', '24', '108,333'],
   ['Trans Nzoia', '23,890,898', '23,890,898', '100', '34', '58,556'],
   ['Turkana', '30,160,850', '10,870,200', '36', '48', '18,872'],
   ['Uasin Gishu', '39,918,400', '38,918,400', '97', '45', '72,071'],
   ['Vihiga', '30,680,000', '30,547,520', '100', '37', '68,801'],
   ['Wajir', '31,715,300', '31,715,300', '100', '46', '57,455'],
   ['West Pokot', '29,884,000', '29,883,738', '100', '33', '75,464'],
   ['Total', '1,804,316,121', '1,565,947,437', '87', '2,219', '58,808']]),
 (58,
  [['County',
    'County Executive (Kshs. Million)',
    None,
    None,
    'County Assembly (Kshs. Million)',
    None,
    None,
    'Grand\nTotal (Kshs.\nMillion)',
    'FY\n2024/25\nBudget\n(Kshs.\nMillion)',
    None,
    '% of\nPending\nBill to\nBudget'],
   [None,
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    None,
    None,
    None,
    None],
   ['Baringo', '202.3', '143.9', '346.3', '-', '-', '-', '346.3', '8,983.76', None, '4'],
   ['Bomet',
    '600',
    '857.4',
    '1,457.40',
    '20.1',
    '45.8',
    '65.9',
    '1,523.20',
    '9,831.70',
    None,
    '15'],
   ['Bungoma',
    '2,227.50',
    '1,368.50',
    '3,596.00',
    '14.7',
    '-',
    '14.7',
    '3,610.70',
    '16,704.46',
    None,
    '22'],
   ['Busia',
    '1,382.30',
    '1,258.90',
    '2,641.20',
    '620.5',
    '-',
    '620.5',
    '3,261.70',
    '10,770.15',
    None,
    '30'],
   ['Elgeyo-Marakwet', '3.1', '9.1', '12.1', '-', '-', '-', '12.1', '7,899.87', None, '0'],
   ['Embu', '924.2', '822.7', '1,746.90', '16.2', '-', '16.2', '1,763.10', '8,533.54', None, '21'],
   [None, None, None, None, None, None, None, None, None, '14', None]]),
 (59,
  [['County',
    'County Executive (Kshs. Million)',
    None,
    None,
    'County Assembly (Kshs. Million)',
    None,
    None,
    'Grand\nTotal (Kshs.\nMillion)',
    'FY\n2024/25\nBudget\n(Kshs.\nMillion)',
    '% of\nPending\nBill to\nBudget'],
   [None,
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    'Recurrent',
    'Develop-\nment',
    'Sub-Total',
    None,
    None,
    None],
   ['Garissa',
    '747.2',
    '1,677.40',
    '2,424.60',
    '116.3',
    '45',
    '161.3',
    '2,585.90',
    '12,005.81',
    '22'],
   ['Homa Bay',
    '715.1',
    '726.1',
    '1,441.30',
    '102.6',
    '94.3',
    '197',
    '1,638.20',
    '13,130.57',
    '12'],
   ['Isiolo', '786.9', '209.8', '996.7', '5.8', '8.1', '13.9', '1,010.60', '6,805.05', '15'],
   ['Kajiado',
    '1,087.50',
    '1,458.20',
    '2,545.70',
    '30.6',
    '69.6',
    '100.2',
    '2,646.00',
    '12,786.47',
    '21'],
   ['Kakamega', '773.6', '938.2', '1,711.90', '454.4', '-', '454.4', '2,166.30', '17,646.79', '12'],
   ['Kericho', '661.3', '1,367.00', '2,028.30', '-', '53.8', '53.8', '2,082.10', '9,756.94', '21'],
   ['Kiambu',
    '4,259.90',
    '3,352.70',
    '7,612.60',
    '244',
    '31.2',
    '275.2',
    '7,887.90',
    '23,480.38',
    '34'],
   ['Kilifi',
    '3,820.10',
    '5,367.40',
    '9,187.40',
    '68.2',
    '-',
    '68.2',
    '9,255.60',
    '21,406.50',
    '43'],
   ['Kirinyaga', '316.2', '486.7', '802.9', '-', '-', '-', '802.9', '7,925.71', '10'],
   ['Kisii', '594.5', '401.8', '996.3', '8.2', '28.4', '36.6', '1,033.00', '15,155.35', '7'],
   ['Kisumu', '507.8', '838', '1,345.90', '2.5', '2.1', '4.6', '1,350.50', '15,314.33', '9'],
   ['Kitui', '173.7', '56.1', '229.9', '-', '-', '-', '229.9', '14,305.36', '2'],
   ['Kwale',
    '654.5',
    '915.5',
    '1,570.00',
    '187.5',
    '142.1',
    '329.6',
    '1,899.60',
    '14,876.06',
    '13'],
   ['Laikipia', '856.3', '999.7', '1,856.00', '10.4', '', '10.4', '1,866.40', '8,479.54', '22'],
   ['Lamu', '32.1', '-', '32.1', '', '', '-', '32.1', '4,988.65', '1'],
   ['Machakos',
    '3,785.10',
    '2,695.10',
    '6,480.10',
    '251.7',
    '1.9',
    '253.6',
    '6,733.80',
    '15,622.16',
    '43'],
   ['Makueni', '558', '98.6', '656.6', '161.5', '', '161.5', '818.2', '11,580.21', '7'],
   ['Mandera', '968.3', '1,525.40', '2,493.70', '', '6.1', '6.1', '2,499.80', '14,567.55', '17'],
   ['Marsabit',
    '532.5',
    '700.2',
    '1,232.60',
    '30.6',
    '170.6',
    '201.2',
    '1,433.80',
    '10,318.61',
    '14'],
   ['Meru', '829.7', '848.7', '1,678.40', '63.5', '', '63.5', '1,741.90', '13,108.95', '13'],
   ['Migori', '475.9', '361.4', '837.2', '184.6', '36.4', '220.9', '1,058.10', '12,147.01', '9'],
   ['Mombasa',
    '2,439.40',
    '1,310.80',
    '3,750.10',
    '117.5',
    '',
    '117.5',
    '3,867.70',
    '17,360.00',
    '22'],
   ["Murang'a", '1,588.10', '333.4', '1,921.50', '72.2', '', '72.2', '1,993.70', '10,743.65', '19'],
   ['Nairobi',
    '78,949.10',
    '7,169.40',
    '86,118.60',
    '650.6',
    '',
    '650.6',
    '86,769.20',
    '43,564.27',
    '199'],
   ['Nakuru', '2,850.40', '668.7', '3,519.20', '158', '', '158', '3,677.20', '23,980.40', '15'],
   ['Nandi', '476', '495.7', '971.7', '-', '13.5', '13.5', '985.1', '10,188.22', '10'],
   ['Narok', '3,962.60', '2,188.90', '6,151.50', '', '', '', '6,151.50', '17,567.52', '35'],
   ['Nyamira', '218', '114.2', '332.2', '-', '8.2', '8.2', '340.4', '8,102.90', '4'],
   ['Nyandarua', '571.6', '869.1', '1,440.70', '71.3', '', '71.3', '1,512.00', '8,779.76', '17'],
   ['Nyeri', '321.1', '27.8', '348.9', '6', '', '6', '354.9', '9,004.03', '4'],
   ['Samburu', '35', '140.6', '175.5', '46.4', '9.3', '55.7', '231.3', '7,382.22', '3'],
   ['Siaya', '832.9', '1,057.00', '1,890.00', '', '', '-', '1,890.00', '10,948.13', '17'],
   ['Taita-Taveta',
    '1,364.40',
    '653.1',
    '2,017.50',
    '38.4',
    '',
    '38.4',
    '2,055.90',
    '8,179.70',
    '25'],
   ['Tana River', '1,293.18', '1,060.06', '2,353.25', '0', '', '0', '2,353.25', '9,177.72', '26'],
   ['Tharaka-Nithi', '468.6', '176.2', '644.7', '82.9', '13.9', '96.8', '741.6', '7,005.68', '11'],
   ['Trans Nzoia', '805.4', '703', '1,508.40', '', '', '-', '1,508.40', '10,455.02', '14'],
   ['Turkana', '43.6', '1,141.50', '1,185.10', '', '144.3', '144.3', '1,329.30', '17,213.59', '8'],
   ['Uasin Gishu', '199.7', '863.6', '1,063.20', '57.7', '', '57.7', '1,121.00', '15,179.79', '7'],
   ['Vihiga', '211.2', '621', '832.2', '', '', '-', '832.2', '7,105.90', '12'],
   ['Wajir',
    '1,324.10',
    '2,155.00',
    '3,479.10',
    '233.5',
    '',
    '233.5',
    '3,712.60',
    '13,517.62',
    '27'],
   ['West Pokot', '215.3', '75', '290.3', '21.5', '', '21.5', '311.8', '8,101.51', '4'],
   ['Total',
    '126,645.28',
    '51,308.56',
    '177,953.75',
    '4,149.90',
    '924.60',
    '5,074.50',
    '183,028.75',
    '601,689.11',
    '30']])]

FY2526_TOC_LINES = ['Table 2.10: Trade Payables for the Counties as of 30 June 2026 '
 '.............................................................................................17',
 'Table 2.11: Trade Payables Ageing Analysis for County Executives as of 30 June 2026 '
 '............................................................19',
 'Table 2.12: Trade Payables Ageing Analysis for County Assemblies as of 30 June 2026 '
 '...........................................................20',
 'Table 2.13: Salary Arrears and Statutory Deductions Trade Payables as of 30 June 2026 '
 '.........................................................22',
 'Table 3.15: Baringo County Trade Payables as of 30 June '
 '2026..............................................................................................41',
 'Table 3.16: Baringo County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.......................................................41',
 'Table 3.17: Baringo County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................42',
 'Table 3.31: Bomet County Trade Payables as of 30 June 2026 '
 '...............................................................................................57',
 'Table 3.32: Bomet County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '........................................................58',
 'Table 3.33: Bomet County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '........................................................58',
 'Table 3.47: Bungoma County Trade Payables as of 30 June 2026 '
 '..........................................................................................75',
 'Table 3.48: Bungoma County Executive Trade Payables Ageing Analysis as of 30 June '
 '2026....................................................75',
 'Table 3.49: Bungoma County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................76',
 'Table 3.63: Busia County Trade Payables as of 30 Jun 2026 '
 '..................................................................................................91',
 'Table 3.64: Busia County Executive Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '...........................................................91',
 'Table 3.65: Busia County Assembly Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '...........................................................91',
 'Table 3.80: Elgeyo Marakwet County Trade Payables as of 30 June 2026 '
 '..............................................................................108',
 'Table 3.81: Elgeyo Marakwet County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.......................................108',
 'Table 3.93: Embu County Trade Payables as of 30 June 2026 '
 '..............................................................................................126',
 'Table 3.94: Embu County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.......................................................126',
 'Table 3.95: Embu County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.......................................................126',
 'Table 3.110: Garissa County Trade Payables as of 30th June 2026 '
 '.......................................................................................145',
 'Table 3.111: Garissa County Executive Trade Payables Ageing Analysis as of 30th June 2026 '
 '................................................145',
 'Table 3.112: Garissa County Assembly Trade Payables Ageing Analysis as of 30th June 2026 '
 '...............................................145',
 'Table 3.126: Homa Bay County Trade Payables as of 30 June 2026 '
 '.....................................................................................161',
 'Table 3.127: Homa Bay County Executive Trade Payables Ageing Analysis as of 30 June '
 '2026...............................................162',
 'Table 3.128: Homa Bay County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..............................................162',
 'Table 3.142: Isiolo County Trade Payables as of 30 Jun 2026 '
 '...............................................................................................180',
 'Table 3.143: Isiolo County Executive Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '........................................................181',
 'Table 3.144: Isiolo County Assembly Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '.......................................................181',
 'Table 3.158: Kajiado County Trade Payables as of 30 June 2026 '
 '..........................................................................................198',
 'Table 3.159: Kajiado County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................199',
 'Table 3.160: Kajiado County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................199',
 'Table 3.174: Kakamega County Trade Payables as of 30 June 2026 '
 '.....................................................................................219',
 'Table 3.175: Kakamega County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '..............................................219',
 'Table 3.176: Kakamega County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..............................................219',
 'Table 3.191: Kericho County Trade Payables as of 30 June 2026 '
 '..........................................................................................238',
 'Table 3.192: Kericho County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................239',
 'Table 3.193: Kericho County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..................................................239',
 'Table 3.208: Kiambu County Trade Payables as of 30 June 2026 '
 '..........................................................................................259',
 'Table 3.209: Kiambu County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................259',
 'Table 3.210: Kiambu County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..................................................259',
 'Table 3.223: Kirinyaga County Trade Payables as of 30 June 2026 '
 '........................................................................................275',
 'Table 3.224: Kirinyaga County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................276',
 'Table 3.238: Kilifi County Trade Payables as of 30 June 2026 '
 '...............................................................................................293',
 'Table 3.239: Kilifi County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '........................................................294',
 'Table 3.240: Kilifi County Assembly Trade Payables Ageing Analysis as of 30 June '
 '2026........................................................294',
 'Table 3.253: Kisii County Trade Payables as of 30 Jun 2026 '
 '.................................................................................................312',
 'Table 3.254: Kisii County Executive Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '..........................................................312',
 'Table 3.255: Kisii County Assembly Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '..........................................................313',
 'Table 3.267: Kisumu County Trade Payables as of 30 June 2026 '
 '..........................................................................................330',
 'Table 3.268: Kisumu County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................331',
 'Table 3.282: Kitui County Trade Payables as of 30 June '
 '2026...............................................................................................348',
 'Table 3.283: Kitui County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '........................................................348',
 'Table 3.284: Kitui County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.......................................................349',
 'Table 3.298: Kwale County Trade Payables as of 30 June 2026 '
 '............................................................................................366',
 'Table 3.299: Kwale County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................367',
 'Table 3.300: Kwale County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................367',
 'Table 3.313: Laikipia County Trade Payables as of 30 June '
 '2026..........................................................................................383',
 'Table 3.314: Laikipia County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................384',
 'Table 3.315: Laikipia County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..................................................384',
 'Table 3.329: Lamu County Trade Payables as of 30 June 2026 '
 '............................................................................................402',
 'Table 3.330: Lamu County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................403',
 'Table 3.344: Machakos County Trade Payables as of 30 June 2026 '
 '......................................................................................425',
 'Table 3.345: Machakos County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...............................................425',
 'Table 3.346: Machakos County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..............................................426',
 'Table 3.360: Makueni County Trade Payables as of 30 June 2026 '
 '........................................................................................445',
 'Table 3.361: Makueni County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................446',
 'Table 3.362: Makueni County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................446',
 'Table 3.375: Mandera County Trade Payables as of 30 June 2026 '
 '........................................................................................463',
 'Table 3.376: Mandera County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................463',
 'Table 3.377: Mandera County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '................................................464',
 'Table 3.391: Marsabit County Trade Payables as of 30 June 2026 '
 '........................................................................................483',
 'Table 3.392: Marsabit County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................484',
 'Table 3.393: Marsabit County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.................................................484',
 'Table 3.409: Meru County Trade Payables as of 30 June 2026 '
 '.............................................................................................508',
 'Table 3.410: Meru County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................508',
 'Table 3.411: Meru County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................509',
 'Table 3.423: Migori County Trade Payables as of 30 June 2026 '
 '............................................................................................527',
 'Table 3.424: Migori County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................527',
 'Table 3.425: Migori County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................527',
 'Table 3.439: Mombasa County Trade Payables as of 30 Jun 2026 '
 '........................................................................................545',
 'Table 3.440: Mombasa County Executive Trade Payables Ageing Analysis as of 30 Jun 2026 '
 '.................................................546',
 'Table 3.441: Mombasa County Assembly Trade Payables Ageing Analysis as of 30 Jun '
 '2026.................................................546',
 'Table 3.454: Muranga County Trade Payables as of 30 June 2026 '
 '........................................................................................563',
 'Table 3.455: Murang’a County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '................................................563',
 'Table 3.456: Murang’a County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '................................................564',
 'Table 3.470: Nairobi City County Trade Payables as of 30th June 2026 '
 '................................................................................586',
 'Table 3.471: Nairobi City County Executive Trade Payables Ageing Analysis as of 30th June '
 '2026..........................................587',
 'Table 3.472: Nairobi City County Assembly Trade Payables Ageing Analysis as of 30th June 2026 '
 '.........................................587',
 'Table 3.486: Nakuru County Trade Payables as of 30 June 2026 '
 '..........................................................................................607',
 'Table 3.487: Nakuru County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................608',
 'Table 3.488: Nakuru County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '...................................................608',
 'Table 3.513: Narok County Trade Payables as of 30th June 2026 '
 '.........................................................................................640',
 'Table 3.514: Narok County Executive Trade Payables Ageing Analysis as of 30th June 2026 '
 '..................................................640',
 'Table 3.527: Nyamira County Trade Payables as of 30 June 2026 '
 '........................................................................................656',
 'Table 3.528: Nyamira County Executive Trade Payables Ageing Analysis as of 30 June '
 '2026..................................................656',
 'Table 3.543: Nyandarua County Trade Payables as of 30 June 2026 '
 '....................................................................................676',
 'Table 3.544: Nyandarua County Executive Trade Payables Ageing Analysis as of 30 June '
 '2026..............................................676',
 'Table 3.545: Nyandarua County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.............................................676',
 'Table 3.557: Nyeri County Trade Payables as of 30 June 2026 '
 '.............................................................................................692',
 'Table 3.558: Nyeri County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................692',
 'Table 3.559: Nyeri County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................693',
 'Table 3.574: Samburu County Trade Payables as of 30 June, 2026 '
 '......................................................................................711',
 'Table 3.575: Samburu County Executive trade payables Ageing Analysis as of 30 June, 2026 '
 '................................................711',
 'Table 3.588: Siaya County Trade Payables as of 30 June 2026 '
 '.............................................................................................727',
 'Table 3.589: Siaya County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................728',
 'Table 3.590: Siaya County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................728',
 'Table 3.603: Taita Taveta County Trade Payables as of 30 June 2026 '
 '....................................................................................745',
 'Table 3.604: Taita Taveta County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.............................................745',
 'Table 3.605: Taita Taveta County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '............................................745',
 'Table 3.617: Tana River County Trade Payables as of 30 June 2026 '
 '......................................................................................761',
 'Table 3.618: Tana River County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '...............................................762',
 'Table 3.632: Tharaka Nithi County Trade Payables as of 30 June 2026 '
 '.................................................................................778',
 'Table 3.633: Tharaka Nithi County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '..........................................779',
 'Table 3.634: Tharaka Nithi County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..........................................779',
 'Table 3.648: Trans Nzoia County Trade Payables as of 30 June 2026 '
 '....................................................................................795',
 'Table 3.649: Trans Nzoia County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.............................................795',
 'Table 3.650: Trans Nzoia County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '............................................795',
 'Table 3.662: Turkana County Trade Payables as of 30 June 2026 '
 '.........................................................................................811',
 'Table 3.663: Turkana County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '..................................................811',
 'Table 3.664: Turkana County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '..................................................811',
 'Table 3.678: Uasin Gishu County Trade Payables as of 30 June 2026 '
 '...................................................................................827',
 'Table 3.679: Uasin Gishu County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '............................................827',
 'Table 3.680: Uasin Gishu County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '...........................................828',
 'Table 3.694: Vihiga County Trade Payables as of 30 June 2026 '
 '............................................................................................845',
 'Table 3.695: Vihiga County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................846',
 'Table 3.696: Vihiga County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '.....................................................846',
 'Table 3.709: Wajir County Trade Payables as of 30 June 2026 '
 '.............................................................................................861',
 'Table 3.710: Wajir County Executive Trade Payables Ageing Analysis as of 30 June '
 '2026.......................................................862',
 'Table 3.711: Wajir County Assembly Trade Payables Ageing Analysis as of 30 June 2026 '
 '......................................................862',
 'Table 3.724: West Pokot County Trade Payables as of 30 June 2026 '
 '....................................................................................879',
 'Table 3.725: West Pokot County Executive Trade Payables Ageing Analysis as of 30 June 2026 '
 '.............................................880']

FY2526_CHAPTER_BLOCKS = {'Uasin Gishu': {'table': '3.678',
                 'pdf_page': 861,
                 'text': 'Table 3.678: Uasin Gishu County Trade Payables as of 30 June 2026\n'
                         'Development Recurrent\n'
                         'County Entity Total (Kshs.)\n'
                         '(Kshs.) (Kshs.)\n'
                         'County Executive 199,652,333 1,238,530,152 1,438,182,484\n'
                         'As at 01 July 2025 (End of FY\n'
                         'a County Assembly - 113,579,633 113,579,633\n'
                         '2024/25)\n'
                         'Total 199,652,333 1,352,109,785 1,551,762,117\n'
                         'County Executive - - -\n'
                         'Trade payables scheduled to be\n'
                         'settled in FY 2025/26 per the action b County Assembly - - -\n'
                         'plan\n'
                         'Total - - -\n'
                         'County Executive 175,200,328 560,391,303 735,591,631\n'
                         'Amount paid in FY 2025/26 c County Assembly 38,748,929 38,748,929\n'
                         'Total 175,200,328 599,140,232 774,340,560\n'
                         'County Executive 231,480,234 472,534,211 704,014,446\n'
                         'Trade Payables Incurred in FY\n'
                         'd County Assembly - - -\n'
                         '2025/26\n'
                         'Total 231,480,234 - 704,014,446\n'
                         'County Executive 255,932,238 1,150,673,060 1,406,605,299\n'
                         'Outstanding trade payables as of\n'
                         'e=a-c*b County Assembly - 74,830,704 74,830,704\n'
                         '30 June 2026\n'
                         'Total 255,932,238 752,969,552 1,481,436,003\n'},
 'Nairobi City': {'table': '3.470',
                  'pdf_page': 620,
                  'text': 'Table 3.470: Nairobi City County Trade Payables as of 30th June 2026\n'
                          'County Entity Development (Kshs.) Recurrent (Kshs.) Total (Kshs.)\n'
                          'County Executive 7,486,464,308 75,345,454,633 82,831,918,941\n'
                          'As at 1 July 2025 (End\n'
                          'County Assembly - 271,237,059 271,237,059\n'
                          'of FY 2024/25)\n'
                          'Total 7,486,464,308 75,616,691,692 83,103,156,000\n'
                          'County Executive 654,825,235 7,756,597,108 8,411,422,343\n'
                          'Amount paid in FY\n'
                          'County Assembly - 40,489,020 40,489,020\n'
                          '2025/26\n'
                          'Total 654,825,235 7,797,086,128 8,451,911,363\n'
                          'COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT\n'
                          'FOR FY 2025/26, AUGUST, 2026 586\n'
                          'County Entity Development (Kshs.) Recurrent (Kshs.) Total (Kshs.)\n'
                          'County Executive 1,256,084,756 10,105,791,680 11,781,726,782\n'
                          'Trade Payables In-\n'
                          'County Assembly 154,234,050 419,850,356 574,084,406\n'
                          'curred in FY 2025/26\n'
                          'Total 1,410,318,806 10,525,642,036 12,355,811,188\n'
                          'County Executive 8,087,723,819 77,694,649,205 85,782,373,024\n'
                          'Outstanding Trade\n'
                          'Payables as of 30 June County Assembly 154,234,050 962,777,153 '
                          '1,117,011,203\n'
                          '2026 (Kshs.)\n'
                          'Total 8,241,957,869 78,657,426,358 86,899,384,227\n'},
 'Busia': {'table': '3.63',
           'pdf_page': 125,
           'text': 'Table 3.63: Busia County Trade Payables as of 30 Jun 2026\n'
                   'Development\n'
                   'County Entity Recurrent (Kshs.) Total (Kshs.)\n'
                   '(Kshs.)\n'
                   'County Executive 1, 258, 115, 665 1, 395, 958, 621 2, 654, 074, 286\n'
                   'As at 1 Jul 2025 (End of FY\n'
                   'a County Assembly - 620, 481, 377 620, 481, 377\n'
                   '2024/25)\n'
                   'Total 1, 258, 115, 665 2, 016, 439, 998 3, 274, 555, 663\n'
                   'County Executive 272, 879, 639\n'
                   'Trade payables scheduled\n'
                   'to be settled in FY 2025/26 b County Assembly 51, 706, 781 51, 706, 781\n'
                   'per the action plan\n'
                   'Total - - 324, 586, 420\n'
                   'County Executive 356, 943, 132 226, 201, 535 583, 943, 132\n'
                   'Amount paid in FY 2025/26 c County Assembly - 97, 040, 040 97, 040, 040\n'
                   'Total 356, 943, 132 323, 241, 575 680, 184, 707\n'
                   'County Executive - - -\n'
                   'Trade Payables Incurred in\n'
                   'd County Assembly - - -\n'
                   'FY 2025/26\n'
                   'Total - - -\n'
                   'County Executive 901,172,533 1,169,757,086 2,070,929,619\n'
                   'Outstanding trade paya-\n'
                   'e=a-c*b County Assembly - 523, 441,337 523,441,337\n'
                   'bles as of 30 Jun 2026\n'
                   'Total 901,172,533 1,693,198,423 2,594,370,956\n'},
 'Baringo': {'table': '3.15',
             'pdf_page': 75,
             'text': 'Table 3.15: Baringo County Trade Payables as of 30 June 2026\n'
                     'Development\n'
                     'County Entity Recurrent (Kshs.) Total (Kshs.)\n'
                     '(Kshs.)\n'
                     'County Executive 217,316,203 178,302,220 395,618,423\n'
                     'As at 1 July 2025 (End of FY\n'
                     'a County Assembly - 81,526,122.61 81,526,123\n'
                     '2024/25)\n'
                     'Total 217,316,203 259,828,342 477,144,545\n'
                     'County Executive - - -\n'
                     'Trade payables scheduled to be\n'
                     'settled in FY 2025/26 per the b County Assembly - - -\n'
                     'action plan\n'
                     'Total - - -\n'
                     'County Executive 121,703,942 26,433,408 148,137,350\n'
                     'Amount paid in FY 2025/26 c County Assembly - 71,089,115 71,089,115\n'
                     'Total 121,703,942 97,522,523 219,226,465\n'
                     'County Executive 234,491,153 323,562,880 558,054,033\n'
                     'Trade Payables Incurred in FY\n'
                     'd County Assembly - 54,259,316 54,259,316\n'
                     '2025/26\n'
                     'Total 234,491,153 377,822,196 612,313,349\n'
                     'County Executive 330,103,414 475,431,692 805,535,106\n'
                     'Outstanding trade payables\n'
                     'e=a-c*b County Assembly 64,696,324 64,696,324\n'
                     'as of 30 June 2026\n'
                     'Total 330,103,414 540,128,016 870,231,430\n'},
 'Kiambu': {'table': '3.208',
            'pdf_page': 293,
            'text': 'Table 3.208: Kiambu County Trade Payables as of 30 June 2026\n'
                    'County Entity Development Recurrent Total\n'
                    'County Executive 2,939,091,025 3,059,846,711 5,998,937,737\n'
                    'As at 01 July 2025 (End of FY\n'
                    'County Assembly 31,208,201 184,675,237 215,883,438\n'
                    '2024/25)\n'
                    'Total 2,970,299,226 3,244,521,948 6,214,821,175\n'
                    'County Executive 1,201,591,114 675,712,555 1,877,303,669\n'
                    'Amount paid in FY 2025/26 County Assembly 6,923,064 11,390,352 18,313,416\n'
                    'Total 1,208,514,178 687,102,907 1,895,617,085\n'
                    'County Executive 464,100,433 1,016,830,140 1,480,930,573\n'
                    'Trade Payables Incurred in FY\n'
                    'County Assembly - - -\n'
                    '2025/26\n'
                    'Total 464,100,433 1,016,830,140 1,480,930,573\n'
                    'County Executive 2,201,600,344 3,400,964,296 5,602,564,641\n'
                    'Outstanding Trade Payables as\n'
                    'County Assembly 24,285,137 173,284,885 197,570,022\n'
                    'of 30 June 026 (Kshs.)\n'
                    'Total 2,225,885,481 3,574,249,181 5,800,134,663\n'}}

FY2425_CHAPTER_BLOCKS = {'3.364': {'pdf_page': 393,
           'text': 'Table 3.364: Nairobi City County Pending Bills as of 30 June 2025\n'
                   'Pending bills Outstanding pending\n'
                   'Pending Bills as of 1 July Settled Pending Bills in Reconciliation FY\n'
                   'incurred in FY bills as of 30 June\n'
                   '2024 (Kshs.) FY 2024/25 (Kshs.) 2024/25 (Kshs.)\n'
                   '2024/25 (Kshs.) 2025 (Kshs.)\n'
                   'County Executive\n'
                   'Recurrent 115,950,137,670 5,843,218,662 7,694,727,638 -38,852,521,872 '
                   '78,949,124,774\n'
                   'Development 5,314,677,553 1,719,061,965 1,505,670,449 2,068,143,926 '
                   '7,169,429,963\n'
                   'Total 121,264,815,223 7,562,280,627 9,200,398,087 -36,784,377,946 '
                   '86,118,554,737\n'
                   'County Assembly\n'
                   'Recurrent 509,956,792 281,212,753 419,850,356 2,004,000 650,598,395\n'
                   'Development 3,962,461 1,958,461 0 -2,004,000 -\n'
                   'Total 513,919,253 283,171,214 419,850,356 - 650,598,395\n'},
 '3.3': {'pdf_page': 67,
         'text': 'Table 3.3: Baringo County Pending Bills as of 30 June 2025\n'
                 'Outstanding\n'
                 'Pending Bills as of 1 Settled Pending Bills in Pending bills incurred pending '
                 'bills as\n'
                 'July 2024 (Kshs.) FY 2024/25 (Kshs.) in FY 2024/25 (Kshs.) of 30 June 2025\n'
                 '(Kshs.)\n'
                 'County Executive\n'
                 'Recurrent 234,639,790 234,639,790 202,316,202.88 202,316,202.88\n'
                 'Development 240,387,648 240,387,648 143,949,619.67 143,949,619.67\n'
                 'Total 475,027,438 475,027,438 346,265,822.55 346,265,822.55\n'
                 'County Assembly\n'
                 'Recurrent 11,446,032.16 11,446,032.16 0 0\n'
                 'Development 103,005,438 103,005,438 22,184,466 0\n'
                 'Total 114,451,470.16 114,451,470.16 22,184,466 -\n'
                 'Total 589,478,908.16 589,478,908.16 368,450,288.55 346,265,822.55\n'}}


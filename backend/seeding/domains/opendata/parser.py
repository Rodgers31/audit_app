"""Static Table 5.13, source-bound cells and unaltered published discrepancies.

Only the reviewed workbook hash is admitted, before any ZIP/XML processing.
No formulas run, no unknown edition is inferred, no missing value becomes zero.
"""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
from io import BytesIO
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from .source import ARTIFACT_BYTES, SHA256, OpenDataSourceRefused

EXTRACTOR = 'knbs-economic-survey-2026-table-5.13-v1'
SHEET = 'Table 5.13'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
COUNTIES = ("Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita/Taveta", "Garissa", "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua", "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana", "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu", "Elgeyo/Marakwet", "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi City")
GROUPS = ((2, 12, 'equitable_share', 'Equitable Share Grant'), (13, 23, 'conditional_grant', 'Conditional Grant1'), (24, 25, 'unconditional_grant', 'Unconditional Grant2'), (26, 36, 'own_source_revenue', 'Annual Own Source Revenue'), (37, 47, 'total_revenue', 'Total Revenue'))


def column(n):
    result = ''
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _read_cells(payload):
    with ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 200 or sum(i.file_size for i in archive.infolist()) > 8 * 1024 * 1024:
            raise OpenDataSourceRefused('OpenData workbook archive shape refused')
        shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
        strings = [''.join(item.itertext()) for item in shared.findall('s:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = [s for s in workbook.findall('s:sheets/s:sheet', NS) if s.get('name') == SHEET]
        if len(sheets) != 1:
            raise OpenDataSourceRefused('OpenData requires the exact reviewed sheet')
        rid = sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = [r.get('Target') for r in rels if r.get('Id') == rid and r.get('TargetMode') is None]
        if len(targets) != 1 or not re.fullmatch(r'worksheets/sheet[0-9]+\.xml', targets[0]):
            raise OpenDataSourceRefused('OpenData sheet relationship refused')
        sheet = ET.fromstring(archive.read('xl/' + targets[0]))
        cells = {}
        for cell in sheet.findall('s:sheetData/s:row/s:c', NS):
            ref = cell.get('r')
            if ref in cells or cell.find('s:f', NS) is not None:
                raise OpenDataSourceRefused('OpenData duplicate or formula cell refused')
            value = cell.find('s:v', NS)
            raw = value.text if value is not None else None
            kind = cell.get('t', 'n')
            if kind == 's' and raw is not None:
                raw = strings[int(raw)]
            elif kind == 'inlineStr':
                raw = ''.join(cell.find('s:is', NS).itertext())
            elif kind not in ('n', 's'):
                raise OpenDataSourceRefused('OpenData unsupported cell type')
            cells[ref] = (kind, raw)
        return cells


def parse_publication(payload):
    if type(payload) is not bytes or len(payload) != ARTIFACT_BYTES or sha256(payload).hexdigest() != SHA256:
        raise OpenDataSourceRefused('OpenData requires exact reviewed KNBS workbook bytes; changed editions need review')
    cells = _read_cells(payload)
    def value(ref):
        return cells.get(ref, ('n', None))[1]
    if value('A1') != 'Table 5.13: County Governments’ Revenue, 2015/16-2025/26' or value('A4') != 'COUNTY':
        raise OpenDataSourceRefused('OpenData table identity differs')
    labels = [value('A' + str(n)) for n in range(5, 53)]
    if labels != [*COUNTIES, 'Total']:
        raise OpenDataSourceRefused('OpenData county identity/order differs')
    columns = []
    for first, last, metric, heading in GROUPS:
        if value(column(first) + '3') != heading:
            raise OpenDataSourceRefused('OpenData column group differs')
        for n in range(first, last + 1):
            col = column(n)
            label = value(col + '4')
            if type(label) is not str or re.fullmatch(r'20[0-9]{2}/[0-9]{2}[+*]?', label) is None:
                raise OpenDataSourceRefused('OpenData fiscal period label differs')
            columns.append({'column': col, 'metric': metric, 'heading': heading, 'period_label': label,
                            'fiscal_year': label.rstrip('+*'), 'status': 'provisional' if label.endswith('*') else 'revised' if label.endswith('+') else 'unspecified',
                            'unit_attribution': 'bounded_knbs_sdmx_unconditional_context' if metric == 'unconditional_grant' else 'official_pdf_table_5_13',
                            'aggregation': 'published_total' if metric == 'total_revenue' else 'component'})
    rows = []
    numeric = missing = 0
    with localcontext() as context:
        context.prec = 40
        for n, label in enumerate(labels, 5):
            values = {}
            for spec in columns:
                ref = spec['column'] + str(n)
                kind, raw = cells.get(ref, ('n', None))
                if raw is None or raw == '-':
                    values[spec['column']] = {'raw': raw, 'amount_million_2dp': None, 'missing': 'blank' if raw is None else 'dash'}
                    missing += 1
                else:
                    if kind != 'n' or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:E[+-]?[0-9]{1,2})?', raw) or len(raw) > 30:
                        raise OpenDataSourceRefused('OpenData numeric grammar refused')
                    number = Decimal(raw)
                    if not number.is_finite() or number < 0 or number > 10000000:
                        raise OpenDataSourceRefused('OpenData numeric range refused')
                    values[spec['column']] = {'raw': raw, 'amount_million_2dp': format(number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f'), 'missing': None}
                    numeric += 1
            rows.append({'row': n, 'county_label': label, 'geography': 'published_county_aggregate' if n == 52 else 'county', 'cells': values})
        reconciliations = []
        for spec in columns:
            col = spec['column']
            amounts = [r['cells'][col]['amount_million_2dp'] for r in rows[:-1]]
            total = rows[-1]['cells'][col]['amount_million_2dp']
            complete = all(a is not None for a in amounts) and total is not None
            actual = sum((Decimal(a) for a in amounts), Decimal(0)) if complete else None
            reconciliations.append({'column': col, 'county_numeric_count': sum(a is not None for a in amounts),
                'published_total_million': total, 'county_sum_million': format(actual, '.2f') if complete else None,
                'sum_minus_published_million': format(actual - Decimal(total), '.2f') if complete else None,
                'status': 'incomplete' if not complete else 'matches_at_2dp' if actual == Decimal(total) else 'published_discrepancy'})
    if numeric != 2125 or missing != 83 or len(columns) != 46:
        raise OpenDataSourceRefused('OpenData reviewed coverage differs')
    return {'dataset': 'knbs_county_revenue_2026_table_5_13', 'extractor': EXTRACTOR,
            'artifact_sha256': SHA256, 'sheet': SHEET, 'table': '5.13', 'range': 'A1:AU57',
            'unit': 'KES million', 'precision_policy': 'raw OOXML retained; derived comparisons round each numeric cell to 2dp HALF_UP; never rebalance',
            'publication_stage': 'mixed_as_published', 'report_publication_month': '2026-04',
            'workbook_publication_date': None,
            'unit_attribution': {
                'official_pdf_table_5_13': {
                    'url': 'https://www.knbs.or.ke/wp-content/uploads/2026/04/2026-Economic-Survey.pdf',
                    'artifact_sha256': '8e26f32b6b7a43250b7c175f24193c00332a0c00244faf0ad050f64dfb14bafc',
                    'printed_pages': [111, 112], 'label': 'KSh Million',
                    'scope': 'Equitable Share, Conditional Grant, Own Source Revenue and Total Revenue; current two periods'},
                'bounded_knbs_sdmx_unconditional_context': {
                    'dataset': 'KE1,DF_PF_CG_REV,1.0', 'series': 'A.KE.G1311_KE001.....',
                    'url': 'https://ke.sdmx.afdb.org/ns-ws/rest/data/KE1,DF_PF_CG_REV,1.0/A.KE.G1311_KE001...../ALL/?detail=full&startPeriod=2024-01-01&endPeriod=2025-12-31&dimensionAtObservation=TIME_PERIOD',
                    'rendered_context_sha256': '6fe59b14808b8ce1ab48fcb14069812ae0d0bb58f30447e6e39cefbee3266559',
                    'unit_measure': 'KES', 'unit_mult': '6', 'ref_period_dtl': 'F07',
                    'observations': {'2024': '108.66', '2025': '7.43'},
                    'qualification': 'Context only, matched to X52/Y52; message declares Test=true; never a runtime ingestion input'}},
            'edition_notes': [{'columns': ['V', 'AI', 'AT'], 'period': '2024/25',
                'workbook_marker': None, 'pdf_marker': '+',
                'disposition': 'PDF marks revised; workbook is unmarked. Preserve both editions without assigning final/actual status.'}],
            'columns': columns, 'rows': rows, 'footnotes': {f'A{n}': value(f'A{n}') for n in range(53, 58)},
            'reconciliations': reconciliations, 'numeric_cells': numeric, 'missing_cells': missing,
            'verification_status': 'source_extracted_not_publication_qualified'}

"""Read the reviewed October 2026 IMF WEO workbook without running formulas."""

from hashlib import sha256
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

WORKBOOK_BYTES = 5_480_592
WORKBOOK_SHA256 = '2aa4f70a05931197b41ed7e0202dc56eee8d816858ac14521e4f8f5dbc38696c'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
UNITS = {
    'GGXWDG_NGDP': ('Units', 'Percent'),
    'GGXCNL_NGDP': ('Units', 'Percent'),
    'NGDPD': ('Billions', 'US dollar'),
    'NGDP_RPCH': ('Units', 'Percent'),
}


def parse_workbook(payload):
    if len(payload) != WORKBOOK_BYTES or sha256(payload).hexdigest() != WORKBOOK_SHA256:
        raise ValueError('IMF WEO workbook bytes differ from the reviewed release')

    result = {}
    years = {}
    with ZipFile(BytesIO(payload)) as archive:
        shared = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        # The reviewed archive binds the Countries sheet to sheet2.xml.
        with archive.open('xl/worksheets/sheet2.xml') as stream:
            for _, row in ET.iterparse(stream, events=('end',)):
                if row.tag != NS + 'row':
                    continue
                cells = {}
                for cell in row:
                    raw = cell.findtext(NS + 'v')
                    column = re.match(r'[A-Z]+', cell.get('r')).group()
                    kind = cell.get('t', 'n')
                    value = shared[int(raw)] if raw is not None and kind == 's' else raw
                    cells[column] = (kind, value, cell.find(NS + 'f') is not None)
                row.clear()

                def value(column):
                    return cells.get(column, (None, None, False))[1]

                if not years:
                    years = {col: int(raw) for col, (_, raw, _) in cells.items() if raw and raw.isdecimal()}
                    if list(years.values()) != list(range(1980, 2032)):
                        raise ValueError('IMF WEO workbook years differ')
                    continue
                indicator = value('E')
                if value('C') != 'KEN' or indicator not in UNITS:
                    continue
                if (indicator in result or value('A') != 'IMF.RES:WEO(9.0.0)'
                        or value('B') != f'KEN.{indicator}.A' or value('H') != 'Annual'
                        or (value('I'), value('J')) != UNITS[indicator]):
                    raise ValueError('IMF WEO workbook cohort identity differs')
                values = {}
                for column, year in years.items():
                    kind, raw, formula = cells.get(column, (None, None, False))
                    if raw is None:
                        continue
                    if kind != 'n' or formula:
                        raise ValueError('IMF WEO workbook observation is not a literal number')
                    values[str(year)] = raw
                first_year = next(iter(values), None)
                if first_year is None or list(values) != [
                    str(year) for year in range(int(first_year), max(years.values()) + 1)
                ]:
                    raise ValueError('IMF WEO workbook cohort coverage differs')
                result[indicator] = {'values': {indicator: {'KEN': values}}}
    if result.keys() != UNITS.keys():
        raise ValueError('IMF WEO workbook is missing a Kenya series')
    return result

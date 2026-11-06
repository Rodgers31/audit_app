"""Real offline PDF/OCR/JVM corpus; never grants publisher/source authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from common import Refusal, identity, publish, require, sha256
from native_environment import regular

RETAINED_SHA256 = 'd8c72b4fbda2c920f30f79b3e0554f9965165735d220a810e6ae3994e2dbf899'


def pdf(streams):
    """Small owned PDF with a shared Helvetica font and physical page order."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    pages = []
    for content in streams:
        page_id = len(objects) + 1
        pages.append(page_id)
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                       f'/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>'.encode())
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream')
    objects[1] = ('<< /Type /Pages /Kids [' + ' '.join(f'{p} 0 R' for p in pages)
                  + f'] /Count {len(pages)} >>').encode()
    result, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{number} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
                  f'startxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def run(output, retained, backend):
    output = Path(output).absolute()
    require(not output.exists() and '..' not in output.parts
            and all(not p.is_symlink() for p in (output, *output.parents)), 'fresh corpus output required')
    retained = regular(retained)
    require(sha256(retained) == RETAINED_SHA256, 'retained OAG corpus bytes differ')
    output.mkdir(mode=0o700)
    started = time.monotonic()
    os.environ['OMP_THREAD_LIMIT'] = '1'
    import pdfplumber
    import pypdfium2 as pdfium
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image, ImageDraw, ImageFont
    import tabula
    cases = []

    def command(argv, timeout=30):
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
        require(result.returncode == 0, 'native corpus command failed: ' + argv[0])
        return result.stdout.decode(errors='strict')

    text = output / 'owned-pages.pdf'
    text.write_bytes(pdf([b'BT /F1 18 Tf 60 700 Td (PAGE ONE 310327) Tj ET',
                          b'BT /F1 18 Tf 60 700 Td (PAGE TWO 987654) Tj ET']))
    with pdfplumber.open(text) as document:
        require(len(document.pages) == 2 and 'PAGE ONE 310327' in document.pages[0].extract_text(),
                'text PDF reader differs')
    extracted = command(['pdftotext', str(text), '-'])
    require('PAGE ONE 310327' in extracted and 'PAGE TWO 987654' in extracted,
            'Poppler text reader differs')
    cases.append({'id': 'text-pdf', 'input_sha256': sha256(text), 'text_sha256': identity(extracted)})
    page_one = command(['pdftotext', '-f', '1', '-l', '1', str(text), '-'])
    require('PAGE ONE 310327' in page_one and 'PAGE TWO' not in page_one,
            'physical page-one selection differs')
    require('Pages:' in command(['pdfinfo', str(text)]), 'PDF info probe missing')
    cases.append({'id': 'physical-page-one', 'text_sha256': identity(page_one)})

    lines = ['0.5 w']
    for x in (50, 180, 300, 450):
        lines.append(f'{x} 640 m {x} 700 l S')
    for y in (640, 670, 700):
        lines.append(f'50 {y} m 450 {y} l S')
    for row, y in zip((('County', 'Year', 'Population'), ('Samburu', '2019', '310327')), (680, 650)):
        for value, x in zip(row, (60, 190, 310)):
            lines.append(f'BT /F1 12 Tf {x} {y} Td ({value}) Tj ET')
    table = output / 'owned-table.pdf'
    table.write_bytes(pdf(['\n'.join(lines).encode()]))
    with pdfplumber.open(table) as document:
        rows = document.pages[0].extract_tables()
        require(rows == [[['County', 'Year', 'Population'], ['Samburu', '2019', '310327']]],
                'table cell fidelity differs')
    # Real JVM subprocess (the wheel's bundled jar is payload-locked).
    tables = tabula.read_pdf(str(table), pages=1, lattice=True, multiple_tables=True,
                             force_subprocess=True, java_options=['-Xmx256m'])
    require(len(tables) == 1 and list(tables[0].columns) == ['County', 'Year', 'Population']
            and tables[0].astype(str).values.tolist() == [['Samburu', '2019', '310327']],
            'JVM table reader differs')
    cases.append({'id': 'ruled-table-and-jvm', 'input_sha256': sha256(table), 'cells_sha256': identity(rows)})

    image = Image.new('RGB', (1600, 500), 'white')
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 48)
    ImageDraw.Draw(image).text((70, 150), 'AUDIT 2025 SAMBURU 310327', font=font, fill='black')
    scanned = output / 'owned-scan.pdf'
    image.save(scanned, 'PDF', resolution=150.0,
               creationDate='D:20261105000000Z', modDate='D:20261105000000Z')
    image.close()
    with pdfplumber.open(scanned) as document:
        require(not document.pages[0].extract_text(), 'scanned control unexpectedly contains text')
    pages = convert_from_path(scanned, dpi=150, first_page=1, last_page=1, thread_count=1, timeout=30)
    try:
        ocr = pytesseract.image_to_string(pages[0], lang='eng', config='--psm 6', timeout=30)
    finally:
        for page in pages:
            page.close()
    require('AUDIT 2025 SAMBURU 310327' in ocr, 'actual scan OCR lost source numbers')
    cases.append({'id': 'scanned-pdf-ocr', 'input_sha256': sha256(scanned), 'ocr_sha256': identity(ocr)})

    # Real retained publisher bytes: decorative page one is not promoted into a
    # publication title/day. Physical page three contains the legible title.
    title = command(['pdftotext', '-f', '3', '-l', '3', str(retained), '-'])
    require('NATIONAL GOVERNMENT' in title and '2024/2025' in title, 'retained cover title differs')
    with pdfium.PdfDocument(str(retained)) as document:
        require(len(document) == 915, 'retained physical page inventory differs')
        page = document[0]
        try:
            bitmap = page.render(scale=1.5)
            try:
                rendered = bitmap.to_pil()
                try:
                    decorative_ocr = pytesseract.image_to_string(rendered, lang='eng', timeout=30)
                finally:
                    rendered.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    cases.append({'id': 'retained-cover-and-decorative-page-one', 'input_sha256': RETAINED_SHA256,
                  'title_sha256': identity(title), 'page_one_ocr_sha256': identity(decorative_ocr),
                  'publication_authority': False})

    sys.path.insert(0, str(Path(backend).resolve()))
    from seeding.extractors import oag_blue_book as blue_book
    qualifications = []
    with pdfplumber.open(retained) as document:
        for index in (265, 690):
            page = document.pages[index]
            try:
                blue_book._page_text(page, qualifications=qualifications)
            finally:
                page.close()
    require(len(qualifications) == 4 and all(q['requires_human_review'] is True for q in qualifications),
            'clipped publisher title holds differ')
    cases.append({'id': 'retained-clipped-layout-holds', 'input_sha256': RETAINED_SHA256,
                  'qualifications_sha256': identity(qualifications), 'holds': 4,
                  'publication_authority': False, 'parser_sha256': sha256(blue_book.__file__)})
    require(sha256(retained) == RETAINED_SHA256 and len(cases) == 6, 'corpus drift/incomplete execution')
    result = {'schema': 'ingestion-real-native-corpus-v1', 'generated_by': str(Path(__file__).resolve()),
              'generator_sha256': sha256(__file__), 'generated_at': datetime.now(timezone.utc).isoformat(),
              'cases': cases, 'seconds': time.monotonic() - started,
              'publication_authority': False, 'verdict': 'LOCAL_REAL_NATIVE_CORPUS_PASSED'}
    publish(output / 'corpus.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retained', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(run(args.output, args.retained, args.backend), sort_keys=True))
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

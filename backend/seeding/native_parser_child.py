"""Apply process limits before decoding one PDF page or running OCR."""
from contextlib import closing
import math
import os
from pathlib import Path
import resource
import sys

MAX_PIXELS = 12_000_000
MAX_TEXT_BYTES = 1024 * 1024
SCALE = 200 / 72


def _limit(kind, requested):
    _, hard = resource.getrlimit(kind)
    limit = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (limit, limit))


def run(arguments):
    operation, path, *rest = arguments
    # Apply limits before loading the decoder or executing the native tool.
    # Keep one overflow byte so a short write cannot look like complete text.
    file_limit = 64 * 1024**2 if operation == "render" else MAX_TEXT_BYTES + 1
    _limit(resource.RLIMIT_FSIZE, file_limit)
    if sys.platform == "linux":
        _limit(resource.RLIMIT_AS, 1024**3)
    if operation == "tesseract":
        os.execv(path, [path, *rest])

    import pypdfium2 as pdfium

    with pdfium.PdfDocument(path) as document:
        if operation == "count" and not rest:
            print(len(document))
            return
        if operation != "render" or len(rest) != 1:
            raise ValueError("Expected a page-render or page-count request")
        page_number = int(rest[0])
        if not 1 <= page_number <= len(document):
            raise ValueError("PDF page does not exist")
        with closing(document[page_number - 1]) as page:
            width, height = page.get_size()
            if (not all(math.isfinite(value) and value > 0 for value in (width, height))
                    or math.ceil(width * SCALE) * math.ceil(height * SCALE) > MAX_PIXELS):
                raise ValueError("OCR raster exceeds the page pixel limit")
            with closing(page.render(scale=SCALE)) as bitmap:
                with bitmap.to_pil() as image:
                    image.save(Path("page.png"), format="PNG", dpi=(200, 200))


if __name__ == "__main__":
    run(sys.argv[1:])

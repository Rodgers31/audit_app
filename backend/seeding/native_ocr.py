"""Render and recognise one OAG page with explicit native process limits."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


NATIVE_TIMEOUT = 20
MAX_PIXELS = 12_000_000


def read_page(pdf_path: Path, page_number: int) -> str:
    import pytesseract
    from PIL import Image

    if type(page_number) is not int or page_number < 1:
        raise ValueError("OCR requires a positive physical page number")
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise FileNotFoundError("pdftoppm is unavailable")
    with tempfile.TemporaryDirectory(prefix="auditgava-ocr-") as directory:
        target = Path(directory) / "page"
        page = str(page_number)
        # pdf2image's conversion starts a separate pdfinfo call without the
        # caller's timeout. Invoke the one-page renderer directly.
        subprocess.run(
            [renderer, "-r", "200", "-f", page, "-l", page, "-singlefile",
             str(pdf_path.absolute()), str(target)],
            env={"PATH": os.defpath, "LC_ALL": "C", "HOME": directory, "TMPDIR": directory},
            timeout=NATIVE_TIMEOUT, check=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with Image.open(target.with_suffix(".ppm"), formats=["PPM"]) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("OCR raster exceeds the page pixel limit")
            return pytesseract.image_to_string(image, lang="eng", timeout=NATIVE_TIMEOUT)

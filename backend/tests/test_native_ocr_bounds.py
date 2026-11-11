"""Executable controls for the native OAG page renderer."""
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from seeding import native_ocr


def renderer(tmp_path, monkeypatch, program):
    executable = tmp_path / "pdftoppm"
    executable.write_text(f"#!{sys.executable}\n{program}\n")
    executable.chmod(0o700)
    monkeypatch.setattr(native_ocr.shutil, "which", lambda name: str(executable))
    return executable


def test_ocr_renderer_gets_a_single_page_and_no_database_credentials(tmp_path, monkeypatch):
    renderer(tmp_path, monkeypatch, """
import os, sys
from pathlib import Path
assert 'DATABASE_URL' not in os.environ
assert sys.argv[sys.argv.index('-f') + 1] == sys.argv[sys.argv.index('-l') + 1] == '3'
Path(sys.argv[-1] + '.ppm').write_bytes(b'P6\\n2 1\\n255\\n' + b'\\xff' * 6)
""")
    monkeypatch.setenv("DATABASE_URL", "disposable-ocr-boundary-test")
    seen = []

    def recognize(image, *, lang, timeout):
        seen.append((image.size, lang, timeout, Path(image.filename).parent))
        return "Audit evidence"

    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(image_to_string=recognize))
    assert native_ocr.read_page(tmp_path / "fixture.pdf", 3) == "Audit evidence"
    (size, lang, timeout, directory), = seen
    assert (size, lang, timeout) == ((2, 1), "eng", 20)
    assert not directory.exists()


def test_stalled_renderer_cannot_reach_recognition(tmp_path, monkeypatch):
    renderer(tmp_path, monkeypatch, "import time; time.sleep(5)")
    monkeypatch.setattr(native_ocr, "NATIVE_TIMEOUT", 0.2)

    def unexpected(*args, **kwargs):
        pytest.fail("Timed-out renderer reached Tesseract")

    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(image_to_string=unexpected))
    with pytest.raises(subprocess.TimeoutExpired):
        native_ocr.read_page(tmp_path / "fixture.pdf", 1)

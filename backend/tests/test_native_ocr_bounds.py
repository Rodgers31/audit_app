"""Executable controls for the native PDF and OCR subprocesses."""
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from seeding import native_ocr


def executable(path, program):
    path.write_text(f"#!{sys.executable}\n{program}\n")
    path.chmod(0o700)
    return path


def test_ocr_reads_requested_page_and_clears_writer_environment(tmp_path, monkeypatch):
    path = tmp_path / "fixture.pdf"
    with Image.new("RGB", (72, 72), "white") as first, Image.new("RGB", (72, 72)) as second:
        first.save(path, save_all=True, append_images=[second])

    tesseract = executable(tmp_path / "tesseract", """
import os, sys
from pathlib import Path
from PIL import Image
assert set(os.environ) <= {'HOME', 'TMPDIR', 'PATH', 'LC_ALL', 'OMP_THREAD_LIMIT',
                           '__CF_USER_TEXT_ENCODING'}
assert Path.cwd() == Path(os.environ['HOME']).resolve()
if sys.argv[1:] == ['--version']:
    print('tesseract 5.5.4\\n Found AVX2')
elif sys.argv[1:] == ['--list-langs']:
    print('List of languages:\\neng\\nosd')
else:
    path = Path(sys.argv[1])
    assert path.parent.resolve() == Path.cwd()
    assert sys.argv[2:5] == ['stdout', '-l', 'eng']
    if path.name == 'annex.png':
        assert sys.argv[5:] == ['--psm', '6', '-c', 'preserve_interword_spaces=1', 'txt']
    else:
        assert path.name == 'page.png' and sys.argv[5:] == ['txt']
        with Image.open(path) as image:
            assert image.size == (200, 200)
            assert image.convert('L').getpixel((100, 100)) == 0
    print('Audit evidence')
""")
    monkeypatch.setattr(native_ocr.shutil, "which", lambda name: str(tesseract))
    for name in ("DATABASE_URL", "RECEIPT_SUPABASE_SECRET_KEY", "RECEIPT_R2_CONTROL_TOKEN",
                 "TESSDATA_PREFIX", "FONTCONFIG_FILE"):
        monkeypatch.setenv(name, "owned-test-marker")
    assert native_ocr.page_count(path) == 2
    assert native_ocr.read_page(path, 2) == "Audit evidence\n"
    assert native_ocr.engine_identity() == ("5.5.4", ["eng", "osd"])
    with Image.new("L", (120, 160)) as annex:
        assert native_ocr.recognize_annex(annex) == "Audit evidence\n"


def test_stalled_renderer_cannot_reach_recognition(tmp_path, monkeypatch):
    monkeypatch.setattr(native_ocr, "_child", lambda *args: [
        sys.executable, "-c", "import time; time.sleep(5)",
    ])
    monkeypatch.setattr(native_ocr, "NATIVE_TIMEOUT", 0.2)

    def unexpected(*args):
        pytest.fail("Timed-out renderer reached Tesseract")

    monkeypatch.setattr(native_ocr.shutil, "which", unexpected)
    with pytest.raises(subprocess.TimeoutExpired):
        native_ocr.read_page(tmp_path / "fixture.pdf", 1)


@pytest.mark.parametrize("report", ["0", "2\n3", "No pages"])
def test_page_count_refuses_ambiguous_output(tmp_path, monkeypatch, report):
    monkeypatch.setattr(native_ocr, "_child", lambda *args: [
        sys.executable, "-c", f"print({report!r})",
    ])
    with pytest.raises(ValueError, match="positive PDF page count"):
        native_ocr.page_count(tmp_path / "fixture.pdf")


def test_large_raster_refuses_before_tesseract(tmp_path, monkeypatch):
    path = tmp_path / "large.pdf"
    with Image.new("L", (1200, 1200)) as page:
        page.save(path, resolution=36)

    def unexpected(*args):
        pytest.fail("Oversized raster reached Tesseract")

    monkeypatch.setattr(native_ocr.shutil, "which", unexpected)
    with pytest.raises(subprocess.CalledProcessError):
        native_ocr.read_page(path, 1)


def test_output_file_limit_applies_before_recognition_returns(tmp_path, monkeypatch):
    tesseract = executable(tmp_path / "tesseract", """
import os, resource
assert resource.getrlimit(resource.RLIMIT_FSIZE) == (1048577, 1048577)
assert os.write(1, b'x' * 2097152) == 1048577
""")
    monkeypatch.setattr(native_ocr.shutil, "which", lambda name: str(tesseract))
    with Image.new("L", (120, 160)) as annex, pytest.raises(ValueError, match="output exceeds"):
        native_ocr.recognize_annex(annex)


def test_timeout_terminates_renderer_process_group(tmp_path, monkeypatch):
    import time

    marker = tmp_path / "renderer-descendant-ran"
    started = tmp_path / "renderer-started"
    descendant = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).touch()"
    program = f"""
import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, '-c', {descendant!r}])
Path({str(started)!r}).touch()
time.sleep(5)
"""
    monkeypatch.setattr(native_ocr, "_child", lambda *args: [sys.executable, "-c", program])
    monkeypatch.setattr(native_ocr, "NATIVE_TIMEOUT", 0.5)
    with pytest.raises(subprocess.TimeoutExpired):
        native_ocr.read_page(tmp_path / "fixture.pdf", 1)
    assert started.exists()
    time.sleep(0.7)
    assert not marker.exists()

"""Run PDF metadata, rasterization and OCR with a fixed child environment."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from .isolated_parser import isolated

from .native_parser_child import MAX_PIXELS, MAX_TEXT_BYTES


NATIVE_TIMEOUT = 20


def _tesseract(*arguments):
    executable = shutil.which("tesseract")
    if executable is None:
        raise FileNotFoundError("tesseract is unavailable")
    return _child("tesseract", os.path.abspath(executable), *arguments)


def _child(*arguments):
    return [sys.executable, "-I", "-B", str(Path(__file__).with_name("native_parser_child.py").resolve()), *arguments]


def _run(command, directory, *, stdout=subprocess.DEVNULL):
    with subprocess.Popen(
        command, cwd=directory, close_fds=True, start_new_session=True,
        env={"PATH": os.defpath, "LC_ALL": "C", "HOME": directory,
             "TMPDIR": directory, "OMP_THREAD_LIMIT": "1"},
        stdin=subprocess.DEVNULL, stdout=stdout, stderr=subprocess.DEVNULL,
    ) as process:
        try:
            code = process.wait(timeout=NATIVE_TIMEOUT)
            if code:
                raise subprocess.CalledProcessError(code, command)
        finally:
            # Reap the process group, including descendants of a stalled
            # command.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _text(command, directory):
    with tempfile.TemporaryFile(dir=directory) as output:
        _run(command, directory, stdout=output)
        output.seek(0)
        raw = output.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("Native parser output exceeds its byte limit")
    return raw.decode("utf-8")


@isolated("pdf_path", timeout=45)
def page_count(pdf_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="auditgava-pdf-count-") as directory:
        output = _text(_child("count", str(pdf_path.absolute())), directory)
    if re.fullmatch(r"[1-9][0-9]{0,5}\n", output) is None:
        raise ValueError("One positive PDF page count required")
    return int(output)


def engine_identity():
    with tempfile.TemporaryDirectory(prefix="auditgava-ocr-identity-") as directory:
        version = _text(_tesseract("--version"), directory)
        languages = _text(_tesseract("--list-langs"), directory)
    # The engine prints CPU feature lines. They vary across hosted runners
    # and should not invalidate a cache keyed to the installed engine release.
    match = re.match(r"^tesseract[ 	]+(\S+)", version)
    if match is None:
        raise ValueError("Tesseract release could not be identified")
    return match[1], languages.splitlines()[1:]


def recognize_annex(image) -> str:
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("OCR raster exceeds the page pixel limit")
    with tempfile.TemporaryDirectory(prefix="auditgava-annex-ocr-") as directory:
        path = Path(directory) / "annex.png"
        image.save(path, format="PNG")
        return _text(_tesseract(str(path), "stdout", "-l", "eng", "--psm", "6",
                                "-c", "preserve_interword_spaces=1", "txt"), directory)


@isolated("pdf_path", timeout=90)
def read_page(pdf_path: Path, page_number: int) -> str:
    if type(page_number) is not int or page_number < 1:
        raise ValueError("OCR requires a positive physical page number")
    with tempfile.TemporaryDirectory(prefix="auditgava-ocr-") as directory:
        _run(_child("render", str(pdf_path.absolute()), str(page_number)), directory)
        raster = Path(directory) / "page.png"
        return _text(_tesseract(str(raster), "stdout", "-l", "eng", "txt"), directory)

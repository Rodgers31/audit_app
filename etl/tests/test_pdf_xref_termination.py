"""A bounded real-library regression for the truncated-xref trailer loop."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("optimized", [False, True])
def test_truncated_xref_rejects_instead_of_looping(optimized):
    # Minimal owned byte input for GHSA-5849-834g-hvw5, without external PDFs.
    program = r'''
from io import BytesIO
from pypdf import PdfReader
from pypdf.errors import PdfReadError
data = b"%PDF-1.4\nstartxref\n28\n%%EOF\nxref\n1 0\naaa"
try:
    PdfReader(BytesIO(data))
except PdfReadError as error:
    if "Xref parsing stuck" not in str(error):
        raise RuntimeError("unexpected PDF rejection") from error
else:
    raise RuntimeError("truncated xref was accepted")
print("truncated-xref-refused")
'''
    result = subprocess.run(
        [sys.executable, "-I", *(["-O"] if optimized else []), "-c", program],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    assert result.stdout.strip() == "truncated-xref-refused"

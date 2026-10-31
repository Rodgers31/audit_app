"""Execute Docker RUN shell control flow with owned offline command ports.

APT and binaries are replaced with controlled executables. This tests failure
propagation and cleanup, not an actual image build or package installation.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess

import pytest


@pytest.mark.parametrize('name', ['Dockerfile', 'Dockerfile.prod'])
@pytest.mark.parametrize('mode,success', [
    ('good', True), ('apt_update_failure', False), ('apt_install_failure', False),
    ('ffprobe_failure', False), ('tesseract_missing', False), ('no_english', False),
    ('similar_not_english', False), ('tesseract_failed_after_english', False),
])
def test_runtime_ocr_capability_guard_preserves_tool_failures(tmp_path, name, mode, success):
    source = (Path(__file__).resolve().parents[1] / name).read_text()
    blocks = [b for b in re.findall(r'^RUN (.*?)(?=\n\n)', source, re.M | re.S)
              if 'ffmpeg' in b]
    assert len(blocks) == 1
    block = blocks[0]

    def executable(name, body):
        path = tmp_path / name
        path.write_text('#!/bin/sh\nset -eu\n' + body)
        path.chmod(0o700)
        return shlex.quote(str(path))

    apt = executable('apt', '''printf 'apt %s\\n' "$*" >> "$CALL_LOG"
if [ "$MODE" = "apt_update_failure" ] && [ "$1" = "update" ]; then exit 2; fi
if [ "$MODE" = "apt_install_failure" ] && [ "$1" = "install" ]; then exit 3; fi
if [ "$1" = "install" ]; then
    printf '%s\\n' "$@" | grep -qx tesseract-ocr
    printf '%s\\n' "$@" | grep -qx tesseract-ocr-eng
fi
''')
    probe = executable('probe', '''printf 'ffprobe\\n' >> "$CALL_LOG"
[ "$MODE" != "ffprobe_failure" ]
''')
    ocr = executable('ocr', '''printf 'tesseract\\n' >> "$CALL_LOG"
if [ "$MODE" = "tesseract_missing" ]; then exit 127; fi
if [ "$MODE" = "no_english" ]; then printf 'fra\\n'; exit 0; fi
if [ "$MODE" = "similar_not_english" ]; then printf 'eng-old\\n'; exit 0; fi
printf 'eng\\nosd\\n'
if [ "$MODE" = "tesseract_failed_after_english" ]; then exit 42; fi
''')
    cleanup = executable('cleanup', 'printf "cleanup\\n" >> "$CALL_LOG"\n')
    for actual, controlled in [('apt-get', apt), ('/usr/bin/ffprobe', probe),
                               ('/usr/bin/tesseract', ocr),
                               ('rm -rf /var/lib/apt/lists/*', cleanup)]:
        assert actual in block, f'required command port absent: {actual}'
        block = block.replace(actual, controlled)
    log = tmp_path / 'calls'
    result = subprocess.run(['/bin/sh', '-c', block], capture_output=True, text=True,
                            env={**os.environ, 'MODE': mode, 'CALL_LOG': str(log)}, timeout=5)
    calls = log.read_text()
    assert (result.returncode == 0) == success, (result.returncode, calls, result.stderr)
    assert ('cleanup\n' in calls) == success
    if mode == 'apt_update_failure':
        assert 'apt install' not in calls
    if mode in ('apt_update_failure', 'apt_install_failure'):
        assert 'ffprobe' not in calls and 'tesseract\n' not in calls

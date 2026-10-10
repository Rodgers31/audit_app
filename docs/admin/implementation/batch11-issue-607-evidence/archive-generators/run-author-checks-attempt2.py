"""Capture explicit frontend gates in the lane's owned Linux runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

out = Path(__file__).resolve().parent / 'author-checks-attempt2'
out.mkdir()
checks = [
    ('lint', ['npm', 'run', 'lint']),
    ('typescript', ['node', 'node_modules/typescript/bin/tsc', '--noEmit']),
    ('jest', ['node', 'node_modules/jest/bin/jest.js', '--runInBand', '--json', '--outputFile=/evidence/author-checks-attempt2/jest-report.json']),
    ('native', ['npm', 'run', 'verify:native']),
]
rows = []
for name, tail in checks:
    command = ['docker', 'exec', 'batch11-navigation-linux', 'env', '-i',
               'PATH=/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin',
               'HOME=/evidence/home', 'CI=true',
               'NEXT_PUBLIC_API_URL=http://127.0.0.1:8141',
               'NATIVE_VERIFY_CACHE_DIR=/evidence/native-cache', *tail]
    print('START ' + name, flush=True)
    with (out / (name + '.log')).open('x') as log:
        child = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    row = {'name': name, 'command': command, 'child_exit': child.returncode,
           'log_sha256': hashlib.sha256((out / (name + '.log')).read_bytes()).hexdigest()}
    rows.append(row)
    with (out / (name + '-receipt.json')).open('x') as f:
        json.dump(row, f, indent=2)
    print('END ' + name + ' ' + str(child.returncode), flush=True)
passed = len(rows) == 4 and all(r['child_exit'] == 0 for r in rows)
with (out / 'summary.json').open('x') as f:
    json.dump({'passed': passed, 'checks': rows, 'scope': 'local Linux AMD64; no hosted or production acceptance'}, f, indent=2)
sys.exit(0 if passed else 1)

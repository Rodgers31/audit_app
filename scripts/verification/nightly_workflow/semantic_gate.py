"""Offline Actions schema/context gate using a supplied verified actionlint.

No downloader, hosted dispatch, dependency install or workflow enablement.
Shellcheck/pyflakes are deliberately outside this semantic gate's scope.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

VERSION = '1.7.12'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflows(root):
    directory = root / '.github/workflows'
    if (root.joinpath('.github').is_symlink() or directory.is_symlink()
            or not directory.is_dir() or not directory.resolve().is_relative_to(root)):
        raise ValueError('Workflow directory missing or linked')
    files = sorted(p for p in directory.iterdir() if p.suffix in ('.yml', '.yaml'))
    if not files or any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Workflow inventory missing, linked or irregular')
    return files


def run(root, binary, expected_sha256, receipt=None):
    """Return the semantic verdict. Direct callers receive the same guards."""
    generator_path = Path(__file__).resolve(strict=True)
    generator_before = digest(generator_path)
    if not isinstance(root, Path):
        raise ValueError('Explicit source root required')
    root = root.resolve(strict=True)
    if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Explicit reviewed actionlint binary SHA256 required')
    binary = Path(binary)
    if binary.is_symlink() or not binary.is_file() or digest(binary) != expected_sha256:
        raise ValueError('actionlint binary identity refused')
    binary = binary.resolve(strict=True)
    files = workflows(root)
    before = {str(p.relative_to(root)): digest(p) for p in files}
    if receipt is not None:
        receipt = Path(receipt)
        if (receipt.exists() or receipt.is_symlink() or receipt.parent.resolve().is_relative_to(root)
                or receipt.resolve() in (binary, Path(__file__).resolve())):
            raise ValueError('Receipt must be fresh and external to source/tool')
    version = subprocess.run([str(binary), '-version'], capture_output=True, text=True, timeout=10)
    if version.returncode != 0 or version.stdout.splitlines()[0:1] != [VERSION]:
        raise ValueError('actionlint version refused')
    argv = [str(binary), '-no-color', '-shellcheck=', '-pyflakes=', *map(str, files)]
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=60)
    after = {name: digest(root/name) if (root/name).is_file() else None for name in before}
    generator_after = digest(generator_path)
    stable = (before == after and files == workflows(root) and digest(binary) == expected_sha256
              and generator_before == generator_after)
    verdict = ('UNINTERPRETABLE' if result.returncode not in (0, 1) else
               'PASSED' if result.returncode == 0 and stable else 'FAILED')
    record = {'generated_by': str(generator_path), 'generator_sha256': generator_before,
        'generator_sha256_after': generator_after,
        'generated_at': datetime.now(timezone.utc).isoformat(), 'target_root': str(root),
        'target_files': before, 'target_files_after': after, 'binary_sha256': expected_sha256,
        'actionlint_version': VERSION, 'argv': argv, 'child_exit': result.returncode,
        'scope': 'offline Actions schema/context validation; not hosted compiler or execution acceptance',
        'verdict': verdict, 'stdout': result.stdout, 'stderr': result.stderr}
    if receipt is not None:
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
        check = json.loads(receipt.read_text())
        if (type(check) is not dict or type(check.get('child_exit')) is not int
                or type(check.get('verdict')) is not str or type(check.get('target_files')) is not dict
                or type(check.get('generator_sha256')) is not str or check != record):
            raise ValueError('Semantic receipt disk readback refused')
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    print(f'Actions semantic gate: {verdict}; workflows={len(files)}')
    return 0 if verdict == 'PASSED' else 1 if result.returncode in (0, 1) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--actionlint', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    try:
        return run(args.root, args.actionlint, args.sha256, args.receipt)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('Actions semantic gate refused: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

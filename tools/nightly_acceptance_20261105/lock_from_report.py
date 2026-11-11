"""Seal pip's official-index resolution only after checking every downloaded wheel."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib.parse import urlparse, unquote

sys.dont_write_bytecode = True
from common import fields, identity, publish, read_json, require, sha256
from runtime import ROOT, MANIFESTS, normalized, wheels_verified


def seal(report_path, wheelhouse, lock_path, receipt_path):
    report = read_json(report_path)
    require(report['version'] == '1', 'unknown pip report')
    packages = []
    for row in report['install']:
        download = row['download_info']
        url = download['url']
        require(urlparse(url).hostname == 'files.pythonhosted.org', 'nonofficial resolution')
        packages.append({'name': normalized(row['metadata']['name']), 'version': row['metadata']['version'],
                         'filename': Path(unquote(urlparse(url).path)).name,
                         'sha256': download['archive_info']['hashes']['sha256'], 'url': url})
    require(packages and len({r['name'] for r in packages}) == len(packages), 'empty/duplicate resolution')
    lock = {'schema': 'ingestion-runtime-v1', 'python': '3.12.16', 'system': 'Linux', 'machine': 'x86_64',
            'manifests': {name: sha256(ROOT / name) for name in MANIFESTS},
            'packages': sorted(packages, key=lambda r: r['name'])}
    wheels_verified(lock, wheelhouse)
    publish(lock_path, lock)
    publish(receipt_path, {'generated_by': str(Path(__file__).resolve()),
                          'generator_sha256': sha256(__file__), 'target_commit': __import__('subprocess').check_output(
                              ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                          'generated_at': datetime.now(timezone.utc).isoformat(),
                          'report_sha256': sha256(report_path), 'lock_sha256': sha256(lock_path),
                          'wheel_count': len(packages), 'wheel_bytes': sum(
                              (Path(wheelhouse) / r['filename']).stat().st_size for r in packages),
                          'verdict': 'ARTIFACTS_VERIFIED_RUNTIME_QUALIFICATION_PENDING'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'wheelhouse', 'lock', 'receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    seal(args.report, args.wheelhouse, args.lock, args.receipt)

"""Append the final #610 census refinement; preserve prior publications."""
import argparse
import hashlib
import json
from pathlib import Path
import time

PACKET = Path(__file__).resolve().parent
HISTORY = PACKET / 'history/coordinator-610'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def write_new(path, body):
    with path.open('xb') as stream:
        stream.write(body)
    if path.read_bytes() != body:
        raise RuntimeError('Publication readback mismatch')


def prepare():
    manifest = json.loads((PACKET / 'manifest.json').read_text())
    if manifest['generated_by'] != 'publish_coordinator_610.py' or manifest['schema'] != 2:
        raise RuntimeError('Expected first schema2 publication')
    for name in ('manifest.json', 'verify_package.py', 'README.md'):
        write_new(HISTORY / ('schema2-initial-' + name), (PACKET / name).read_bytes())
    record = {'generated_by': Path(__file__).name, 'generator_sha256': sha(Path(__file__)),
              'generated_at': time.time(), 'status': 'HISTORICAL_SUPERSEDED_VALIDATOR',
              'previous_manifest_sha256': sha(PACKET / 'manifest.json'),
              'reason': 'Tighten complete asset census to exempt only the canonical root manifest; original execution identity and retained archive stay unchanged.'}
    write_new(HISTORY / 'schema2-initial-preservation.json', encode(record))
    print(json.dumps({'stage': 'prepare', 'previous_manifest_sha256': record['previous_manifest_sha256']}))


def publish():
    previous = HISTORY / 'schema2-initial-manifest.json'
    if (PACKET / 'manifest.json').read_bytes() != previous.read_bytes():
        raise RuntimeError('Publication changed after prepare')
    manifest = json.loads(previous.read_text())
    replacements = {name: 'history/coordinator-610/schema2-initial-' + name for name in ('README.md', 'verify_package.py')}
    for name, expected in manifest['assets_sha256'].items():
        if sha(PACKET / replacements.get(name, name)) != expected:
            raise RuntimeError('Intermediate asset changed: ' + name)
    record = {'generated_by': Path(__file__).name, 'generator_sha256': sha(Path(__file__)),
              'generated_at': time.time(), 'issue': 610,
              'previous_manifest_sha256': manifest['previous_publication_sha256'],
              'intermediate_manifest_sha256': sha(previous),
              'intermediate_publication_status': 'HISTORICAL_SUPERSEDED_VALIDATOR',
              'original_execution_status': 'HISTORICAL_EXECUTION_PACKET',
              'current_checkout_acceptance': False,
              'reason': 'Complete asset-census refinement; two actual normal/-O nested-manifest rejection controls ran red. Earlier publications and all original runs remain unchanged.'}
    write_new(HISTORY / 'publication-v2.json', encode(record))
    manifest.update({'generated_by': Path(__file__).name, 'generator_sha256': sha(Path(__file__)),
                     'generated_at': time.time(), 'publication_history': 'history/coordinator-610/publication-v2.json',
                     'intermediate_publication': 'history/coordinator-610/schema2-initial-manifest.json',
                     'intermediate_publication_sha256': sha(previous),
                     'intermediate_publication_status': 'HISTORICAL_SUPERSEDED_VALIDATOR'})
    manifest['assets_sha256'] = {str(path.relative_to(PACKET)): sha(path) for path in sorted(PACKET.rglob('*'))
                                 if path.is_file() and path != PACKET / 'manifest.json'}
    body = encode(manifest)
    (PACKET / 'manifest.json').write_bytes(body)
    if (PACKET / 'manifest.json').read_bytes() != body:
        raise RuntimeError('Current publication readback mismatch')
    print(json.dumps({'stage': 'publish', 'assets': len(manifest['assets_sha256'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'publish'))
    args = parser.parse_args()
    {'prepare': prepare, 'publish': publish}[args.stage]()

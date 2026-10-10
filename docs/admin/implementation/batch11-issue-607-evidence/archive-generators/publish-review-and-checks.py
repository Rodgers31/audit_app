"""Append exact producer artifacts; never overwrite previously published bytes."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--artifacts', type=Path, required=True)
p.add_argument('--packet', type=Path, required=True)
p.add_argument('--receipt', type=Path, required=True)
p.add_argument('--adversarial-list', default='COMMIT_ARTIFACTS_V1.json')
a = p.parse_args()
rows = []

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def copy(source, relative, expected=None):
    assert source.is_file() and not any(x.is_symlink() for x in [source, *source.parents])
    raw = source.read_bytes()
    if expected:
        assert digest(raw) == expected
    target = a.packet / relative
    if target.exists():
        assert target.read_bytes() == raw, 'Previously published producer changed: ' + relative
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write(raw)
    assert target.read_bytes() == raw and source.read_bytes() == raw
    rows.append({'input': source.relative_to(a.artifacts).as_posix(), 'output': relative,
                 'sha256': digest(raw), 'bytes': len(raw)})

for group in ['author-checks', 'review-spec', 'review-standards']:
    for source in sorted((a.artifacts / group).rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts and not source.is_symlink():
            relative = ('checks/' if group == 'author-checks' else 'reviews/') + source.relative_to(a.artifacts).as_posix()
            copy(source, relative)
review = a.artifacts / 'review-adversarial'
listing = review / a.adversarial_list
for row in json.loads(listing.read_text())['finite_artifacts']:
    copy(review / row['path'], 'reviews/review-adversarial/' + row['path'], row['sha256'])
copy(listing, 'reviews/review-adversarial/' + listing.name)
data = {'generator_sha256': digest(Path(__file__).read_bytes()), 'copies': rows}
with a.receipt.open('x') as f:
    json.dump(data, f, indent=2)
assert json.loads(a.receipt.read_text()) == data
print(json.dumps({'copied': len(rows), 'receipt': str(a.receipt)}))

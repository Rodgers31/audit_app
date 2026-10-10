"""Seal a fresh catalogue; all prior run identities remain archival records."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--packet', type=Path, required=True)
p.add_argument('--name', required=True)
p.add_argument('--previous', type=Path)
a = p.parse_args()
root = a.packet

def load(name):
    return json.loads(gzip.decompress((root / name).read_bytes()))

def specs(report):
    out = []
    def visit(s):
        out.extend(s['specs'])
        for c in s.get('suites', []):
            visit(c)
    for s in report['suites']:
        visit(s)
    return out

runs = []
def add(name, category, report, receipt, cohort_receipt=None):
    filename = 'archives/' + report + '-report.json.gz'
    r = load(filename)
    row = {'name': name, 'category': category, 'report': filename,
           'receipt': 'archives/' + receipt + '.json.gz',
           'counts': {k: r['stats'][k] for k in ['expected', 'unexpected', 'skipped', 'flaky']},
           'case_ids': [s['id'] for s in specs(r)]}
    if cohort_receipt:
        row['cohort_receipt'] = 'archives/' + cohort_receipt + '-receipt.json.gz'
    runs.append(row)

for name, category, report, receipt in [
    ('baseline-original-100', 'diagnostic-positive', 'baseline-original-100', 'baseline-original-100'),
    ('gated-original-40', 'diagnostic-positive', 'gated-original-40-attempt2', 'gated-original-40-attempt2'),
    ('pending-original-red', 'historical-red', 'pending-original-red', 'pending-original-red'),
    ('boundary-red', 'historical-red', 'boundary-red-attempt2', 'boundary-red-attempt2'),
    ('contracts-corrected-red', 'historical-red', 'contracts-corrected-before-fix', 'contracts-corrected-before-fix'),
    ('budget-launch-control', 'diagnostic-positive', 'budget-selector-launch-control', 'budget-selector-launch-control'),
    ('unrelated-budget-cohort-failure', 'historical-red', 'full-current/public', 'full-current-capture'),
    ('prior-focused-green', 'diagnostic-positive', 'focused-green', 'focused-green'),
    ('prior-pending-original-green', 'diagnostic-positive', 'pending-original-green', 'pending-original-green'),
    ('focused-green', 'current-acceptance', 'focused-green-rechecked', 'focused-green-rechecked'),
    ('pending-original-green', 'current-acceptance', 'pending-original-green-rechecked', 'pending-original-green-rechecked'),
]:
    add(name, category, report, receipt)

for cohort in ['public', 'users', 'operations', 'overview-audit', 'etl-ui', 'coordinator']:
    add('prior-complete-' + cohort, 'diagnostic-positive',
        'full-current-attempt2/' + cohort, 'full-current-attempt2-capture',
        'full-current-attempt2/' + cohort)
    add('full-' + cohort, 'current-acceptance',
        'full-current-attempt3/' + cohort, 'full-current-attempt3-capture',
        'full-current-attempt3/' + cohort)

if a.previous:
    assert json.loads(a.previous.read_text())['runs'] == runs, 'Behavioral inventory changed during reseal'
files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in root.rglob('*') if p.is_file()}
data = {'schema': 1,
        'scope': 'Recorded local Linux AMD64 under Docker Desktop emulation; no hosted/production acceptance',
        'launch_commit': 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20',
        'launch_tree': '9d0061928c16d173859f98cb6daa5f2f591b257c',
        'product_commit': '982a961a58ed3647ead6bc7900250efa7d882a94',
        'product_tree': '5ebb363b208efd159d4b4673a760f111cdd1d629',
        'implementation_commit': '09fd3c150032e8595678ddf2046948651a260b96',
        'source_identity_note': 'Earlier author browser runs measured pinned HEAD plus exact staged/working implementation bytes. After four old router-transport unit assertions failed,982a961 updated the observer without changing product code. Current author gates/controls/full cohorts measured982a961. Evidence commits add docs only; final remote identity is in external postcommit binder.',
        'current_source_receipt': 'archives/full-current-attempt3-capture.json.gz',
        'current_inventory': 'archives/current-inventory.json.gz',
        'runs': runs, 'files': files,
        'limitations': ['#601 native-auto Y100 cause unmeasured',
                        '#607 historical naturally delivered200 lost retry not established',
                        'First full public attempt failed independent budget selector; preserved and tracked separately',
                        'First full Jest found four obsolete router-transport assertions; raw failed report and native-observer correction retained',
                        'Early recorder external helper inventory incomplete; separate generated-source manifests retained',
                        'Synthetic helper attacks certify guard behavior only; no browser/provider/DB acceptance']}
with (root / a.name).open('x') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
assert json.loads((root / a.name).read_text()) == data
print(json.dumps({'manifest': a.name, 'files': len(files), 'runs': len(runs),
                  'manifest_sha256': hashlib.sha256((root / a.name).read_bytes()).hexdigest()}))

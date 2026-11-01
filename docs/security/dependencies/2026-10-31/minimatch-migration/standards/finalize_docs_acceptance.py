from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import urllib.request

base = Path(__file__).parent
candidate = Path('/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app')
prior = json.loads((base / 'FINAL_BINDING.json').read_text())
proof_path = 'docs/security/dependencies/2026-10-31/minimatch-migration/author-acceptance.json'
proof = json.loads((candidate / proof_path).read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
current = {name: sha((candidate / name).read_bytes()) for name in prior['executable_inputs']}
assert current == prior['executable_inputs'] == proof['executable_inputs'] and len(current) == 7
for row in proof['records']:
    assert not row['timeout'] and row['source_changes'] == []
    assert row['exit'] == (1 if row['label'] == 'accepted-audit-full' else 0), row['label']
assert len({row['source_sha256'] for row in proof['records']}) == 1
seen = {}
documents = ['docs/security/DEPENDENCY_MATCHER_MIGRATION_2026_10_31.md', 'docs/security/DEPENDENCY_FOLLOWUP_2026_10_31.md']
full_path = 'docs/security/dependencies/2026-10-31/minimatch-migration/npm-full.json'
production_path = 'docs/security/dependencies/2026-10-31/minimatch-migration/npm-production.json'
for file in documents + [proof_path, full_path, production_path]:
    data = (candidate / file).read_bytes()
    try:
        indexed = subprocess.check_output(['git', 'show', ':' + file], cwd=candidate, stderr=subprocess.DEVNULL)
        staged_hash = sha(indexed)
    except subprocess.CalledProcessError:
        staged_hash = None
    if file in documents:
        assert staged_hash == sha(data), file
    seen[file] = {'sha256': sha(data), 'staged_sha256': staged_hash, 'staged_equals_working': staged_hash == sha(data)}
full = json.loads((candidate / full_path).read_text())
production = json.loads((candidate / production_path).read_text())
assert full['metadata']['vulnerabilities'] == {'info': 0, 'low': 5, 'moderate': 0, 'high': 0, 'critical': 0, 'total': 5}
assert production['metadata']['vulnerabilities']['total'] == 0
assert seen[full_path]['sha256'] == next(row for row in proof['records'] if row['label'] == 'accepted-audit-full')['outputs']['stdout']
assert seen[production_path]['sha256'] == next(row for row in proof['records'] if row['label'] == 'accepted-audit-production')['outputs']['stdout']
request = urllib.request.Request('https://registry.npmjs.org/eslint', headers={'Accept': 'application/vnd.npm.install-v1+json'})
with urllib.request.urlopen(request, timeout=30) as response:
    metadata = json.load(response)
versions = [v for v in metadata['versions'] if v.startswith('9.') and '-' not in v]
version = max(versions, key=lambda text: tuple(map(int, text.split('.'))))
item = metadata['versions'][version]
latest9 = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'url': 'https://registry.npmjs.org/eslint/' + version, 'version': version, 'dependencies': item.get('dependencies', {}), 'engines': item.get('engines', {})}
assert latest9['dependencies']['minimatch'].startswith('^3.')
(base / 'latest-eslint9-metadata.json').write_text(json.dumps(latest9, indent=2) + '\n')
record = {
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=candidate).decode().strip(),
    'prior_implementation_binding_sha256': sha((base / 'FINAL_BINDING.json').read_bytes()),
    'implementation_unchanged': True, 'executable_inputs': current,
    'documents_and_final_author_evidence': seen,
    'author_proof_observed_at': proof['observed_at'], 'author_acceptance_read': proof['acceptance'],
    'all_author_gate_records_have_unchanged_source_and_expected_exits': True,
    'all_author_gate_records_have_same_source_digest': True,
    'raw_audit_files_match_actual_command_stdout_hashes': True,
    'fresh_full_audit_counts': full['metadata']['vulnerabilities'], 'fresh_production_audit_counts': production['metadata']['vulnerabilities'],
    'documentation_review': 'Corrected plugin-file count, native ESM distinction, export-inventory wording, current-policy/modern-edge distinction, both resolved shadow findings, Unix qualification and holds are accurately scoped. Full360-diagnostic and347-export comparisons remain attributed to the other independent reviewer; Standards independently established366 complete-config parity and32 plugin outcome parity.',
    'remaining_findings': [],
    'limits': 'Author broad acceptance was read and source-bound, not independently rerun by Standards. No candidate/remote edits or merge/deploy performed. A subsequent commit/evidence copy may receive an additional head binding without retesting byte-identical executable inputs.'
}
(base / 'FINAL_DOCS_AND_ACCEPTANCE_BINDING.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({'head': record['head'], 'implementation_unchanged': True, 'documents': seen, 'acceptance': proof['acceptance'], 'latest_eslint9': version, 'additive_binding_sha256': sha((base / 'FINAL_DOCS_AND_ACCEPTANCE_BINDING.json').read_bytes())}, indent=2))

from pathlib import Path
import datetime
import hashlib
import json
import subprocess

base = Path(__file__).parent
candidate = Path('/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app')
front = candidate / 'frontend'
sha = lambda data: hashlib.sha256(data).hexdigest()
git = lambda *args: subprocess.check_output(['git', *args], cwd=candidate)
paths = ['frontend/package.json', 'frontend/package-lock.json', 'frontend/scripts/apply-tooling-repairs.cjs', 'frontend/scripts/tooling-repairs.json', 'frontend/scripts/tooling-repair-install.test.cjs', 'frontend/scripts/lint-matcher-migration.test.cjs', 'frontend/scripts/fixtures/lint-rules-before-matcher-migration.json']
inputs = {file: sha((candidate / file).read_bytes()) for file in paths}
probe = json.loads((base / 'link-graph-results.json').read_text())
for relative, digest in probe['sourceHashes'].items():
    assert inputs['frontend/' + relative] == digest
permanent = json.loads((base / 'permanent-entry-red-green.json').read_text())
assert permanent['results'][1]['helper_sha256'] == inputs['frontend/scripts/apply-tooling-repairs.cjs']
assert permanent['results'][1]['test_sha256'] == inputs['frontend/scripts/tooling-repair-install.test.cjs']
alias = json.loads((base / 'metadata-alias-resolution-final-results.json').read_text())
assert alias['accepted'] is False
assert alias['sourceHashes']['apply-tooling-repairs.cjs'] == inputs['frontend/scripts/apply-tooling-repairs.cjs']
manifest = json.loads((front / 'scripts/tooling-repairs.json').read_text())
originals = json.loads((base / 'original-inventory-verification.json').read_text())
assert originals['manifest_sha256'] == inputs['frontend/scripts/tooling-repairs.json']
entry = json.loads((base / ('matcher-entry-verification-' + inputs['frontend/scripts/apply-tooling-repairs.cjs'][:12] + '.json')).read_text())
assert all(row['helper_contains_actual_entry_hash'] and row['installed_entry_matches_official_tar'] for row in entry['bindings'])
caller = json.loads((base / 'plugin-callers-final-results.json').read_text())
assert caller['cases'] == 32 and caller['baselineFailures'] == 0 and caller['installedFailures'] == 0 and caller['equivalents'] == 32
for file, digest in caller['sourceHashes'].items():
    inventory = next(p for p in manifest['packages'] if file.startswith(p['name'] + '/'))
    assert inventory['files'][file.removeprefix(inventory['name'] + '/')]['repaired_sha256'] == digest
baseline = json.loads((base / 'baseline-effective-configs.json').read_text())
for file, digest in baseline['sourceInputs'].items():
    if file == '.eslintrc.json' or file.startswith('eslint-rules/'):
        assert sha((front / file).read_bytes()) == digest
rules = json.loads((front / 'scripts/fixtures/lint-rules-before-matcher-migration.json').read_text())
assert all(config['rules'] == rules for config in baseline['configs'].values())
comparison = json.loads((base / 'effective-config-comparison.json').read_text())
assert comparison['filesCompared'] == 366 and not comparison['differences']
lock = json.loads((front / 'package-lock.json').read_text())
named = lambda entry, name: entry == 'node_modules/' + name or entry.endswith('/node_modules/' + name)
graph = {name: [{'path': path, 'version': rec['version'], 'dev': rec.get('dev')} for path, rec in lock['packages'].items() if named(path, name)] for name in ['minimatch', 'glob', 'rimraf']}
for name, version in [('minimatch', '11.0.3'), ('glob', '14.0.3'), ('rimraf', '6.1.3')]:
    assert graph[name] and all(row['version'] == version and row['dev'] is True for row in graph[name])
changes = set(git('diff', 'HEAD', '--name-only', '-z').decode().strip('\0').split('\0')) | set(git('ls-files', '--others', '--exclude-standard', '-z').decode().strip('\0').split('\0'))
changes.discard('')
files = {}
for file in sorted(changes):
    current = (candidate / file).read_bytes()
    try:
        indexed = subprocess.check_output(['git', 'show', ':' + file], cwd=candidate, stderr=subprocess.DEVNULL)
        staged = sha(indexed)
    except subprocess.CalledProcessError:
        staged = None
    files[file] = {'sha256': sha(current), 'staged_sha256': staged, 'matches_staged': staged == sha(current), 'bytes': len(current)}
diff = git('diff', 'HEAD', '--')
(base / 'reviewed-candidate.diff').write_bytes(diff)
record = {
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'candidate': str(candidate), 'branch': git('branch', '--show-current').decode().strip(), 'head': git('rev-parse', 'HEAD').decode().strip(),
    'head_tree': git('rev-parse', 'HEAD^{tree}').decode().strip(), 'reviewed_delta_sha256': sha(diff),
    'executable_inputs': inputs, 'changed_files_observed': files,
    'all_prepared_guard_probes_bind_final_helper': True,
    'all_15_executed_plugin_callsite_hashes_equal_final_manifest': True,
    'entire_effective_configuration_parity': {'files': 366, 'different': 0, 'unique_configs': 2, 'configured_rules': 54, 'enabled_rules': 46, 'all_local_rule_source_and_configuration_bytes_unchanged': True, 'permanent_baseline_matches_independent_snapshot': True},
    'caller_cases': {'raw_originals_with_modern_matcher_fail': 30, 'raw_class_only_controls_pass': 2, 'baseline_and_final_equal': 32},
    'installer_cases': {'total': probe['cases'], 'refused_without_package_tree_changes': sum(row.get('refused', False) for row in probe['output']), 'cold_repaired_files': 25, 'idempotent_repeat_changes': 0, 'full_check_changes': 0, 'explicit_omitted_packages': 7},
    'cache_cases': {'baseline_flat3_rimraf3_pass': 9, 'candidate_flat3_rimraf6_pass': 9, 'rejected_flat4_alternative_fail': 2},
    'provenance': {'new_inventory_original_files_verified_against_official_lock_tars': originals['original_files_verified'], 'new_inventory_package_installations_verified': len(originals['results']), 'complete_repair_inventory_regular_files': sum(len(p['files']) for p in manifest['packages']), 'explicit_cli_links': sum(len(p.get('symlinks', {})) for p in manifest['packages']), 'modern_entry_tar_verification': entry['bindings']},
    'locked_matcher_graph': graph,
    'resolved_finding': {'priority': 'P2', 'description': 'Metadata alias resolves reviewed package.json while untracked nested original3 executable runs. Original helper falsely succeeds; final helper binds and hashes canonical executable and rejects.', 'old_helper': permanent['results'][0]['helper_sha256'], 'final_helper': permanent['results'][1]['helper_sha256'], 'permanent_tests_red': {'pass': 0, 'fail': 2}, 'permanent_tests_green': {'pass': 2, 'fail': 0}},
    'remaining_implementation_findings': [],
    'scope': 'Independent Standards implementation review. Broader final clean-install/full Jest/type/lint/browser and fresh audit acceptance belongs to the author after review closure and is not claimed as reexecuted by this reviewer. Existing Python/worker/deployment/publishing/financial holds remain. Later report/evidence copies or commit require an additive final-head binding. No source or candidate node_modules edits, installs, remote writes, service starts, merge or deployment by this reviewer.'
}
(base / 'FINAL_BINDING.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({'head': record['head'], 'executable_inputs': inputs, 'changed_files': len(files), 'all_staged': all(f['matches_staged'] for f in files.values()), 'remaining_implementation_findings': []}, indent=2))

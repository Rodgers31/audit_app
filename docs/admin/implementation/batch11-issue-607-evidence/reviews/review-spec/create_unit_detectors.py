"""Create immutable reviewer-only copies for two synthetic assertion detectors."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

REPO = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
OUT = Path(__file__).resolve().parent
TARGET = OUT / 'unit-detectors'
TARGET.mkdir()
unit = REPO / 'frontend/__tests__/countiesUrlStateSsr.test.tsx'
original = unit.read_text()
noop = original.replace("listHistoryReplace = jest.spyOn(window.history, 'replaceState');", "listHistoryReplace = jest.spyOn(window.history, 'replaceState').mockImplementation(() => undefined);")
assert noop != original
mutation = original.replace("expect(listHistoryReplace).not.toHaveBeenCalled();", "window.history.replaceState(null, '', window.location.href);\n    expect(listHistoryReplace).not.toHaveBeenCalled();")
assert mutation != original
inputs = {'valid.test.tsx': original, 'noop.test.tsx': noop, 'same-url-write.test.tsx': mutation, 'jest.config.cjs': """const factory = require('/app/frontend/jest.config.js');
module.exports = async () => {
  const base = typeof factory === 'function' ? await factory() : await factory;
  return { ...base, rootDir: '/app/frontend', roots: ['/app/frontend', '/evidence/review-spec/unit-detectors'],
    testMatch: ['/evidence/review-spec/unit-detectors/**/*.test.tsx'],
    moduleDirectories: ['/app/frontend/node_modules', 'node_modules'] };
};
"""}
for name, data in inputs.items():
    with (TARGET / name).open('x') as f:
        f.write(data)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(), 'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=REPO, text=True).strip(), 'generator_sha256': sha(Path(__file__)), 'original_unit_sha256': sha(unit), 'created': time.time(), 'inputs': {name: sha(TARGET / name) for name in inputs}, 'scope': 'Synthetic assertion detectors in reviewer-owned copies; do not count selected/skipped copies as browser inventory or product causal evidence.'}
with (OUT / 'unit-detector-source.json').open('x') as f:
    json.dump(report, f, indent=2)
assert json.loads((OUT / 'unit-detector-source.json').read_text()) == report
print(json.dumps(report, indent=2))

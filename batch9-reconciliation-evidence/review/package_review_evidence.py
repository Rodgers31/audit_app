"""Copy explicitly public receipts without changing their execution identities."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/Users/roger/.codex/worktrees/batch9-pr592-review/audit_app')
SOURCE = Path(__file__).resolve().parent
DEST = ROOT / 'batch9-reconciliation-evidence/review'
NAMES = [
    'publishing-final-scope-current.json', 'publishing-final-scope-minimum.json',
    'spec-final.json', 'spec-final-spec.md', 'standards-current.json',
    'standards-minimum.json', 'standards-current-standards.md',
    'standards-minimum-standards.md', 'ci-controls-final-current.json',
    'ci-controls-final-minimum.json', 'publishing-final-behavior-current.json',
    'frozen-minimum.json', 'critical-lint-final.json', 'final-cleanup.json',
    'temporary-artifact-relocation.json', 'orphan-fixture-cleanup.json',
    'run_checks.py', 'package_review_evidence.py',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DEST.mkdir()
    custody = []
    for name in NAMES:
        original, copy = SOURCE / name, DEST / name
        shutil.copyfile(original, copy)
        assert digest(original) == digest(copy)
        custody.append({'original_path': str(original),
                        'committed_copy': str(copy.relative_to(ROOT)),
                        'sha256': digest(copy), 'bytes_unchanged': True})
    subjects = [
        '.github/scripts/prepare_reconciliation_test_fixture.py',
        '.github/scripts/tests/test_reconciliation_test_fixture.py',
        'backend/tests/batch9_reconciliation_fixture/sitecustomize.py',
        *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'backend/tests').glob('test_batch9_reconciliation*.py'))],
        'backend/seeding/reconciliation.py', 'backend/seeding/reconcile_operator.py',
        'backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py',
        'backend/models.py',
        *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'batch9-reconciliation-evidence').glob('*.py'))],
        'batch9-reconciliation-evidence/behavior/verify_behavior_v6.py',
    ]
    manifest = {'generated_by': 'batch9-reconciliation-evidence/review/package_review_evidence.py',
                'generator_sha256': digest(Path(__file__)),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'author_head': '950a0d54ace562acdf1ade46d66dc7fa18d50cb5',
                'integrated_main': 'b0ec603ccbf29d5ae7f6540faa3d484964334fb1',
                'actual_execution_target': '93f39ded212edb9e847221cdb7def25900015159',
                'copied_receipt_identity': 'original execution identities retained; no postcommit relabeling',
                'custody': custody,
                'source_sha256': {name: digest(ROOT / name) for name in subjects},
                'production_acceptance': 'PENDING; issue #583 remains open',
                'independent_coordinator_review': 'PENDING',
                'historical_supersessions': 'batch9-reconciliation-evidence/publication-supersessions.json'}
    target = DEST / 'custody-manifest.json'
    target.write_text(json.dumps(manifest, indent=2) + '\n')
    assert json.loads(target.read_text()) == manifest
    print(f'{len(custody)} unchanged public artifacts copied; manifest readback verified')


if __name__ == '__main__':
    main()

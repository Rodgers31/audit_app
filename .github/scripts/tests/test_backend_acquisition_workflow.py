"""The manual backend gate removes registry credentials before candidate execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]
TRUSTED_BACKEND_ACQUISITION_REF = 'e00af52f290591c9f1d0109b3e2999407ffc46ef'
MODE = {
    'AUDIT_CI_TEST_POSTGRES_TRANSPORT': 'docker-hub-preloaded-v1',
    'CI': 'true', 'GITHUB_ACTIONS': 'true',
    'GITHUB_EVENT_NAME': '${{ github.event_name }}',
}
RECEIPT = {
    'name': 'Preserve backend registry authentication receipt',
    'if': 'always()', 'uses': 'actions/upload-artifact@v4',
    'with': {'name': 'backend-registry-authentication',
             'path': '${{ runner.temp }}/backend-registry-state.json',
             'if-no-files-found': 'error', 'retention-days': 14},
}
EXISTING_COVERAGE_SECRET_STEPS = {
    'Prepare optional Codecov upload': 'b476c7ee2f3773a4a2f1fcf918b8c6d3648d3bad6aee9225614d9592bbd1ebbe',
    'Attempt optional Codecov upload (hosted report unverified)': '017e0fb77a9078a850f3c0921a8a13c43d8f023e6d3590112b42b91000781004',
}


class BackendAcquisitionWorkflowTests(unittest.TestCase):
    def validate(self, workflow):
        event = workflow.get('on', workflow.get(True))
        self.assertEqual(set(event), {'workflow_dispatch'})
        job = workflow['jobs']['test-backend']
        self.assertIs(type(job['timeout-minutes']), int)
        self.assertEqual(job['timeout-minutes'], 60)
        self.assertEqual(job['env'], MODE)
        steps = job['steps']
        source, acquire, cleanup, candidate, guard = steps[:5]
        self.assertIs(source['with']['persist-credentials'], False)
        self.assertIs(candidate['with']['persist-credentials'], False)
        self.assertRegex(TRUSTED_BACKEND_ACQUISITION_REF, '^[0-9a-f]{40}$')
        self.assertNotEqual(TRUSTED_BACKEND_ACQUISITION_REF, '0' * 40)
        self.assertEqual(source, {
            'name': 'Check out reviewed immutable backend image acquisition source',
            'uses': 'actions/checkout@v5',
            'with': {'ref': TRUSTED_BACKEND_ACQUISITION_REF, 'persist-credentials': False},
        })
        prefix = 'python3 -I .github/scripts/prepare_backend_registry_auth.py '
        state = ' --state "$RUNNER_TEMP/backend-registry-state.json"'
        self.assertEqual(acquire, {
            'name': 'Authenticate pinned backend PostgreSQL pulls',
            'if': "github.event_name == 'workflow_dispatch'",
            'run': prefix + 'prepare' + state + ' --platform linux/amd64',
            'env': {'DOCKERHUB_USERNAME': '${{ secrets.DOCKERHUB_USERNAME }}',
                    'DOCKERHUB_TOKEN': '${{ secrets.DOCKERHUB_TOKEN }}'},
        })
        self.assertEqual(cleanup, {
            'name': 'Remove owned backend registry credentials', 'if': 'always()',
            'run': prefix + 'cleanup' + state,
        })
        self.assertEqual(candidate, {
            'name': 'Check out frozen candidate after backend credential removal',
            'uses': 'actions/checkout@v5',
            'with': {'ref': '${{ inputs.commit_sha }}', 'persist-credentials': False},
        })
        self.assertEqual(guard, {
            'name': 'Verify frozen checkout',
            'run': 'python3 .github/scripts/verify_checkout.py',
            'env': {'VERIFICATION_COMMIT': '${{ inputs.commit_sha }}',
                    'VERIFICATION_SCOPE': '${{ inputs.verification_scope }}'},
        })
        boundary = next(step for step in steps if step.get('name') == 'Test workflow boundaries and optional coverage reporting')
        self.assertEqual(boundary['run'], "env -u AUDIT_CI_TEST_POSTGRES_TRANSPORT python -m unittest discover -s .github/scripts/tests -p 'test_*.py' -v")
        self.assertEqual([step for step in steps if step.get('name') == RECEIPT['name']], [RECEIPT])
        receipt = next(step for step in steps if step.get('name') == RECEIPT['name'])
        self.assertIs(type(receipt['with']['retention-days']), int)
        for environment in (workflow.get('env', {}), job.get('env', {})):
            self.assertFalse({'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'DOCKER_CONFIG'} & set(environment))
            text = json.dumps(environment).casefold()
            self.assertIsNone(re.search(r'\bsecrets\b', text))
            self.assertFalse(any(name in text for name in ('dockerhub_username', 'dockerhub_token')))
        for step in steps:
            if step is not acquire:
                self.assertFalse({'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'DOCKER_CONFIG'} & set(step.get('env', {})))
                text = json.dumps(step).casefold()
                self.assertFalse(any(name in text for name in ('dockerhub_username', 'dockerhub_token')))
                if re.search(r'\bsecrets\b', text):
                    actual = hashlib.sha256(json.dumps(step, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    self.assertEqual(actual, EXISTING_COVERAGE_SECRET_STEPS.get(step.get('name')))

    def test_trusted_acquisition_cleanup_and_candidate_order(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/verification.yml').read_text())
        self.validate(workflow)
        mutations = ('candidate-first', 'mutable-source', 'cleanup-bypass', 'cleanup-condition',
                     'wrong-platform', 'job-secret', 'aliased-secret', 'candidate-credentials',
                     'automatic-event', 'missing-mode', 'fallback-mode', 'missing-receipt',
                     'changed-unit-boundary', 'deadline', 'bracket-secret', 'spaced-secret',
                     'whole-step-context', 'whole-global-context', 'changed-coverage-secret',
                     'source-numeric-false', 'candidate-numeric-false', 'float-deadline', 'float-retention')
        for mutation in mutations:
            bad = deepcopy(workflow)
            job = bad['jobs']['test-backend']
            steps = job['steps']
            if mutation == 'candidate-first':
                steps[0], steps[3] = steps[3], steps[0]
            elif mutation == 'mutable-source':
                steps[0]['with']['ref'] = '${{ inputs.commit_sha }}'
            elif mutation == 'cleanup-bypass':
                steps[2]['continue-on-error'] = True
            elif mutation == 'cleanup-condition':
                steps[2]['if'] = 'success()'
            elif mutation == 'wrong-platform':
                steps[1]['run'] = steps[1]['run'].replace('linux/amd64', 'linux/arm64')
            elif mutation == 'job-secret':
                job['env']['DOCKERHUB_TOKEN'] = '${{ secrets.DOCKERHUB_TOKEN }}'
            elif mutation == 'aliased-secret':
                steps[5]['env'] = {'ALIAS': '${{ SeCrEtS.DOCKERHUB_TOKEN }}'}
            elif mutation == 'bracket-secret':
                steps[5]['env'] = {'ALIAS': "${{ secrets['DOCKERHUB_TOKEN'] }}"}
            elif mutation == 'spaced-secret':
                steps[5]['env'] = {'ALIAS': '${{ secrets . DOCKERHUB_TOKEN }}'}
            elif mutation == 'whole-step-context':
                steps[3]['env'] = {'OPAQUE_ALIAS': '${{ toJSON(secrets) }}'}
            elif mutation == 'whole-global-context':
                bad['env'] = {'OPAQUE_ALIAS': '${{ toJSON(SeCrEtS) }}'}
            elif mutation == 'changed-coverage-secret':
                next(step for step in steps if step.get('name') == 'Prepare optional Codecov upload')['env']['OPAQUE_ALIAS'] = '${{ toJSON(secrets) }}'
            elif mutation == 'candidate-credentials':
                steps[3]['with']['persist-credentials'] = True
            elif mutation == 'source-numeric-false':
                steps[0]['with']['persist-credentials'] = 0
            elif mutation == 'candidate-numeric-false':
                steps[3]['with']['persist-credentials'] = 0
            elif mutation == 'float-deadline':
                job['timeout-minutes'] = 60.0
            elif mutation == 'float-retention':
                next(step for step in steps if step.get('name') == RECEIPT['name'])['with']['retention-days'] = 14.0
            elif mutation == 'automatic-event':
                bad['on']['pull_request'] = {}
            elif mutation == 'missing-mode':
                del job['env']['AUDIT_CI_TEST_POSTGRES_TRANSPORT']
            elif mutation == 'fallback-mode':
                job['env']['AUDIT_CI_TEST_POSTGRES_TRANSPORT'] = 'fallback'
            elif mutation == 'missing-receipt':
                steps.remove(next(step for step in steps if step.get('name') == RECEIPT['name']))
            elif mutation == 'changed-unit-boundary':
                next(step for step in steps if step.get('name') == 'Test workflow boundaries and optional coverage reporting')['run'] = 'true'
            else:
                job['timeout-minutes'] = 90
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.validate(bad)


if __name__ == '__main__':
    unittest.main()

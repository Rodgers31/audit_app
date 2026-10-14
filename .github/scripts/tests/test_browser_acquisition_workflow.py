"""Credential access ends before frozen candidate checkout and browser execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]
TRUSTED_ACQUISITION_REF = '1124c1502a0b0192773c36b1c9059e63d40839bf'


class BrowserAcquisitionWorkflowTests(unittest.TestCase):
    def validate(self, workflow):
        event = workflow.get('on', workflow.get(True))
        self.assertEqual(set(event), {'workflow_dispatch'})
        steps = workflow['jobs']['test-browser-legacy']['steps']
        source, acquire, cleanup, candidate = steps[:4]
        self.assertEqual(source['uses'], 'actions/checkout@v5')
        self.assertEqual(source['with'], {'ref': TRUSTED_ACQUISITION_REF, 'persist-credentials': False})
        self.assertRegex(TRUSTED_ACQUISITION_REF, r'^[0-9a-f]{40}$')
        self.assertNotEqual(TRUSTED_ACQUISITION_REF, '0' * 40, 'A reviewed real helper commit must replace preparation placeholder')
        self.assertEqual(acquire['if'], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(acquire['env'], {
            'DOCKERHUB_USERNAME': '${{ secrets.DOCKERHUB_USERNAME }}',
            'DOCKERHUB_TOKEN': '${{ secrets.DOCKERHUB_TOKEN }}',
            'GITHUB_EVENT_NAME': '${{ github.event_name }}',
        })
        prefix = 'python3 -I .github/scripts/prepare_browser_registry_auth.py '
        suffix = ' --state "$RUNNER_TEMP/browser-registry-state.json"'
        self.assertEqual(acquire['run'], prefix + 'prepare' + suffix)
        self.assertEqual(cleanup['run'], prefix + 'cleanup' + suffix)
        self.assertEqual(cleanup['if'], 'always()')
        self.assertEqual(candidate['uses'], 'actions/checkout@v5')
        self.assertEqual(candidate['with'], {'ref': '${{ inputs.commit_sha }}', 'persist-credentials': False})
        for step in (source, acquire, cleanup, candidate):
            self.assertNotIn('continue-on-error', step)
        self.assertNotIn('if', candidate)
        tests = next(step for step in steps if step.get('name') == 'Run original cases against built Next.js and synthetic API')
        self.assertEqual(tests['env'], {'BROWSER_POSTGRES_TRANSPORT': 'preloaded-dockerhub'})
        self.assertEqual(tests['run'], 'npm run test:e2e:legacy')
        self.assertNotIn('continue-on-error', tests)
        # Environment inheritance and aliases must not reintroduce credentials
        # into candidate-controlled processes after the acquisition step.
        for environment in (workflow.get('env', {}), workflow['jobs']['test-browser-legacy'].get('env', {})):
            self.assertFalse({'DOCKERHUB_USERNAME','DOCKERHUB_TOKEN','DOCKER_CONFIG'} & set(environment))
            self.assertNotIn('secrets', json.dumps(environment).casefold())
        for step in steps:
            if step is not acquire:
                self.assertNotIn('secrets', json.dumps(step).casefold())
            if step is not acquire:
                self.assertFalse({'DOCKERHUB_USERNAME','DOCKERHUB_TOKEN','DOCKER_CONFIG'} & set(step.get('env', {})))

    def test_acquisition_is_trusted_and_cleanup_precedes_candidate_code(self):
        workflow = yaml.safe_load((ROOT/'.github/workflows/verification.yml').read_text())
        self.validate(workflow)
        for mutation in ['candidate-first','wrong-source','cleanup-bypass','secret-in-tests','anonymous-tests','workflow-token','job-token','aliased-token','uppercase-workflow-token','mixed-job-token','uppercase-step-token']:
            bad = deepcopy(workflow)
            steps = bad['jobs']['test-browser-legacy']['steps']
            if mutation == 'candidate-first':
                steps[0], steps[3] = steps[3], steps[0]
            elif mutation == 'wrong-source':
                steps[0]['with']['ref'] = '${{ inputs.commit_sha }}'
            elif mutation == 'cleanup-bypass':
                steps[2]['continue-on-error'] = True
            elif mutation == 'secret-in-tests':
                next(step for step in steps if step.get('env', {}).get('BROWSER_POSTGRES_TRANSPORT'))['env']['DOCKERHUB_TOKEN'] = '${{ secrets.DOCKERHUB_TOKEN }}'
            elif mutation == 'workflow-token':
                bad['env'] = {'DOCKERHUB_TOKEN': '${{ secrets.DOCKERHUB_TOKEN }}'}
            elif mutation == 'job-token':
                bad['jobs']['test-browser-legacy']['env'] = {'DOCKERHUB_TOKEN': '${{ secrets.DOCKERHUB_TOKEN }}'}
            elif mutation == 'aliased-token':
                steps[4]['env']['ALIAS'] = '${{ secrets.DOCKERHUB_TOKEN }}'
            elif mutation == 'uppercase-workflow-token':
                bad['env'] = {'ALIAS': '${{ SECRETS.DOCKERHUB_TOKEN }}'}
            elif mutation == 'mixed-job-token':
                bad['jobs']['test-browser-legacy']['env'] = {'ALIAS': '${{ SeCrEtS.DOCKERHUB_TOKEN }}'}
            elif mutation == 'uppercase-step-token':
                steps[4]['env']['ALIAS'] = '${{ SECRETS.DOCKERHUB_TOKEN }}'
            else:
                next(step for step in steps if step.get('env', {}).get('BROWSER_POSTGRES_TRANSPORT'))['env']['BROWSER_POSTGRES_TRANSPORT'] = 'original-ecr'
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.validate(bad)

    def test_pull_request_and_deployment_callers_have_no_new_secret_requirement(self):
        baseline_hashes = {'ci.yml': '2f7fb89d35d3b1f6bdf5d77809b2329747200a7113f9a9382e5880e27683d095', 'docker-build-deploy.yml': '949e8ae94456b38d2b2d5ed32a899fdc0f6a44541b05c44d19a56063ed055793'}
        for name, expected_hash in baseline_hashes.items():
            raw = (ROOT/'.github/workflows'/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_hash)
            workflow = yaml.safe_load(raw)
            self.assertNotIn('BROWSER_POSTGRES_TRANSPORT', raw.decode())
            self.assertNotIn('prepare_browser_registry_auth.py', raw.decode())
            # Deployment retains its existing global registry username and
            # separate build-job login. No new test-job credentials are added.
            if name == 'docker-build-deploy.yml':
                frontend = workflow['jobs']['test-frontend']
                self.assertNotIn('DOCKERHUB_TOKEN', frontend.get('env', {}))
                self.assertIn('test:e2e:legacy', json.dumps(frontend))


if __name__ == '__main__':
    unittest.main()

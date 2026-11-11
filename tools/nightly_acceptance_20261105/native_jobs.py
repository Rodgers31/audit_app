"""Verify job-specific local native observations and refuse unapproved hosted writers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

sys.dont_write_bytecode = True
from common import BoundEvidence, Refusal, digest, fields, identity, loads, require
import native_corpus
import runtime

PROFILES = Path('docs/operations/nightly-acceptance-20261105/native')
NATIVE_LOCK = Path('tools/nightly_acceptance_20261105/native_runtime/native-artifacts-with-git.lock.json')
ROLES = {
    'production': ('/opt/ingestion', 'backend/ingestion-runtime.lock.json', 86),
    'qualification': ('/opt/qualification', 'backend/ingestion-qualification.lock.json', 95),
}
CPU_FIELDS = ('vendor_id', 'cpu family', 'model', 'model name', 'stepping', 'flags')
LOCAL_SCOPE = 'LOCAL_QUALIFICATION_ONLY'
DISTRIBUTION = 'RETAINED_LOCAL_DOCKER_ARCHIVE'
LOCAL_ENV = {
    'PATH': '/opt/ingestion/bin:/usr/local/bin:/usr/bin:/bin',
    'HOME': '/tmp',
    'TMPDIR': '/tmp',
    'LC_ALL': 'C.UTF-8',
    'OMP_THREAD_LIMIT': '1',
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHON_DOTENV_DISABLED': '1',
}
PROBES = {
    'migrate': (('/opt/ingestion/bin/alembic', 'heads'), 'a756b20a0001 (head)'),
    'bootstrap': (('-B', '-c', 'from bootstrap import initialize_reference_data; '
                   'from github_database_tls import bundle_bytes; '
                   'print(initialize_reference_data.__name__, len(bundle_bytes()) > 1367)'),
                  'initialize_reference_data True'),
    'seed': (('-B', '-m', 'seeding.source_plan', '--check'), None),
    'validate': (('-B', '-m', 'seeding.source_cache', '--help'), None),
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _oci_digest(value):
    require(type(value) is str and value.startswith('sha256:'), 'exact OCI digest required')
    digest(value[7:])


def load_job(job, root=runtime.ROOT):
    require(type(job) is str and job in PROBES, 'unknown native writer job')
    path = root / PROFILES
    with BoundEvidence(maximum_bytes=256 * 1024) as evidence:
        profile_raw = evidence.read(path / f'{job}.local.json')
        profile = loads(profile_raw)
        fields(profile, ('schema', 'scope', 'job', 'bundle_sha256'))
        require(profile['schema'] == 'ingestion-native-job-v1'
                and profile['scope'] == LOCAL_SCOPE, 'local native job profile required')
        require(profile['job'] == job, 'native profile/job mismatch')
        bundle_raw = evidence.read(path / 'local-bundle.json')
        require(_sha(bundle_raw) == digest(profile['bundle_sha256']), 'native bundle digest mismatch')
        bundle = loads(bundle_raw)
        fields(bundle, ('schema', 'scope', 'distribution', 'image', 'cpu', 'native_lock_sha256',
                        'native_inventory_sha256', 'runtimes', 'corpus'))
        require(bundle['schema'] == 'ingestion-native-bundle-v1' and bundle['scope'] == LOCAL_SCOPE
                and bundle['distribution'] == DISTRIBUTION, 'retained local native bundle required')
        image = bundle['image']
        fields(image, ('platform', 'manifest', 'config', 'layers', 'archive_sha256', 'archive_bytes'))
        require(image['platform'] == 'linux/amd64', 'native image platform differs')
        _oci_digest(image['manifest'])
        _oci_digest(image['config'])
        require(type(image['layers']) is list and bool(image['layers']), 'ordered rootfs layers required')
        for layer in image['layers']:
            _oci_digest(layer)
        require(len(set(image['layers'])) == len(image['layers']), 'duplicate rootfs layer')
        digest(image['archive_sha256'])
        require(type(image['archive_bytes']) is int and image['archive_bytes'] > 0,
                'positive native archive size required')
        fields(bundle['cpu'], CPU_FIELDS)
        require(all(type(v) is str and v for v in bundle['cpu'].values()), 'exact CPU values required')
        require(_sha(evidence.read(root / NATIVE_LOCK)) == digest(bundle['native_lock_sha256']),
                'native lock bytes differ')
        digest(bundle['native_inventory_sha256'])
        fields(bundle['runtimes'], ROLES)
        for role, (prefix, lock, count) in ROLES.items():
            entry = bundle['runtimes'][role]
            fields(entry, ('prefix', 'lock_sha256', 'packages', 'runtime_sha256'))
            require(entry['prefix'] == prefix and type(entry['packages']) is int
                    and entry['packages'] == count, 'native runtime role differs')
            require(_sha(evidence.read(root / lock)) == digest(entry['lock_sha256']),
                    'Python lock bytes differ')
            digest(entry['runtime_sha256'])
        fields(bundle['corpus'], ('retained_sha256', 'cases_sha256'))
        require(bundle['corpus']['retained_sha256'] == native_corpus.RETAINED_SHA256,
                'retained corpus binding differs')
        digest(bundle['corpus']['cases_sha256'])
    return bundle, _sha(profile_raw)


def require_job(job):
    require(os.environ.get('GITHUB_JOB') == job, 'runner/job mismatch')


def verify_cpu(expected, raw):
    for block in raw.strip().split('\n\n'):
        rows = [line.split(':', 1) for line in block.splitlines() if ':' in line]
        selected = [(key.strip(), value.strip()) for key, value in rows if key.strip() in CPU_FIELDS]
        require(len(selected) == len(CPU_FIELDS) and dict(selected) == expected,
                'unqualified CPU model or feature flags')


def hosted_preflight(job):
    """The local archive has no authorized hosted launcher or distribution."""
    require_job(job)
    load_job(job)
    raise Refusal('hosted native writer held: no approved immutable distribution, CPU or launcher')


def runner_diagnostics():
    """Report the Actions host independently of the controlled runtime."""
    return {'scope': 'ACTIONS_RUNNER_DIAGNOSTICS', 'job': os.environ.get('GITHUB_JOB'),
            'platform': platform.platform(), 'python': sys.version,
            'cpuinfo': Path('/proc/cpuinfo').read_text(), 'native': runtime.native_inventory()}


def verify_probe_output(job, output, expected):
    if job == 'seed':
        selection = {'domains': ['audits'], 'bootstrap': False, 'dry_run': True,
                     'audits_review': '', 'reacquire_pending_pdf': False,
                     'audits_source_acceptance': '', 'evidence': 'selection_plan_only'}
        matches = identity(loads(output)) == identity(selection)
    elif job == 'validate':
        matches = all(flag in output for flag in ('--database-url-env', '--profile {county,reviewed}', '--fetch'))
    else:
        matches = output.rstrip('\n') == expected
    require(matches, 'offline job probe output differs')


def qualify(job, role, output, retained=None):
    """Run in the local launcher's isolated namespace, with fixed offline probes."""
    require_job(job)
    require(os.environ == {**LOCAL_ENV, 'GITHUB_JOB': job}, 'qualification environment differs')
    require(type(role) is str and role in ROLES, 'unknown native runtime role')
    bundle, profile_sha = load_job(job)
    prefix, lock, count = ROLES[role]
    require(sys.prefix == prefix and sys.executable == prefix + '/bin/python',
            'wrong fixed native interpreter or prefix')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'wrong native platform')
    cpuinfo = Path('/proc/cpuinfo').read_text()
    verify_cpu(bundle['cpu'], cpuinfo)
    actual = runtime.validate_runtime(runtime.verify(runtime.ROOT / lock))
    require(len(actual['packages']) == count and identity(actual['native']) == bundle['native_inventory_sha256']
            and identity(actual) == bundle['runtimes'][role]['runtime_sha256'],
            'exact installed native runtime differs')
    result = {'scope': 'LOCAL_RUNTIME_OBSERVATION', 'job': job, 'role': role, 'profile_sha256': profile_sha,
              'runtime_sha256': identity(actual), 'runtime': actual, 'cpuinfo': cpuinfo}
    if role == 'production':
        require(retained is not None, 'retained native corpus required')
        args, expected = PROBES[job]
        argv = list(args) if args[0].startswith('/') else [sys.executable, *args]
        probe_env = dict(os.environ)
        if job == 'seed':
            probe_env.update(SEED_PLAN_EVENT='workflow_dispatch', SEED_PLAN_DOMAIN='audits',
                             SEED_PLAN_DRY_RUN='true')
        probe = subprocess.run(argv, cwd=runtime.ROOT / 'backend', env=probe_env, capture_output=True,
                               check=True, text=True, timeout=30)
        verify_probe_output(job, probe.stdout, expected)
        corpus = native_corpus.run(output, retained, runtime.ROOT / 'backend')
        require(identity(corpus['cases']) == bundle['corpus']['cases_sha256'],
                'native corpus observations differ')
        result.update(probe={'argv': argv, 'env': probe_env, 'stdout': probe.stdout, 'stderr': probe.stderr},
                      corpus=corpus)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('runner-diagnostics')
    hosted = actions.add_parser('hosted-preflight')
    hosted.add_argument('--job', choices=PROBES, required=True)
    local = actions.add_parser('qualify')
    local.add_argument('--job', choices=PROBES, required=True)
    local.add_argument('--role', choices=ROLES, required=True)
    local.add_argument('--output', type=Path, required=True)
    local.add_argument('--retained', type=Path)
    args = parser.parse_args()
    if args.action == 'hosted-preflight':
        hosted_preflight(args.job)
    elif args.action == 'runner-diagnostics':
        print(json.dumps(runner_diagnostics(), sort_keys=True))
    else:
        print(json.dumps(qualify(args.job, args.role, args.output, args.retained), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

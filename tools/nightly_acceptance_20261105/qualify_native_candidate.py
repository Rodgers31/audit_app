"""Qualify a sealed native candidate offline without granting writer admission."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import re
import selectors
import shutil
import subprocess
import tarfile
import tempfile
import time
from uuid import uuid4

from common import BoundEvidence, canonical, digest, fields, identity, integer, loads, require, sha256, string
from hosted_runner_observation import isolated
from native_corpus import RETAINED_SHA256
from native_jobs import CPU_FIELDS, LOCAL_ENV, PROBES, ROLES
import runtime

REPOSITORY = 'Rodgers31/audit_app'
REF = 'refs/heads/codex/consolidated-execution-20261104'
COMPANION = '5a7ad4c5aa7ef3d52a3eff08df9cb325f45b7b5b'
COMMON_BASE = 'fe6dc884f35997bbcda93a460d9f34d442726b5d'
OFFLINE_FIXTURE_REVISION = '2d04e1c81c8e87dfd49f4a0fdf18d39e0f0f9050'
TAG = 'native-qualification-915-20261111'
IMAGE = 'auditgava-native-qualification:915-20261111'
ASSET = 'auditgava-native-915-linux-amd64.tar'
CORPUS = ('https://www.oagkenya.go.ke/wp-content/uploads/2026/05/'
          'AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf')
CORPUS_CASES = {'text-pdf', 'physical-page-one', 'ruled-table-and-jvm', 'scanned-pdf-ocr',
                'retained-cover-and-decorative-page-one', 'retained-clipped-layout-holds'}
PROBE = '/source/tools/nightly_acceptance_20261105/native_candidate_probe.py'
SOURCE_PATHS = ('backend', 'tools/nightly_acceptance_20261105',
                '.github/workflows/seed.yml', 'scripts/verification/supabase-project-ca.crt',
                'docs/operations/nightly-acceptance-20261105/native',
                'docs/operations/nightly-acceptance-20261105/contract.json')
MEMORY = 4 * 1024**3
FILE_LIMIT = 192 * 1024**2
SCRATCH = {
    '/opt': 'rw,exec,nosuid,nodev,mode=1777,size=2400m',
    '/tmp': 'rw,exec,nosuid,nodev,mode=1777,size=256m',
}
CLIENT_ENV = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'}
CLEAN_ENV = shlex.join(['/usr/bin/env', '-i', *(f'{k}={v}' for k, v in LOCAL_ENV.items())])
BOOTSTRAP = """\
set -eu
tools=/source/tools/nightly_acceptance_20261105
for role in ingestion qualification; do
  lock=ingestion-runtime
  [ "$role" = ingestion ] || lock=ingestion-qualification
  if ! /usr/local/bin/python -B "$tools/runtime.py" install \
      --lock "/source/backend/$lock.lock.json" --wheelhouse "/wheels-$role" \
      --venv "/opt/$role" > "/tmp/install-$role.log" 2>&1; then
    tail -40 "/tmp/install-$role.log" >&2
    exit 1
  fi
done
cd "$tools"
for mode in normal optimized; do
  option=
  [ "$mode" = normal ] || option=-O
  CLEAN_ENV /opt/ingestion/bin/python -B $option "$1" >&2
  cat "/tmp/qualification/$mode-summary.json"
  /usr/bin/env -u PYTHON_DOTENV_DISABLED /opt/qualification/bin/python -B $option -m pytest -p no:cacheprovider -q \
    --basetemp "/tmp/tests-$mode" --junitxml "/tmp/tests-$mode.xml" \
    test_native_runtime_boundary.py test_native_jobs.py test_controls.py >&2
  /usr/local/bin/python -B -c 'import json, sys, xml.etree.ElementTree as ET
row, = ET.parse(sys.argv[2]).getroot().findall("testsuite")
print(json.dumps({"mode": sys.argv[1], "tests": {k: int(row.attrib[k])
    for k in ("tests", "failures", "errors", "skipped")}}))' "$mode" "/tmp/tests-$mode.xml"
done
""".replace('CLEAN_ENV', CLEAN_ENV)


def checked(argv, *, timeout, cwd=None, stdout=None):
    return subprocess.run(argv, env=CLIENT_ENV, capture_output=stdout is None, stdout=stdout,
                          cwd=cwd, timeout=timeout, check=True)


def qualify_observations(lines, expected):
    require(len(lines) <= 128 * 1024, 'candidate output ceiling exceeded')
    rows = [loads(line) for line in lines.splitlines()]
    require(len(rows) == 4, 'incomplete normal/optimized observations')
    semantic = []
    runner_fingerprints = []
    for index, mode in enumerate(('normal', 'optimized')):
        observation, tests = rows[index * 2:index * 2 + 2]
        fields(observation, ('scope', 'writer_admission', 'mode', 'runtime_sha256', 'packages',
                             'native_sha256', 'isolation', 'cpu_independent_runtime_sha256',
                             'tools', 'git', 'cpu', 'probes', 'app_ocr_sha256', 'text', 'maxrss_kib'))
        for key in ('runtime_sha256', 'native_sha256', 'cpu_independent_runtime_sha256', 'app_ocr_sha256'):
            digest(observation[key])
        fields(observation['cpu'], CPU_FIELDS)
        for value in observation['cpu'].values():
            string(value)
        integer(observation['maxrss_kib'], minimum=1)
        fields(observation['git'], ('version', 'sha256'))
        require(observation['git']['version'] == 'git version 2.56.1', 'candidate Git differs')
        digest(observation['git']['sha256'])
        tools = observation['tools']
        fields(tools, ('tesseract', 'java', 'pdftoppm', 'pdftotext', 'pdfinfo'))
        for tool, row in tools.items():
            fields(row, ('path', 'version', 'sha256'))
            require(row['path'] == '/usr/bin/' + tool, 'native executable path differs')
            digest(row['sha256'])
            version = string(row['version']).splitlines()[0]
            if tool == 'tesseract':
                require(version == 'tesseract 5.5.4', 'candidate OCR version differs')
            elif tool == 'java':
                require('Temurin-21.0.13+9' in row['version'], 'candidate JVM version differs')
            else:
                require(version == tool + ' version 26.11.0', 'candidate PDF tool version differs')
        fields(observation['isolation'], ('network_interfaces', 'inactive_interfaces', 'root_read_only',
               'uid', 'capabilities', 'no_new_privileges', 'docker_socket', 'credential_env_present'))
        require(type(observation['isolation']['inactive_interfaces']) is list
                and all(type(name) is str for name in observation['isolation']['inactive_interfaces']),
                'inactive interface inventory differs')
        require(observation['mode'] == mode and observation['scope'] == 'OFFLINE_NATIVE_CANDIDATE'
                and observation['writer_admission'] == 'HELD'
                and integer(observation['packages']) == 86 and isolated(observation['isolation'])
                and set(observation['probes']) == set(PROBES), 'offline job observation differs')
        for probe in observation['probes'].values():
            fields(probe, ('probe_sha256', 'cases'))
            digest(probe['probe_sha256'])
            cases = probe['cases']
            require(type(cases) is list and len(cases) == len(CORPUS_CASES)
                    and {case['id'] for case in cases} == CORPUS_CASES, 'native corpus incomplete')
            for case in cases:
                hashes = [value for key, value in case.items() if key.endswith('_sha256')]
                require(bool(hashes) and all(digest(value) for value in hashes),
                        'native corpus case evidence missing')
        fields(observation['text'], ('pages', 'characters', 'sha256'))
        require(integer(observation['text']['pages']) == 915
                and integer(observation['text']['characters']) == 2027634,
                'retained text counts differ')
        require(observation['text']['sha256'] ==
                'db754688aa4c88fa69908266a41aad28a03e603027226d0fce877fa81c27cc72',
                'retained text digest differs')
        fields(tests, ('mode', 'tests'))
        result = tests['tests']
        fields(result, ('tests', 'failures', 'errors', 'skipped'))
        require(tests['mode'] == mode and integer(result['tests']) == 130
                and all(integer(result[key]) == 0 for key in ('failures', 'errors', 'skipped')),
                'qualification tests incomplete')
        runner_fingerprints.append(identity({k: observation[k] for k in
                                            ('tools', 'cpu', 'runtime_sha256', 'native_sha256')}))
        values = {k: observation[k] for k in
                  ('cpu_independent_runtime_sha256', 'probes', 'git', 'app_ocr_sha256', 'text')}
        semantic.append(identity({**values, 'tests': result['tests'],
                                  'tool_sha256s': {name: row['sha256'] for name, row in tools.items()}}))
    require(semantic[0] == semantic[1] and runner_fingerprints[0] == runner_fingerprints[1], 'normal/optimized qualification differs')
    if expected is not None:
        require(semantic[0] == digest(expected), 'hosted/local semantic qualification differs')
    return {'semantic_sha256': semantic[0], 'observations': rows}


def attach(docker, container):
    deadline = time.monotonic() + 480
    with subprocess.Popen([*docker, 'start', '-a', container], env=CLIENT_ENV,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        output = {process.stdout: bytearray(), process.stderr: bytearray()}
        try:
            with selectors.DefaultSelector() as selector:
                for stream in output:
                    selector.register(stream, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, 'candidate wall ceiling exceeded')
                    for key, _ in selector.select(remaining):
                        block = os.read(key.fd, 16 * 1024)
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        data = output[key.fileobj]
                        data.extend(block)
                        require(len(data) <= 128 * 1024, 'candidate output ceiling exceeded')
            code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            if code:
                print(output[process.stderr].decode(errors='replace')[-12000:], flush=True)
            require(code == 0, 'candidate process failed')
            return bytes(output[process.stdout])
        finally:
            if process.poll() is None:
                process.kill()


def run_candidate(docker, image, inputs, expected=None):
    mounts = {key: str(path.resolve(strict=True)) for key, path in inputs.items()}
    require(set(mounts) == {'/source', '/retained.pdf', '/wheels-ingestion', '/wheels-qualification'},
            'exact candidate input mounts required')
    require(len(set(mounts.values())) == len(mounts)
            and all(path.is_file() if target == '/retained.pdf' else path.is_dir()
                    for target, path in ((name, Path(value)) for name, value in mounts.items())),
            'candidate input aliases or types differ')
    arguments = []
    for target, path in mounts.items():
        require(',' not in path, 'candidate mount path contains a delimiter')
        arguments += ['--mount', f'type=bind,source={path},target={target},readonly']

    def run(*args, timeout=20):
        return checked([*docker, *args], timeout=timeout).stdout

    command = ['/usr/bin/env', '-i', *(f'{key}={value}' for key, value in LOCAL_ENV.items()),
               '/bin/sh', '-ec', BOOTSTRAP, 'candidate-probe', PROBE]
    name = 'auditgava-qualify-' + uuid4().hex

    def inspect():
        state, = loads(run('inspect', container))
        host = state['HostConfig']
        require(state['Id'] == container and state['Image'] == image
                and state['Config']['User'] == '65534:65534' and state['Path'] == command[0]
                and state['Args'] == command[1:] and state['Name'] == '/' + name
                and host['PidMode'] == '' and host['IpcMode'] == 'private'
                and host['Devices'] in (None, [])
                and host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] is True
                and host['CapDrop'] == ['ALL'] and host['SecurityOpt'] == ['no-new-privileges']
                and host['Privileged'] is False and integer(host['PidsLimit']) == 96
                and integer(host['NanoCpus']) == 10**9 and integer(host['Memory']) == MEMORY
                and integer(host['MemorySwap']) == MEMORY
                and canonical(host['Ulimits']) ==
                canonical([{'Name': 'fsize', 'Soft': FILE_LIMIT, 'Hard': FILE_LIMIT}])
                and host['Tmpfs'] == SCRATCH
                and len(state['Mounts']) == len(mounts)
                and {mount['Destination']: mount['Source'] for mount in state['Mounts']
                     if mount['Type'] == 'bind' and mount['RW'] is False} == mounts,
                'candidate sandbox differs')
        return state

    try:
        container = run('create', '--name', name, '--pull=never', '--network=none', '--read-only',
                        '--user=65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                        '--cpus=1', '--memory=4g', '--memory-swap=4g', '--pids-limit=96',
                        '--ulimit', f'fsize={FILE_LIMIT}:{FILE_LIMIT}',
                        '--tmpfs', '/opt:' + SCRATCH['/opt'], '--tmpfs', '/tmp:' + SCRATCH['/tmp'],
                        *arguments, image, *command).decode().strip()
        require(re.fullmatch('[a-f0-9]{64}', container), 'owned container ID required')

        inspect()
        stdout = attach(docker, container)
        state = inspect()['State']
        require(state['Running'] is False and state['OOMKilled'] is False
                and state['Dead'] is False and integer(state['ExitCode']) == 0,
                'candidate did not exit successfully')
        report = qualify_observations(stdout, expected)
    finally:
        owned = run('ps', '-aq', '--no-trunc', '--filter', f'name=^/{name}$').strip()
        if owned:
            run('rm', '-f', name)
        require(not run('ps', '-aq', '--no-trunc', '--filter', f'name=^/{name}$').strip(),
                'owned candidate container remains')
    return {**report, 'container_removed': True, 'writer_admission': 'HELD'}


def download(url, destination, size, expected, *, seconds=90):
    checked(['curl', '--disable', '--fail', '--silent', '--show-error', '--location', '--max-redirs', '4',
             '--proto', '=https', '--proto-redir', '=https', '--max-time', str(seconds),
             '--max-filesize', str(size), '--output', str(destination), url], timeout=seconds + 5)
    require(destination.stat().st_size == size and sha256(destination) == digest(expected),
            'acquired artifact identity differs')


def verify_archive(archive, manifest):
    with tarfile.open(archive, mode='r:') as tar:
        def metadata(path, expected=None):
            member = tar.getmember(path)
            require(member.isfile() and member.size <= 8192, 'invalid OCI metadata member')
            with tar.extractfile(member) as stream:
                raw = stream.read(8193)
            if expected is not None:
                require('sha256:' + hashlib.sha256(raw).hexdigest() == expected,
                        'OCI metadata bytes differ')
            return loads(raw)

        def blob(checksum):
            return metadata('blobs/sha256/' + checksum[7:], checksum)

        index = metadata('index.json')
        image, = index['manifests']
        require(image['digest'] == manifest['manifest'], 'archive OCI manifest differs')
        descriptor = blob(image['digest'])
        require(descriptor['config']['digest'] == manifest['config'], 'archive OCI config differs')
        config = blob(manifest['config'])
        require(config['os'] == 'linux' and config['architecture'] == 'amd64'
                and config['rootfs']['diff_ids'] == manifest['layers'], 'archive OCI rootfs differs')


def qualify_hosted():
    env = os.environ
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_REF') == REF
            and env.get('GITHUB_JOB') == 'qualify_native_candidate'
            and env.get('GITHUB_WORKFLOW_REF') == f'{REPOSITORY}/.github/workflows/ingestion-preflight.yml@{REF}',
            'native qualification job required')
    def git(*args, timeout=20, stdout=None):
        return checked(['git', *args], cwd=runtime.ROOT, timeout=timeout, stdout=stdout).stdout
    revision = git('rev-parse', 'HEAD').decode().strip()
    require(revision == digest(env.get('GITHUB_SHA'), length=40)
            and env.get('GITHUB_WORKFLOW_SHA') == revision, 'checkout source differs')
    git('fetch', '--no-tags', '--depth=16', f'https://github.com/{REPOSITORY}.git',
        OFFLINE_FIXTURE_REVISION, COMPANION, timeout=100)
    require(git('merge-base', OFFLINE_FIXTURE_REVISION, COMPANION).decode().strip() == COMMON_BASE,
            'qualification companion base differs')
    tree = digest(git('merge-tree', '--write-tree', OFFLINE_FIXTURE_REVISION, COMPANION).decode().strip(), length=40)
    with BoundEvidence(maximum_bytes=8192) as bound:
        manifest = loads(bound.read(runtime.ROOT / 'docs/operations/nightly-acceptance-20261105/native/candidate.json'))
    fields(manifest, ('archive_sha256', 'archive_bytes', 'manifest', 'config', 'layers', 'semantic_sha256'))
    require(type(manifest['layers']) is list and len(manifest['layers']) == 1
            and 0 < integer(manifest['archive_bytes']) < 2 * 1024**3,
            'single-layer bounded archive required')
    expected_semantics = digest(manifest['semantic_sha256'])
    for value in [manifest['manifest'], manifest['config'], *manifest['layers']]:
        require(type(value) is str and value.startswith('sha256:'), 'OCI hash required')
        digest(value[7:])
    with tempfile.TemporaryDirectory(prefix='native-candidate-') as directory:
        base = Path(directory)
        archive = base / ASSET
        download(f'https://github.com/{REPOSITORY}/releases/download/{TAG}/{ASSET}', archive,
                 manifest['archive_bytes'], manifest['archive_sha256'])
        verify_archive(archive, manifest)
        retained = base / 'retained.pdf'
        download(CORPUS, retained, 13_428_198, RETAINED_SHA256, seconds=300)
        config = base / 'docker'
        config.mkdir()
        docker = ['docker', '--host', 'unix:///var/run/docker.sock', '--config', str(config)]
        checked([*docker, 'image', 'load', '--input', str(archive)], timeout=90)
        image, = loads(checked([*docker, 'image', 'inspect', IMAGE], timeout=15).stdout)
        require(image['Id'] in (manifest['manifest'], manifest['config'])
                and (not image.get('Descriptor') or image['Descriptor']['digest'] == manifest['manifest'])
                and image['RootFS']['Layers'] == manifest['layers']
                and image['Os'] == 'linux' and image['Architecture'] == 'amd64',
                'loaded candidate image differs')
        source = base / 'source'
        source.mkdir(mode=0o755)
        with (base / 'source.tar').open('xb') as stream:
            git('archive', tree, *SOURCE_PATHS, stdout=stream)
        shutil.unpack_archive(base / 'source.tar', source, filter='data')
        inputs = {'/source': source, '/retained.pdf': retained}
        for role, destination in (('production', 'ingestion'), ('qualification', 'qualification')):
            wheels = base / ('wheels-' + destination)
            runtime.acquire(source / ROLES[role][1], wheels)
            wheels.chmod(0o755)
            inputs['/wheels-' + destination] = wheels
        result = run_candidate(docker, image['Id'], inputs, expected_semantics)
    return {**result, 'source': OFFLINE_FIXTURE_REVISION, 'launcher_source': revision,
            'companion': COMPANION, 'tree': tree, 'manifest': manifest['manifest'], 'archive_sha256': manifest['archive_sha256'],
            'runner_image': env.get('ImageOS'), 'runner_image_version': env.get('ImageVersion')}


if __name__ == '__main__':
    print(json.dumps(qualify_hosted(), sort_keys=True))

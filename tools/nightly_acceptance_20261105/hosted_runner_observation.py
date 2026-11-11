"""Observe the existing standard runner using the pinned public Python base."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

from common import BoundEvidence, Refusal, loads, require
from native_jobs import NATIVE_LOCK, load_job, verify_cpu
from runtime import ROOT


PROBE = """\
import json
import os
from pathlib import Path
import socket

root_read_only = bool(os.statvfs('/').f_flag & os.ST_RDONLY)
links = sorted(name for _, name in socket.if_nameindex())
status = Path('/proc/self/status').read_text().splitlines()
print(json.dumps({
    'cpuinfo': Path('/proc/cpuinfo').read_text(),
    'network_interfaces': links,
    'root_read_only': root_read_only,
    'uid': os.getuid(),
    'capabilities': next(line.split()[1] for line in status if line.startswith('CapEff:')),
    'no_new_privileges': next(line.split()[1] for line in status if line.startswith('NoNewPrivs:')),
    'docker_socket': Path('/var/run/docker.sock').exists(),
    'credential_env_present': any(
        token in name for name in os.environ
        for token in ('TOKEN', 'SECRET', 'DATABASE', 'PASSWORD', 'KEY')
    ),
}))
"""


def isolated(observation):
    return (
        type(observation['uid']) is int and observation['uid'] == 65534
        and observation['network_interfaces'] == ['lo']
        and observation['root_read_only'] is True
        and observation['capabilities'] == '0000000000000000'
        and observation['no_new_privileges'] == '1'
        and observation['docker_socket'] is False
        and observation['credential_env_present'] is False
    )


def observe():
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_JOB') == 'observe_native_runner'
            and platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'standard hosted x86_64 observation job required')
    bundle, profile_sha = load_job('migrate')
    with BoundEvidence(maximum_bytes=256 * 1024) as originals:
        lock_raw = originals.read(ROOT / NATIVE_LOCK)
        require(hashlib.sha256(lock_raw).hexdigest() == bundle['native_lock_sha256'],
                'consumed native lock differs from the profile')
    lock = loads(lock_raw)
    base = lock['base_image']
    require(type(base) is str and re.fullmatch(r'docker\.io/library/python@sha256:[0-9a-f]{64}', base),
            'pinned public base required')
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin'}
    with tempfile.TemporaryDirectory(prefix='native-runner-observation-') as scratch:
        docker = ['docker', '--host', 'unix:///var/run/docker.sock', '--config', scratch]

        def run(*args, timeout=15):
            return subprocess.run([*docker, *args], env=env, capture_output=True,
                                  check=True, text=True, timeout=timeout).stdout

        run('pull', '--platform', 'linux/amd64', base, timeout=100)
        image, = json.loads(run('image', 'inspect', base))
        require(image['Os'] == 'linux' and image['Architecture'] == 'amd64',
                'pulled image platform differs')
        container = run('create', '--pull=never', '--network=none', '--read-only',
                        '--user=65534:65534', '--cap-drop=ALL',
                        '--security-opt=no-new-privileges', '--cpus=1',
                        '--memory=512m', '--pids-limit=32', base, '/usr/bin/env', '-i',
                        'PATH=/usr/local/bin:/usr/bin:/bin', '/usr/local/bin/python', '-I', '-c', PROBE).strip()
        require(re.fullmatch('[0-9a-f]{64}', container), 'owned container ID required')
        try:
            observation = json.loads(run('start', '-a', container))
            require(isolated(observation), 'isolated probe envelope differs')
            state, = json.loads(run('inspect', container))
            host = state['HostConfig']
            exit_code = state['State']['ExitCode']
            require(state['Image'] == image['Id'] and type(exit_code) is int and exit_code == 0
                    and state['Mounts'] == [] and host['NetworkMode'] == 'none'
                    and host['ReadonlyRootfs'] is True and host['Memory'] == 512 * 1024**2
                    and host['PidsLimit'] == 32 and host['NanoCpus'] == 10**9
                    and host['Privileged'] is False, 'probe image, execution or limits differ')
        finally:
            run('rm', '-f', container)
            require(not run('ps', '-a', '--no-trunc', '--filter', f'id={container}',
                            '--format', '{{.ID}}').strip(), 'owned container remains')
    cpuinfo = observation.pop('cpuinfo')
    try:
        verify_cpu(bundle['cpu'], cpuinfo)
    except Refusal:
        matches = False
    else:
        matches = True
    model = next((line.split(':', 1)[1].strip() for line in cpuinfo.splitlines()
                  if line.startswith('model name')), None)
    return {
        'scope': 'HOSTED_RUNNER_BASE_OBSERVATION', 'source': os.environ['GITHUB_SHA'],
        'runner_image': os.environ.get('ImageOS'), 'runner_image_version': os.environ.get('ImageVersion'),
        'base_image': base, 'base_image_config': image['Id'], 'local_profile_sha256': profile_sha,
        'cpu_model': model, 'local_profile_cpu_matches': matches,
        'container_removed': True, 'writer_admission': 'HELD', 'isolation': observation,
    }


if __name__ == '__main__':
    print(json.dumps(observe(), sort_keys=True))

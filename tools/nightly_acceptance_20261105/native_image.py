"""Build and retain a local native rootfs using only an exact offline deb set.

No registry publication, remote build, implicit pull or production admission.
The image is an owned local artifact. Keep its archive and exact digest; hosted
consumption requires separately verified existing artifact capacity and wiring.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
from common import Refusal, loads, publish, require, sha256
from native_artifacts import snapshot_native_assets, verify_native_assets
from native_environment import regular
import runtime

HEAVY_LOCK = '/tmp/auditgava-launch-heavy-20261103.lock'


def source_identity():
    result = {}
    for key, arguments in (('commit', ['rev-parse', 'HEAD']),
                           ('tree', ['rev-parse', 'HEAD^{tree}']),
                           ('status', ['status', '--porcelain=v1', '--untracked-files=all'])):
        probe = subprocess.run(['/usr/bin/git', '-C', str(runtime.ROOT), *arguments],
                               env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'},
                               capture_output=True, timeout=20)
        require(probe.returncode == 0, 'source identity unavailable')
        result[key] = probe.stdout.decode().strip()
    return result


def build(lock_path, directory, output, *, docker_socket=None):
    output = Path(output).absolute()
    require('..' not in output.parts and not output.is_relative_to(runtime.ROOT),
            'fresh external image output required')
    require(all(not p.is_symlink() for p in (output, *output.parents)) and not output.exists(),
            'fresh unaliased image output required')
    installer = regular(Path(__file__).parent / 'native_runtime/install_native.sh')
    lock_path = regular(lock_path)
    default_socket = (Path(pwd.getpwuid(os.getuid()).pw_dir) / '.docker/run/docker.sock'
                      if sys.platform == 'darwin' else Path('/var/run/docker.sock'))
    socket = Path(docker_socket) if docker_socket is not None else default_socket
    require(socket.is_absolute() and '..' not in socket.parts and socket.is_socket(),
            'explicit existing local Docker Unix socket required')
    client = '/usr/local/bin/docker' if sys.platform == 'darwin' else '/usr/bin/docker'
    # Lock covers validation, container installation, commit, export and cleanup.
    with open(HEAVY_LOCK, 'a') as heavy:
        try:
            fcntl.flock(heavy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal('shared heavy lock busy; no image work started') from exc
        integrity = verify_native_assets(lock_path, directory)
        raw_lock = lock_path.read_bytes()
        require(hashlib.sha256(raw_lock).hexdigest() == integrity['lock_sha256'], 'native lock changed')
        native_lock = loads(raw_lock)
        output.mkdir(mode=0o700)
        config = output / 'docker-config'
        config.mkdir(mode=0o700)
        (config / 'config.json').write_text('{}\n')
        docker = [client, '--host', 'unix://' + str(socket), '--config', str(config)]
        client_environment = {'PATH': '/usr/bin:/bin', 'HOME': str(output), 'LC_ALL': 'C.UTF-8'}
        token = uuid.uuid4().hex
        container = 'auditgava-native-build-' + token
        tag = 'auditgava-ingestion-native-20261105:' + token
        commands, failures, image_id, completed = [], [], None, False
        started = time.monotonic()
        helpers = [Path(__file__).parent / name for name in
                   ('native_artifacts.py', 'native_environment.py', 'runtime.py', 'common.py')]
        inputs = {str(p): sha256(p) for p in (Path(__file__), installer, lock_path, *helpers)}
        source = source_identity()

        def command(argv, timeout, label):
            result = subprocess.run([*docker, *argv], env=client_environment,
                                    capture_output=True, timeout=timeout)
            (output / (label + '.log')).write_bytes(result.stdout + result.stderr)
            commands.append({'argv': [*docker, *argv], 'exit': result.returncode, 'log': label + '.log'})
            require(result.returncode == 0, 'native image phase failed: ' + label)
            return result.stdout.decode().strip()

        try:
            captured = snapshot_native_assets(native_lock, directory, output / 'native-debs')
            command(['run', '--name', container, '--pull=never',
                     '--platform=linux/amd64', '--network=none', '--cpus=1', '--memory=1g',
                     '--pids-limit=128', '--security-opt=no-new-privileges',
                     '--ulimit', 'fsize=536870912:536870912',
                     '--tmpfs', '/tmp:exec,size=67108864', '--entrypoint', '/usr/bin/env',
                     '-v', str(captured) + ':/native-debs:ro',
                     '-v', str(installer) + ':/install-native.sh:ro',
                     native_lock['base_image'], '-i', 'PATH=/usr/local/bin:/usr/bin:/bin',
                     '/bin/sh', '/install-native.sh'], 300, 'install')
            image_id = command(['commit', '--change', 'ENV PYTHONDONTWRITEBYTECODE=1',
                                '--change', 'ENTRYPOINT []', '--change', 'CMD ["python", "-B"]',
                                container, tag], 120, 'commit')
            require(image_id.startswith('sha256:') and len(image_id) == 71, 'invalid built image ID')
            inspected = command(['image', 'inspect', tag, '--format', '{{.Id}}'],
                                20, 'image-identity')
            require(inspected == image_id, 'built image readback differs')
            command(['image', 'save', '-o', str(output / 'native-image.tar'), tag],
                    180, 'export')
            require(0 < (output / 'native-image.tar').stat().st_size <= 2 * 1024**3,
                    'native image archive byte ceiling/empty output')
            verify_native_assets(lock_path, directory)
            require(all(sha256(p) == checksum for p, checksum in inputs.items()),
                    'native build input changed')
            require(source_identity() == source, 'native build source identity changed')
            completed = True
        except BaseException as exc:
            failures.append(type(exc).__name__ + ': ' + str(exc))
        finally:
            if not completed:
                failures.append('native image build did not complete')
            def cleanup(argv):
                try:
                    return subprocess.run([*docker, *argv], env=client_environment,
                                          capture_output=True, timeout=20)
                except (OSError, subprocess.SubprocessError) as exc:
                    failures.append('cleanup ' + argv[0] + ': ' + type(exc).__name__ + ': ' + str(exc))
                    return None
            removed = cleanup(['rm', '-f', container])
            census = cleanup(['ps', '-aq', '--filter', 'name=^/' + container + '$'])
            absent = census is not None and census.returncode == 0 and not census.stdout.strip()
            if not absent:
                failures.append('owned build container remains/census failed')
            image_absent = None
            if failures:
                cleanup(['image', 'rm', tag])
                image_census = cleanup(['image', 'inspect', tag])
                image_absent = (image_census is not None and image_census.returncode != 0
                                and b'no such image' in image_census.stderr.lower())
                if not image_absent:
                    failures.append('owned failed-build image absence unproven: ' + tag)
            receipt = {'schema': 'local-ingestion-native-image-build-v1',
                       'generated_by': str(Path(__file__).resolve()), 'generator_sha256': sha256(__file__),
                       'generated_at': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
                       'source': source, 'docker': docker, 'client_environment': client_environment,
                       'artifact_integrity': integrity, 'image_id': image_id, 'owned_tag': tag,
                       'commands': commands, 'seconds': time.monotonic() - started,
                       'archive_sha256': sha256(output / 'native-image.tar')
                           if (output / 'native-image.tar').is_file() else None,
                       'cleanup': {'container': container,
                                   'rm_exit': removed.returncode if removed is not None else None,
                                   'census_exit': census.returncode if census is not None else None,
                                   'container_absent': absent, 'owned_image_tag': tag,
                                   'failed_image_absent': image_absent,
                                   'retained_image': tag if image_id and not failures else None},
                       'failures': failures,
                       'verdict': 'LOCAL_NATIVE_IMAGE_BUILT_QUALIFICATION_PENDING'
                           if not failures else 'FAILED'}
            publish(output / 'build.json', receipt)
        require(not failures, 'native image build failed; retained build.json is diagnostic')
        return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--docker-socket', type=Path)
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(build(args.lock, args.directory, args.output,
                               docker_socket=args.docker_socket), sort_keys=True))
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

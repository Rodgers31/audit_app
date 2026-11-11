"""Provision and exercise the parser before the writer receives any credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, require
from native_corpus import pdf
from qualify_native_candidate import ASSET, REF, REPOSITORY, SOURCE_PATHS, TAG, download, verify_archive
import runtime

sys.path.insert(0, str(runtime.ROOT / 'backend'))
from seeding import isolated_parser


def prepare(root, tree, archive, wheelhouse):
    """Shared exact provisioner for a hosted canary and a real writer."""
    source = root / 'source'
    source.mkdir(mode=0o755)
    archive_source = root / 'source.tar'
    with archive_source.open('xb') as stream:
        subprocess.run(['git', 'archive', tree, *SOURCE_PATHS], cwd=runtime.ROOT,
                       env=isolated_parser.CLIENT_ENV, stdout=stream, check=True, timeout=60)
    shutil.unpack_archive(archive_source, source, filter='data')
    archive_source.unlink()
    config = root / 'docker'
    config.mkdir(mode=0o700)
    (config / 'config.json').write_bytes(b'{}\n')
    docker = isolated_parser._docker_command(root)

    manifest = json.loads((source / 'docs/operations/nightly-acceptance-20261105/native/candidate.json').read_bytes())
    require(manifest['manifest'] == isolated_parser.IMAGE
            and manifest['config'] == isolated_parser.IMAGE_CONFIG
            and manifest['layers'] == [isolated_parser.IMAGE_DIFF_ID],
            'reviewed parser identity differs')
    if archive is None:
        archive = root / ASSET
        download(f'https://github.com/{REPOSITORY}/releases/download/{TAG}/{ASSET}', archive,
                 manifest['archive_bytes'], manifest['archive_sha256'])
        verify_archive(archive, manifest)
        subprocess.run([*docker, 'image', 'load', '--input', str(archive)],
                       env=isolated_parser.CLIENT_ENV, check=True, timeout=120,
                       stdout=subprocess.DEVNULL)
        archive.unlink()
    image = isolated_parser._verified_image(docker)
    lock = source / 'backend/ingestion-runtime.lock.json'
    if wheelhouse is None:
        wheelhouse = root / 'wheels'
        runtime.acquire(lock, wheelhouse)
    wheelhouse.chmod(0o755)
    runtime.wheels_verified(runtime.load_lock(lock), wheelhouse)
    stage = root / 'install'
    stage.mkdir(mode=0o755)
    # No document enters this container. It only installs the verified wheel
    # set into a new directory; the writer later mounts that venv read-only.
    mounts = (('/source', source, ',readonly'), ('/wheels', wheelhouse, ',readonly'), ('/opt', stage, ''))
    args = []
    for target, directory, mode in mounts:
        require(',' not in str(directory) and not directory.is_symlink(), 'invalid installation mount')
        args += ['--mount', f'type=bind,source={directory},target={target}{mode}']
    subprocess.run([*docker, 'run', '--rm', '--pull=never', '--platform=linux/amd64', '--network=none',
                    '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--memory=2g', '--memory-swap=2g', '--pids-limit=64', '--cpus=2',
                    '--user', f'{os.getuid()}:{os.getgid()}',
                    '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,mode=1777,size=192m',
                    *args, '--entrypoint', '/usr/bin/env', image,
                    '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/tmp', 'LC_ALL=C.UTF-8',
                    '/usr/local/bin/python', '-B', '/source/tools/nightly_acceptance_20261105/runtime.py',
                    'install', '--wheelhouse', '/wheels', '--venv', '/opt/ingestion'],
                   env=isolated_parser.CLIENT_ENV, check=True, timeout=480,
                   stdout=subprocess.DEVNULL)
    (stage / 'ingestion').rename(root / 'runtime')
    stage.rmdir()
    return lock, wheelhouse


def canary(root):
    """Exercise the actual path before the job exports its verified runtime."""
    marker = root / 'writer-only'
    marker.write_text('synthetic writer-only file')
    document = root / 'owned.pdf'
    document.write_bytes(pdf([b'BT /F1 24 Tf 60 700 Td (AUDIT 310327) Tj ET']))
    try:
        result = isolated_parser._call(
            'seeding.isolated_parser:_containment_probe', document,
            {'writer_only': str(marker)}, {}, {ValueError.__name__: ValueError}, 90, root)
        require(result == {'pages': 1, 'ocr': True, 'writer_isolated': True},
                'parser container canary failed')
    finally:
        marker.unlink()
        document.unlink()


def qualify():
    """Exercise the same provisioner on a standard runner with owned input."""
    env = os.environ
    require(env.get('GITHUB_ACTIONS') == 'true'
            and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_REF') == REF
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_JOB') == 'qualify_isolated_parser'
            and env.get('GITHUB_WORKFLOW_REF') == f'{REPOSITORY}/.github/workflows/ingestion-preflight.yml@{REF}',
            'credential-free parser qualification workflow required')
    revision = digest(env.get('GITHUB_SHA'), length=40)
    require(revision == env.get('GITHUB_WORKFLOW_SHA') == checkout_revision(),
            'qualification source differs')
    prove_no_writer_secrets(env)
    root = Path(env['RUNNER_TEMP']).resolve(strict=True) / 'qualify-isolated-parser'
    root.mkdir(mode=0o700)
    try:
        lock, wheels = prepare(root, revision, None, None)
        runtime.install(lock, wheels, root / 'writer')
        canary(root)
        print(f'Isolated parser provisioned and exercised for {revision}; no production connection.')
    finally:
        shutil.rmtree(root)


def checkout_revision():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runtime.ROOT,
                                   env=isolated_parser.CLIENT_ENV, timeout=20).decode().strip()


def prove_no_writer_secrets(env):
    require(not any(name in env for name in (
        'DATABASE_URL', 'DATABASE_POOLER_URL', 'SUPABASE_SERVICE_ROLE_KEY',
        'RECEIPT_SUPABASE_SECRET_KEY', 'RECEIPT_R2_ACCESS_KEY_ID',
        'RECEIPT_R2_SECRET_ACCESS_KEY', 'RECEIPT_R2_CONTROL_TOKEN',
    )),
            'provisioning must run before writer secrets are present')


def main():
    env = os.environ
    ref = 'refs/heads/main'
    workflow = '.github/workflows/seed.yml'
    jobs = {'migrate', 'bootstrap', 'seed', 'validate'}
    job = env.get('GITHUB_JOB')
    require(env.get('GITHUB_ACTIONS') == 'true'
            and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_REF') == ref
            and job in jobs and env.get('GITHUB_WORKFLOW_REF') == f'{REPOSITORY}/{workflow}@{ref}'
            and (env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
                 or (env.get('GITHUB_EVENT_NAME') == 'schedule' and env.get('NIGHTLY_ENABLED') == 'true')),
            'reviewed writer workflow required')
    revision = digest(env.get('GITHUB_SHA'), length=40)
    require(revision == env.get('APPROVED_SHA') == env.get('GITHUB_WORKFLOW_SHA') == checkout_revision(),
            'writer source is not admitted')
    prove_no_writer_secrets(env)
    root = Path(env['RUNNER_TEMP']).resolve(strict=True) / f'isolated-parser-{job}'
    root.mkdir(mode=0o700)
    lock, wheels = prepare(root, revision, None, None)
    host = root / 'writer'
    runtime.install(lock, wheels, host)
    canary(root)
    shutil.rmtree(wheels)
    with open(env['GITHUB_PATH'], 'a', encoding='utf-8') as out:
        out.write(f'{host}/bin\n')
    with open(env['GITHUB_ENV'], 'a', encoding='utf-8') as out:
        out.write(f'SEED_PARSER_ROOT={root}\n')
    print('Verified writer dependencies and isolated parser on this runner.')


if __name__ == '__main__':
    if sys.argv[1:] == ['--qualification']:
        qualify()
    else:
        require(not sys.argv[1:], 'unexpected writer provisioning argument')
        main()

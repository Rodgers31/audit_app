"""Build-only bounded installation of the complete public runtime lock.

One locked distribution per pip process avoids retaining all wheel/resolver state
in a single installer. Final pip check and exact installed-version readback are
mandatory. This never reads a live service, credential or ambient package index.
"""
import importlib.metadata
from pathlib import Path
import re
import subprocess
import sys
from pip._vendor.packaging.version import Version


def install(path):
    rows = Path(path).read_text().splitlines()
    pinned = []
    names = set()
    for row in rows:
        row = row.strip()
        if not row or row.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)', row)
        if match is None:
            raise ValueError('Only exact public distribution pins are supported')
        name, version = match.groups()
        Version(version)  # Validate every PEP440 value before the first install.
        canonical = re.sub(r'[-_.]+', '-', name).lower()
        if canonical in names:
            raise ValueError('Duplicate distribution pin')
        names.add(canonical)
        pinned.append((name, version, row))
    if not pinned:
        raise ValueError('Nonempty complete lock required')
    # Upgrade the profile's installer before it handles any other distribution.
    # Stable sorting retains the declared order of all non-installer pins.
    pinned.sort(key=lambda item: item[0].lower() != 'pip')
    # PIP_CONFIG_FILE disables global/site config too; --isolated alone does not.
    environment = dict(PATH='/usr/local/bin:/usr/bin:/bin', HOME='/tmp',
        LC_ALL='C.UTF-8', PIP_CONFIG_FILE='/dev/null')
    for index, (name, version, row) in enumerate(pinned, 1):
        print('FIXTURE_LOCK_INSTALL %d/%d %s' % (index, len(pinned), row), flush=True)
        subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
            '--index-url', 'https://pypi.org/simple', '--no-deps', '--no-cache-dir', row],
            check=True, env=environment)
        if importlib.metadata.version(name) != version:
            raise RuntimeError('Exact installed version readback differs')
    subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'check'],
        check=True, env=environment)
    print('FIXTURE_LOCK_VERIFIED %d' % len(pinned), flush=True)


if __name__ == '__main__':
    if sys.argv != [sys.argv[0], '/input/requirements.lock']:
        raise ValueError('Fixed public build lock required')
    install('/input/requirements.lock')

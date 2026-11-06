"""Offline wheel acquisition/installation and exact ingestion-runtime readback.

Run with CPython 3.12.16 on Linux x86_64. Never installs into the invoking
interpreter. Network resolution belongs to the separately reviewed lock producer.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import sysconfig
import venv
import zipfile
from email.parser import BytesParser

sys.dont_write_bytecode = True
from common import Refusal, digest, fields, identity, integer, publish, read_json, require, sha256, string

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'backend/ingestion-runtime.lock.json'
APPROVED_LOCK_IDS = {'a4066dc41ce4d3f42bbf44e5df967d2bb90f50537d43db329b774935a7546ce8', 'dab4db7f4443c6035f9fc34f950dfad63351847f15231cd6c1c61b20c636ed44'}
PAYLOAD_SHA256 = '0d527709b1b2279c90a4ec0513975b522e0bfc2103302bfcca818f3839af5282'
MANIFESTS = ('backend/requirements.txt', 'backend/security-constraints.txt')


def normalized(name):
    return re.sub(r'[-_.]+', '-', string(name)).lower()


def load_lock(path=LOCK):
    return validate_lock(read_json(path))


def validate_lock(lock):
    fields(lock, ('schema', 'python', 'system', 'machine', 'manifests', 'packages'))
    require(lock['schema'] == 'ingestion-runtime-v1', 'unknown runtime lock schema')
    require(lock['python'] == '3.12.16' and lock['system'] == 'Linux' and lock['machine'] == 'x86_64',
            'unqualified runtime target')
    require(type(lock['manifests']) is dict and set(lock['manifests']) in (set(MANIFESTS), set(MANIFESTS) | {'backend/ingestion-qualification.in'}), 'unknown locked manifests')
    for name, checksum in lock['manifests'].items():
        require(sha256(ROOT / name) == digest(checksum), f'manifest changed: {name}')
    require(type(lock['packages']) is list and bool(lock['packages']), 'empty package lock')
    names, wheels = set(), set()
    for row in lock['packages']:
        fields(row, ('name', 'version', 'filename', 'sha256', 'url'))
        name = normalized(row['name'])
        require(name == row['name'] and name not in names, 'noncanonical/duplicate package')
        names.add(name)
        require(re.fullmatch(r'[A-Za-z0-9_.+!]+', string(row['version'])) is not None, 'invalid pin')
        wheel = string(row['filename'])
        require(Path(wheel).name == wheel and wheel.endswith('.whl') and wheel not in wheels,
                'invalid/duplicate wheel filename')
        wheels.add(wheel)
        digest(row['sha256'])
        require(string(row['url']).startswith('https://files.pythonhosted.org/packages/')
                and row['url'].endswith('/' + wheel), 'nonofficial wheel URL')
    require('pip' in names, 'installer must be locked')
    require(identity(lock) in APPROVED_LOCK_IDS, 'lock differs from reviewed complete artifact set')
    return lock


def wheels_verified(lock, wheelhouse):
    validate_lock(lock)
    wheelhouse = Path(wheelhouse)
    require(wheelhouse.is_dir() and not wheelhouse.is_symlink(), 'wheelhouse required')
    require({p.name for p in wheelhouse.iterdir()} == {r['filename'] for r in lock['packages']},
            'wheelhouse must contain exactly the locked wheels')
    for row in lock['packages']:
        path = wheelhouse / row['filename']
        require(path.is_file() and not path.is_symlink() and sha256(path) == row['sha256'],
                f"wheel hash mismatch: {row['name']}")
        with zipfile.ZipFile(path) as archive:
            files = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            require(len(files) == 1, 'one wheel METADATA required')
            metadata = BytesParser().parsebytes(archive.read(files[0]))
        require(normalized(metadata['Name']) == row['name'] and metadata['Version'] == row['version'],
                'wheel metadata differs from lock')
    return identity(lock)


def environment():
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'LC_ALL': 'C.UTF-8',
            'PIP_CONFIG_FILE': '/dev/null', 'PYTHONDONTWRITEBYTECODE': '1'}


def target_verified(lock):
    validate_lock(lock)
    require(platform.python_implementation() == 'CPython'
            and platform.python_version() == lock['python'] and platform.system() == lock['system']
            and platform.machine() == lock['machine'], 'interpreter/platform differs from lock')


def package_inventory():
    rows = {}
    for distribution in importlib.metadata.distributions():
        name = normalized(distribution.metadata['Name'])
        require(name not in rows, 'duplicate installed distribution')
        # RECORD binds installed extension/parser bytes as well as version strings.
        records = []
        raw_record = distribution.read_text('RECORD')
        require(type(raw_record) is str and bool(raw_record), f'installed RECORD missing: {name}')
        seen = set()
        for row in csv.reader(raw_record.splitlines()):
            require(len(row) == 3 and row[0] and row[0] not in seen, 'malformed/duplicate installed RECORD')
            seen.add(row[0])
            path = Path(distribution.locate_file(row[0]))
            if row[0].endswith('.pyc') and not path.exists():
                records.append([row[0], None])
                continue
            require(path.is_file(), f'installed RECORD file absent: {name} {row[0]}')
            checksum = sha256(path)
            if row[1]:
                algorithm, encoded = row[1].split('=', 1)
                require(algorithm == 'sha256' and base64.urlsafe_b64encode(bytes.fromhex(checksum)).decode().rstrip('=') == encoded,
                        f'installed RECORD digest differs: {name} {row[0]}')
            if row[2]:
                require(row[2].isdigit() and int(row[2]) == path.stat().st_size, 'installed RECORD size differs')
            records.append([row[0], checksum])
        require(bool(records), f'empty installed record: {name}')
        rows[name] = {'version': distribution.version, 'files_sha256': identity(sorted(records))}
    require(bool(rows), 'nonempty installed distribution inventory required')
    return dict(sorted(rows.items()))


def native_inventory():
    """Absence is explicit; callers decide parity against a reviewed native lock."""
    import shutil
    result = {}
    for name, argv in {'tesseract': ['--version'], 'pdftoppm': ['-v'],
                       'pdftotext': ['-v'], 'pdfinfo': ['-v'], 'java': ['-version']}.items():
        path = shutil.which(name)
        if path is None:
            result[name] = None
            continue
        process = subprocess.run([path, *argv], env=environment(), capture_output=True, timeout=10)
        require(process.returncode == 0, f'native version probe failed: {name}')
        result[name] = {'path': path, 'sha256': sha256(path),
                        'version': (process.stdout + process.stderr).decode(errors='strict').strip()}
    # OCR trained data and dynamic native dependencies must accompany executable IDs.
    dpkg = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n'],
                          capture_output=True, env=environment(), timeout=15)
    require(dpkg.returncode == 0 and bool(dpkg.stdout.strip()), 'native package inventory unavailable')
    result['dpkg'] = sorted(dpkg.stdout.decode().splitlines())
    result['dpkg_sha256'] = identity(result['dpkg'])
    result['traineddata'] = {str(p): sha256(p) for p in sorted(Path('/usr/share/tesseract-ocr').rglob('*.traineddata'))}
    if result['tesseract'] is not None:
        languages = subprocess.run([result['tesseract']['path'], '--list-langs'], capture_output=True, env=environment(), timeout=10)
        require(languages.returncode == 0, 'OCR language census failed')
        result['languages'] = languages.stdout.decode().splitlines()
    else:
        result['languages'] = []
    linked = {}
    for name in ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo', 'java'):
        if result[name] is None:
            continue
        probe = subprocess.run(['ldd', str(Path(result[name]['path']).resolve())], capture_output=True, env=environment(), timeout=10)
        require(probe.returncode == 0, 'native linked-library census failed')
        for token in probe.stdout.decode().split():
            if token.startswith('/'):
                library = Path(token)
                require(library.is_file(), 'linked library missing')
                linked[str(library)] = sha256(library)
    if result['java'] is not None:
        # libjvm and the module/security stores are loaded after the launcher
        # starts; ldd(java) does not enumerate them. Bind the complete selected
        # JVM home, following Debian's alternatives/configuration links to the
        # bytes actually consumed, without treating the runner's other JDKs as
        # part of this execution environment.
        java_home = Path(result['java']['path']).resolve().parent.parent
        require((java_home / 'lib/server/libjvm.so').is_file(), 'selected JVM library absent')
        seen_directories, file_count, byte_count = set(), 0, 0
        for directory, directories, files in os.walk(java_home, followlinks=True):
            resolved = Path(directory).resolve()
            require(resolved not in seen_directories, 'selected JVM directory cycle/alias')
            seen_directories.add(resolved)
            directories.sort()
            for filename in sorted(files):
                member = Path(directory) / filename
                require(member.is_file(), 'selected JVM nonregular/missing file')
                file_count += 1
                byte_count += member.stat().st_size
                require(file_count <= 8192 and byte_count <= 512 * 1024**2,
                        'selected JVM inventory ceiling')
                linked[str(member)] = sha256(member)
    result['linked_libraries'] = linked
    result['os_release_sha256'] = sha256('/etc/os-release')
    return result


def verify(lock_path=LOCK, native_profile=None):
    lock = load_lock(lock_path)
    target_verified(lock)
    site_roots = {Path(sysconfig.get_path(key)) for key in ('purelib', 'platlib')}
    require(all(not any(root.rglob('*.pyc')) for root in site_roots), 'precompiled site-package bytecode refuses artifact qualification')
    payloads_verified(lock)
    actual = package_inventory()
    expected = {r['name']: r['version'] for r in lock['packages']}
    require({n: r['version'] for n, r in actual.items()} == expected, 'installed packages differ from lock')
    subprocess.run([sys.executable, '-I', '-B', '-m', 'pip', '--isolated', 'check'],
                   env=environment(), check=True, timeout=60)
    native = native_inventory()
    if native_profile is not None:
        expected_native = read_json(native_profile)
        fields(expected_native, ('schema', 'native'))
        require(expected_native['schema'] == 'reviewed-ingestion-native-v1', 'unknown native profile')
        require(all(native[name] is not None for name in ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo')), 'required OCR/PDF tools absent')
        require(identity(native) == identity(expected_native['native']), 'native runtime differs from reviewed profile')
    return {'native_profile_sha256': sha256(native_profile) if native_profile else None,
            'qualification': 'PYTHON_AND_REVIEWED_NATIVE' if native_profile else 'PYTHON_ONLY_NATIVE_PENDING',
            'lock_sha256': sha256(lock_path), 'python': platform.python_version(),
            'executable_sha256': sha256(sys.executable), 'stdlib_sha256': stdlib_identity(), 'soabi': sysconfig.get_config_var('SOABI'),
            'system': platform.system(), 'machine': platform.machine(),
            'packages': actual, 'native': native}


def payloads_verified(lock):
    validate_lock(lock)
    path = ROOT / 'backend/ingestion-payloads.lock.json'
    require(sha256(path) == PAYLOAD_SHA256, 'installed payload manifest differs from reviewed source')
    payloads = read_json(path)
    require(payloads['schema'] == 'ingestion-installed-payloads-v1', 'unknown payload manifest')
    registered = set()
    prefix = Path(sys.prefix).resolve()
    for row in sorted(lock['packages'], key=lambda item: item['name'] != 'pip'):
        distribution = importlib.metadata.distribution(row['name'])
        expected = payloads['packages'][row['name']]
        require(expected['wheel_sha256'] == row['sha256'], 'payload/wheel identity differs')
        for member, checksum in expected['files'].items():
            actual = Path(distribution.locate_file(member))
            require(actual.is_file() and sha256(actual) == checksum,
                    f"installed wheel payload differs: {row['name']} {member}")
        for member, checksum in expected['scripts'].items():
            script = prefix / 'bin' / member
            require(script.is_file() and hashlib.sha256(script.read_bytes().split(b'\n', 1)[1]).hexdigest() == checksum,
                    'installed wheel script body differs')
        # Trust installer-generated entry wrappers only after the pip wheel's
        # own Python payload was matched above (pip is validated first below).
        allowed = {Path(distribution.locate_file(member)).resolve() for member in expected['files']}
        metadata_members = [member for member in expected['files'] if member.endswith('.dist-info/METADATA')]
        require(len(metadata_members) == 1, 'exact installed metadata directory required')
        metadata = Path(distribution.locate_file(metadata_members[0])).parent
        allowed.add((metadata / 'RECORD').resolve())
        for member, content in (('INSTALLER', b'pip\n'), ('REQUESTED', b'')):
            generated = metadata / member
            if generated.exists():
                require(generated.read_bytes() == content, 'unexpected generated installer metadata')
                allowed.add(generated.resolve())
        import configparser
        entry_file = metadata / 'entry_points.txt'
        entries = configparser.ConfigParser()
        if entry_file.exists():
            entries.read_string(entry_file.read_text())
        from pip._internal.operations.install.wheel import PipScriptMaker
        from pip._vendor.distlib.util import get_export_entry
        maker = PipScriptMaker(None, str(prefix / 'bin'))
        maker.executable = str(prefix / 'bin/python')
        for section in ('console_scripts', 'gui_scripts'):
            if not entries.has_section(section):
                continue
            for name, export in entries.items(section):
                names = [name]
                if row['name'] == 'pip' and name == 'pip':
                    names.extend(['pip3', 'pip3.12'])
                text = maker._get_script_text(get_export_entry(name + '=' + export)).encode()
                expected_script = maker._get_shebang('utf-8') + text
                for generated_name in names:
                    generated = prefix / 'bin' / generated_name
                    require(generated.is_file() and generated.read_bytes() == expected_script,
                            f'unreviewed generated entrypoint wrapper: {generated_name}')
                    allowed.add(generated.resolve())
        for member, checksum in expected['scripts'].items():
            generated = prefix / 'bin' / member
            require(generated.read_bytes().split(b'\n', 1)[0] == ('#!' + str(prefix / 'bin/python')).encode(),
                    'wheel script interpreter differs')
            allowed.add(generated.resolve())
        raw_record = distribution.read_text('RECORD')
        require(type(raw_record) is str and bool(raw_record), 'installed RECORD missing')
        owned = set()
        for entry in csv.reader(raw_record.splitlines()):
            require(len(entry) == 3 and bool(entry[0]), 'malformed installed RECORD')
            actual = Path(distribution.locate_file(entry[0])).resolve()
            require(actual.is_relative_to(prefix), 'installed RECORD escapes owned interpreter')
            if actual not in allowed and actual.is_relative_to(prefix / 'include'):
                require(actual.is_file() and sha256(actual) in expected['nonruntime_headers'].values(),
                        'unreviewed installed header')
            else:
                require(actual in allowed, 'installed RECORD registers unreviewed payload')
            require(actual not in owned, 'duplicate installed path')
            owned.add(actual)
        require(allowed <= owned, 'installed RECORD omits expected wheel/generated payload')
        registered.update(owned)
    for key in ('purelib', 'platlib'):
        for actual in Path(sysconfig.get_path(key)).rglob('*'):
            require(not actual.is_symlink(), 'site-package symlink refuses artifact qualification')
            if actual.is_file():
                require(actual.resolve() in registered, 'unrecorded site-package payload refuses qualification')


def stdlib_identity():
    root = Path(sysconfig.get_path('stdlib'))
    rows = {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob('*'))
            if 'site-packages' not in p.relative_to(root).parts and p.is_file()}
    library = Path(sysconfig.get_config_var('LIBDIR')) / sysconfig.get_config_var('LDLIBRARY')
    require(library.is_file(), 'linked Python library absent')
    rows['@linked-libpython/' + library.name] = sha256(library)
    require(bool(rows), 'stdlib file inventory missing')
    return identity(rows)


def validate_runtime(value):
    fields(value, ('qualification', 'native_profile_sha256', 'lock_sha256', 'python', 'executable_sha256',
                   'stdlib_sha256', 'soabi', 'system', 'machine', 'packages', 'native'))
    digest(value['lock_sha256'])
    paths = [ROOT / 'backend/ingestion-runtime.lock.json', ROOT / 'backend/ingestion-qualification.lock.json']
    matches = [p for p in paths if p.is_file() and sha256(p) == value['lock_sha256']]
    require(len(matches) == 1, 'unknown runtime artifact lock')
    lock = load_lock(matches[0])
    require(value['python'] == lock['python'] and value['system'] == lock['system']
            and value['machine'] == lock['machine'], 'runtime target differs')
    digest(value['executable_sha256'])
    digest(value['stdlib_sha256'])
    string(value['soabi'])
    expected = {p['name']: p['version'] for p in lock['packages']}
    require(type(value['packages']) is dict and set(value['packages']) == set(expected), 'runtime packages incomplete')
    for name, package in value['packages'].items():
        fields(package, ('version', 'files_sha256'))
        require(package['version'] == expected[name], 'runtime version differs')
        digest(package['files_sha256'])
    native = value['native']
    fields(native, ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo', 'java', 'dpkg', 'dpkg_sha256',
                    'os_release_sha256', 'traineddata', 'languages', 'linked_libraries'))
    for tool in ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo', 'java'):
        if native[tool] is not None:
            fields(native[tool], ('path', 'sha256', 'version'))
            require(Path(string(native[tool]['path'])).is_absolute(), 'absolute native tool path required')
            digest(native[tool]['sha256']); string(native[tool]['version'])
    require(type(native['dpkg']) is list and bool(native['dpkg'])
            and all(type(x) is str and x for x in native['dpkg'])
            and len(set(native['dpkg'])) == len(native['dpkg'])
            and identity(native['dpkg']) == digest(native['dpkg_sha256']), 'native package inventory differs')
    digest(native['os_release_sha256'])
    for key in ('traineddata', 'linked_libraries'):
        require(type(native[key]) is dict, 'native file inventory required')
        for name, checksum in native[key].items():
            require(Path(string(name)).is_absolute(), 'absolute native file path required')
            digest(checksum)
    require(type(native['languages']) is list and all(type(x) is str and x for x in native['languages'])
            and len(set(native['languages'])) == len(native['languages']),
            'OCR language inventory required')
    require(value['qualification'] in ('PYTHON_ONLY_NATIVE_PENDING', 'PYTHON_AND_REVIEWED_NATIVE'),
            'unknown runtime qualification')
    if value['qualification'] == 'PYTHON_AND_REVIEWED_NATIVE':
        digest(value['native_profile_sha256'])
        require(all(native[name] is not None for name in ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo'))
                and bool(native['traineddata']) and bool(native['linked_libraries']) and 'eng' in native['languages'], 'native qualification incomplete')
    else:
        require(value['native_profile_sha256'] is None, 'unqualified native profile identity')
    return value


def acquire(lock_path, wheelhouse):
    """Download only sealed official wheel URLs: 64MiB/file, 256MiB/300s total.

    No ambient proxies, redirects, sdists or resolver. Partial acquisitions remain
    explicitly incomplete and cannot pass wheels_verified or be installed.
    """
    import hashlib
    import time
    import urllib.request
    lock = load_lock(lock_path)
    wheelhouse = Path(wheelhouse).absolute()
    require(not wheelhouse.exists(), 'fresh wheelhouse required')
    for path in [wheelhouse, *wheelhouse.parents]:
        require(not path.is_symlink(), 'wheelhouse symlink')
    require(not wheelhouse.is_relative_to(ROOT), 'wheelhouse must be external to source')
    wheelhouse.mkdir(mode=0o700)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + 300
    total = 0
    for row in lock['packages']:
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'acquisition wall ceiling')
        h, size = hashlib.sha256(), 0
        path = wheelhouse / row['filename']
        with opener.open(row['url'], timeout=min(20, remaining)) as response, path.open('xb') as output:
            require(response.status == 200 and response.url == row['url'], 'unexpected wheel response')
            while True:
                require(time.monotonic() < deadline, 'acquisition wall ceiling')
                block = response.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                total += len(block)
                require(size <= 64 * 1024**2 and total <= 256 * 1024**2, 'wheel byte ceiling')
                output.write(block)
                h.update(block)
        require(h.hexdigest() == row['sha256'], 'acquired wheel hash differs')
    return wheels_verified(lock, wheelhouse)


def install(lock_path, wheelhouse, destination):
    lock = load_lock(lock_path)
    target_verified(lock)
    wheels_verified(lock, wheelhouse)
    destination = Path(destination).absolute()
    require('..' not in destination.parts, 'venv destination traversal')
    for parent in [destination, *destination.parents]:
        require(not parent.is_symlink(), 'venv destination symlink ancestor')
    require(not destination.exists(), 'fresh venv destination required')
    require(not destination.is_relative_to(ROOT), 'venv must be external to source')
    # No resolver, sdist, build backend, ambient config, index, or dependency upgrade.
    venv.EnvBuilder(with_pip=True).create(destination)
    python = destination / 'bin/python'
    pins = destination / 'requirements.lock'
    pins.write_text('\n'.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}"
                              for r in lock['packages']) + '\n')
    installer = next(row for row in lock['packages'] if row['name'] == 'pip')
    bootstrap = destination / 'pip-bootstrap.lock'
    bootstrap.write_text(f"pip=={installer['version']} --hash=sha256:{installer['sha256']}\n")
    base = [str(python), '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--no-index', '--no-cache-dir', '--no-compile', '--only-binary=:all:', '--no-deps',
            '--require-hashes', '--find-links', str(Path(wheelhouse).resolve())]
    subprocess.run([*base, '-r', str(bootstrap)], check=True, env=environment(), timeout=90)
    # Reinstall pip itself using the locked installer, so every generated entry
    # wrapper uses the reviewed pip template rather than ensurepip's bootstrap.
    subprocess.run([*base, '--force-reinstall', '-r', str(pins)],
                   check=True, env=environment(), timeout=300)
    # ensurepip may add setuptools; exact verification refuses any extra distribution.
    subprocess.run([str(python), '-B', str(Path(__file__).resolve()), 'verify',
                    '--lock', str(Path(lock_path).resolve())], check=True, env=environment(), timeout=120)
    return str(python)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('acquire', 'wheels', 'install', 'verify'))
    parser.add_argument('--lock', type=Path, default=LOCK)
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--venv', type=Path)
    parser.add_argument('--native-profile', type=Path)
    args = parser.parse_args()
    if args.action == 'acquire':
        print(acquire(args.lock, args.wheelhouse))
    elif args.action == 'install':
        print(install(args.lock, args.wheelhouse, args.venv))
    elif args.action == 'wheels':
        print(wheels_verified(load_lock(args.lock), args.wheelhouse))
    else:
        import json
        print(json.dumps(verify(args.lock, args.native_profile), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

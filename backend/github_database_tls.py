"""Default-off, credential-free TLS policy for the existing GitHub DB jobs."""
import hashlib
import os
from pathlib import Path
import stat

FLAG = 'AUDIT_GITHUB_DATABASE_TLS'
CA = Path(__file__).resolve().parents[1]/'scripts/verification/supabase-project-ca.crt'
SYSTEM_CA = Path('/etc/ssl/certs/ca-certificates.crt')
CA_HASH = '700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7'
BUNDLE_NAME = 'audit-github-database-roots.crt'


def read_bounded(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit+1)
    if not 0 < len(data) <= limit:
        raise RuntimeError('GITHUB_DATABASE_CA_REFUSED')
    return data


def bundle_bytes():
    ca = read_bounded(CA, 4096)
    if len(ca) != 1367 or hashlib.sha256(ca).hexdigest() != CA_HASH:
        raise RuntimeError('GITHUB_DATABASE_CA_REFUSED')
    return read_bounded(SYSTEM_CA, 1024*1024)+b'\n'+ca


def owned_regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o022):
        raise RuntimeError('GITHUB_DATABASE_FILE_REFUSED')


def prepare():
    """Write public roots/settings only, never a URL, password or token."""
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get(FLAG) != '1':
        raise RuntimeError('GITHUB_DATABASE_POLICY_REFUSED')
    root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    envfile = Path(os.environ['GITHUB_ENV'])
    if (envfile.is_symlink() or not envfile.resolve().is_relative_to(root)
            or any(ord(c) < 32 for c in str(root))):
        raise RuntimeError('GITHUB_DATABASE_FILE_REFUSED')
    owned_regular(envfile)
    path = root/BUNDLE_NAME
    data = bundle_bytes()
    try:
        descriptor = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    except FileExistsError:
        owned_regular(path)
        if read_bounded(path, 1024*1024+4097) != data:
            raise RuntimeError('GITHUB_DATABASE_CA_REFUSED') from None
    else:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    with envfile.open('a', encoding='utf-8') as stream:
        stream.write('PGSSLROOTCERT='+str(path)+'\n')


def connection_args():
    enabled = os.environ.get(FLAG)
    if enabled is None:
        return {}
    if enabled != '1' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('GITHUB_DATABASE_POLICY_REFUSED')
    path = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)/BUNDLE_NAME
    if os.environ.get('PGSSLROOTCERT') != str(path):
        raise RuntimeError('GITHUB_DATABASE_CA_REFUSED')
    owned_regular(path)
    if read_bounded(path, 1024*1024+4097) != bundle_bytes():
        raise RuntimeError('GITHUB_DATABASE_CA_REFUSED')
    # SQLAlchemy merges these after URI query options, so even ?sslmode=require
    # cannot weaken the actual native/bootstrap/validation writing transport.
    return {'sslmode':'verify-full', 'sslrootcert':str(path),
            'gssencmode':'disable', 'hostaddr':''}

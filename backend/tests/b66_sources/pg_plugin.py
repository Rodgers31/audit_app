"""Lane-owned, constrained session fixture; never imports a production env file.

Opt in with -p b66_sources.pg_plugin. Reuses one owned container for legacy and
new source tests; each test module still owns its isolated case databases.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

IMAGE = 'public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
PORT = 56973
DATABASE = 'batch9-reconciliation-batch11-602-template'
RESOURCE = None
PLUGIN_ENABLED = False


def command_environment(url=None):
    env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
           'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    if url: env['DATABASE_URL'] = url
    return env


def docker(*args):
    return subprocess.check_output(['docker', *args], env=command_environment(), text=True, timeout=45).strip()


@contextmanager
def resource(output=None):
    from sqlalchemy import create_engine, text
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', PORT))
    name = 'b66-sources-' + uuid4().hex
    volume = name + '-data'
    base = os.environ.get('B66_SOURCE_EVIDENCE') or output
    if base is None: raise RuntimeError('Owned resource evidence directory required')
    out = Path(base) / name
    out.mkdir(parents=True, exist_ok=False)
    url = f'postgresql+psycopg2://batch11_602:inert-owned-602@127.0.0.1:{PORT}/{DATABASE}'
    record = {'generated_by': str(Path(__file__).resolve()), 'generator_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'generated_at': datetime.now(timezone.utc).isoformat(), 'container': name, 'volume': volume, 'port': PORT,
              'image': IMAGE, 'memory_bytes': 512*1024*1024, 'cpus': .5}
    has_volume = has_container = False
    try:
        docker('image', 'inspect', IMAGE)
        record['image_id'] = docker('image','inspect',IMAGE,'--format','{{.Id}}')
        docker('volume', 'create', '--label', 'audit.b66.lane=sources', volume); has_volume = True
        docker('run','-d','--name',name,'--label','audit.b66.lane=sources','--memory','512m','--cpus','0.5',
               '-p',f'127.0.0.1:{PORT}:5432','-v',volume+':/var/lib/postgresql/data',
               '-e','POSTGRES_USER=batch11_602','-e','POSTGRES_PASSWORD=inert-owned-602','-e','POSTGRES_DB='+DATABASE,IMAGE)
        has_container = True
        engine = create_engine(url)
        try:
            end = time.monotonic()+30
            while True:
                try:
                    with engine.connect() as c:
                        identity = tuple(c.execute(text('SELECT current_database(),current_user,version()')).one())
                    break
                except Exception:
                    if time.monotonic() > end: raise
                    time.sleep(.1)
            if identity[:2] != (DATABASE, 'batch11_602'): raise RuntimeError('Owned database identity mismatch')
            record['identity'] = identity
        finally: engine.dispose()
        backend = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable,'-m','alembic','upgrade','head'], cwd=backend,
            env=command_environment(url), capture_output=True, text=True, timeout=90)
        (out/'migration.log').write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError('Owned migration failed: '+result.stderr)
        yield url
    finally:
        if has_container: docker('rm','-f',name)
        if has_volume: docker('volume','rm',volume)
        if docker('ps','-aq','--filter','name=^/'+name+'$') or docker('volume','ls','-q','--filter','name=^'+volume+'$'):
            raise RuntimeError('Owned resource cleanup failed')
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', PORT))
        record['cleanup_verified'] = True
        path = out/'resources.json'; path.write_text(json.dumps(record, indent=2)+'\n')
        check = json.loads(path.read_text())
        if check['generator_sha256'] != record['generator_sha256'] or check['cleanup_verified'] is not True:
            raise RuntimeError('Resource receipt readback mismatch')


@contextmanager
def shared(_output):
    global RESOURCE
    if not PLUGIN_ENABLED:
        with resource(_output) as url:
            yield url
        return
    if RESOURCE is None:
        manager = resource(_output)
        RESOURCE = (manager, manager.__enter__())
    yield RESOURCE[1]


def pytest_configure(config):
    global PLUGIN_ENABLED
    PLUGIN_ENABLED = True
    from batch11_native_sources_fixture import owned_postgres
    owned_postgres.postgres = shared


def pytest_sessionfinish(session, exitstatus):
    global RESOURCE
    if RESOURCE is not None:
        manager, _ = RESOURCE
        RESOURCE = None
        manager.__exit__(None,None,None)

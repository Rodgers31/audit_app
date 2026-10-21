"""Private copied-root boot, then exec the authentic application as outer PID1."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from isolation import post_exec, require
from bounded_profile import inert_environment

PG = '/usr/lib/postgresql/17/bin/'


def call(argv, timeout=45):
    subprocess.run(argv, stdin=subprocess.DEVNULL, check=True, timeout=timeout, close_fds=True)


def main():
    require(os.getpid() == 1, 'Actual outer PID1 required')
    print('HOST_FIXTURE_POST_EXEC ' + json.dumps(post_exec(), sort_keys=True), flush=True)
    inert_environment(dict(os.environ))
    manifest = json.loads(Path('/manifest.json').read_text())
    import hashlib
    require(manifest['files'], 'Nonempty immutable source inventory required')
    for name, sha in manifest['files'].items():
        with Path('/' + name).open('rb') as source:
            require(hashlib.file_digest(source, 'sha256').hexdigest() == sha, 'Immutable copied source changed')
            # Verification reads all tests/fixtures too. Do not retain their
            # otherwise-unused cache pages as synthetic workload overhead.
            # This advice cannot create a pass: actual cgroup limits/samples
            # still decide qualification, and app/native heaps are untouched.
            os.posix_fadvise(source.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    from custody import export
    export('manifest', Path('/manifest.json').read_bytes())
    # Alembic's reviewed configuration resolves its script directory relative
    # to the application working directory, as in the production container.
    os.chdir('/app')
    require(not Path('/state/pg').exists(), 'Fresh private PostgreSQL required')
    os.umask(0o077)
    call([PG + 'initdb', '-D', '/state/pg', '-U', 'postgres', '--auth=trust',
          '--no-locale', '--encoding=UTF8', '--wal-segsize=1'])
    with Path('/state/pg/postgresql.conf').open('a') as stream:
        stream.write("\nlisten_addresses='127.0.0.2'\nunix_socket_directories=''\n"
            "shared_buffers='8MB'\nwork_mem='1MB'\nmaintenance_work_mem='8MB'\n"
            "max_connections=12\njit=off\nautovacuum=off\n"
            "shared_preload_libraries='pg_stat_statements'\npg_stat_statements.track=all\n")
    call([PG + 'pg_ctl', '-D', '/state/pg', '-l', '/evidence/postgres.log', '-w', 'start'])
    call([PG + 'psql', '-h', '127.0.0.2', '-U', 'postgres', '-c',
        'CREATE ROLE b15_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE '
        'NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'])
    Path('/evidence/endpoint-case').write_text('capacity')
    Path('/evidence/endpoint-delay').write_text('0')
    call([sys.executable, '-B', '/host/prepare_endpoint.py'])
    children = []
    for name, argv in [('endpoint', [sys.executable, '-B', '/host/endpoint.py']),
                       ('wire', [sys.executable, '-B', '-c', 'import wire; wire.main("127.0.0.3")'])]:
        with open('/evidence/' + name + '.log', 'xb', buffering=0) as log:
            children.append(subprocess.Popen(argv,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True))
    end = time.monotonic() + 30
    while True:
        require(all(child.poll() is None for child in children), 'Private service died')
        try:
            with socket.create_connection(('127.0.0.4', 443), timeout=.2):
                pass
            with socket.create_connection(('127.0.0.3', 5432), timeout=.2):
                pass
            break
        except OSError:
            require(time.monotonic() < end, 'Private service startup deadline')
            time.sleep(.1)
    call([sys.executable, '-B', '/harness/control.py', 'init', 'b15_worker_capacity'], timeout=60)
    seeded = subprocess.check_output([sys.executable, '-B', '/harness/control.py', 'seed',
        'b15_worker_capacity', 'image'], text=True, timeout=45)
    rows = [json.loads(line[len('CONTROL_JSON:'):]) for line in seeded.splitlines()
            if line.startswith('CONTROL_JSON:')]
    require(len(rows) == 1 and rows[0]['image'] is True, 'Image-first seed required')
    Path('/evidence/image-seed.json').write_text(json.dumps(rows[0]))
    plan = [dict(target_id=rows[0]['target_id'], delay=0)]
    for delay in (0, 0, 25, 50, 75, 100, 125, 150):
        raw = subprocess.check_output([sys.executable, '-B', '/harness/control.py', 'seed',
            'b15_worker_capacity'], text=True, timeout=35)
        values = [json.loads(line[len('CONTROL_JSON:'):]) for line in raw.splitlines()
                  if line.startswith('CONTROL_JSON:')]
        require(len(values) == 1 and values[0]['image'] is False, 'One text seed required')
        plan.append(dict(target_id=values[0]['target_id'], delay=delay))
    Path('/evidence/capacity-plan.json').write_text(json.dumps(plan))
    subprocess.Popen([sys.executable, '-B', '/host/driver.py'], stdin=subprocess.DEVNULL, close_fds=True)
    print('HOST_FIXTURE_EXEC_ACTUAL_SUPERVISOR', flush=True)
    os.chdir('/app')
    os.execv(sys.executable, [sys.executable, '-B', '-m', 'social_worker_supervisor'])


if __name__ == '__main__':
    main()

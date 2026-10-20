"""Fixed, inert single-cgroup services. Executed only inside an owned fixture.

The bootstrap execs the *real* application supervisor as PID1. PostgreSQL,
TLS endpoints, wire proxy and docker-exec controllers share its hard cgroup
limits. There is no Docker socket, external network or production configuration.
"""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from bounded_profile import inert_environment

PG = '/usr/lib/postgresql/17/bin/'
DATA = '/state/pg'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def boundary():
    require(os.getpid() == 1 and os.getuid() == 10001 and os.getgid() == 10001,
            'Owned non-root container PID1 required')
    require(os.environ.get('B27_FIXTURE') == 'isolated', 'Explicit fixture required')
    require(Path('/sys/fs/cgroup/memory.max').read_text().strip() == str(512 * 1024 ** 2),
            'Aggregate memory ceiling unavailable')
    require(Path('/sys/fs/cgroup/memory.swap.max').read_text().strip() == '0',
            'Swap must be disabled')
    parts = Path('/sys/fs/cgroup/cpu.max').read_text().split()
    require(len(parts) == 2 and all(part.isascii() and part.isdecimal() for part in parts),
            'Finite positive CPU quota/period required')
    quota, period = map(int, parts)
    require(quota > 0 and period > 0, 'Positive CPU quota/period required')
    require(quota / period == .5, 'Aggregate CPU ceiling unavailable')
    require(Path('/sys/fs/cgroup/pids.max').read_text().strip() == '128',
            'Aggregate PID ceiling unavailable')
    # Docker --network=none supplies only loopback. Do not attempt any external
    # connection until the absence of all non-loopback interfaces is proven.
    interfaces = socket.if_nameindex()
    require((1, 'lo') in interfaces, 'Loopback unavailable')
    for index, name in interfaces:
        require(type(index) is int and index > 0 and re.fullmatch('[a-z0-9_]{1,15}', name), 'Interface identity invalid')
        if name != 'lo':
            # Some Docker kernels expose dormant built-in tunnel devices even
            # under network=none. They must be DOWN and cannot be activated with
            # all capabilities dropped. No live interface is admitted.
            require(int(Path('/sys/class/net', name, 'flags').read_text().strip(), 16) & 1 == 0,
                    'External interface refused')
    routes = Path('/proc/net/route').read_text().splitlines()
    require(len(routes) == 1 and routes[0].startswith('Iface'), 'External route refused')
    ipv6 = [line.split() for line in Path('/proc/net/ipv6_route').read_text().splitlines()]
    require(ipv6 and all(len(row) == 10 and row[-1] == 'lo'
            and all(re.fullmatch('[0-9a-f]+', field) for field in row[:-1]) for row in ipv6),
            'External IPv6 route refused')
    for host, expected in [('b15-worker-db', '127.0.0.2'), ('b15-worker-wire', '127.0.0.3'),
                           ('b15-worker-api', '127.0.0.1'), ('graph.facebook.com', '127.0.0.4'),
                           ('auth.fixture.test', '127.0.0.4'),
                           ('a' * 32 + '.r2.cloudflarestorage.com', '127.0.0.4')]:
        require(socket.gethostbyname_ex(host)[2] == [expected], 'Inert host mapping mismatch')
    require(os.environ.get('SOCIAL_MEDIA_ENABLED') == 'false'
            and os.environ.get('SOCIAL_MEDIA_RETAINED_WRITES_ENABLED') == 'false',
            'Uploads/retained writes must be off')
    # Even an accidental ambient key must never reach an executed fixture.
    allowed = {'PATH','LANG','LC_ALL','PYTHONUNBUFFERED','PYTHONDONTWRITEBYTECODE',
               'HOME','HOSTNAME','B27_FIXTURE','B27_MODE','B15_ENDPOINT_RUN_ID',
               'PYTHONPATH','PYTHONOPTIMIZE','PORT','WEB_CONCURRENCY','RENDER_GIT_COMMIT',
               'ENVIRONMENT','SECRET_KEY','AUTO_SEEDER_ENABLED','SUPABASE_URL',
               'SUPABASE_SERVICE_ROLE_KEY','SUPABASE_JWT_SECRET','REDIS_URL','SSL_CERT_FILE',
               'AWS_CA_BUNDLE','AWS_EC2_METADATA_DISABLED','DATABASE_URL',
               'SOCIAL_WORKER_DATABASE_URL','SOCIAL_WORKER_ROLE','SOCIAL_WORKER_DATABASE_SCHEMA',
               'SOCIAL_WORKER_SUPERVISOR_ENABLED','SOCIAL_WORKER_SHUTDOWN_SECONDS',
               'SOCIAL_NATIVE_ENABLED','SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED',
               'META_CONNECTIONS_ENABLED','META_APP_CONFIGURATION_VALIDATED','META_APP_ID',
               'META_APP_SECRET','META_ACCESS_MODE','META_REDIRECT_URIS',
               'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION','SOCIAL_CREDENTIAL_KEYS',
               'META_PRIVACY_ENABLED','META_DEAUTHORIZATION_ENABLED','META_PRIVACY_STATUS_URL',
               'META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION','META_PRIVACY_SUBJECT_KEYS',
               'SOCIAL_MEDIA_ENABLED','SOCIAL_WORKER_MEDIA_READS_ENABLED',
               'SOCIAL_MEDIA_RETAINED_WRITES_ENABLED','SOCIAL_MEDIA_R2_ENDPOINT',
               'SOCIAL_MEDIA_BUCKET','SOCIAL_MEDIA_ACCESS_KEY','SOCIAL_MEDIA_SECRET_KEY',
               'B15_REHEARSAL','B15_START_DELAY','B15_CLOSE_DELAY','B15_START_GATE',
               'B15_CLOSE_GATE','B15_RUN_GATE'}
    require(not set(os.environ) - allowed, 'Unexpected image/ambient environment refused')
    inert_environment(dict(os.environ))


def call(args, *, timeout=45):
    subprocess.run(args, stdin=subprocess.DEVNULL, check=True, timeout=timeout)


def main():
    boundary()
    os.umask(0o077)
    if not Path(DATA).exists():
        call([PG + 'initdb', '-D', DATA, '-U', 'postgres', '--auth=trust', '--no-locale', '--encoding=UTF8'])
        with Path(DATA, 'postgresql.conf').open('a') as stream:
            stream.write("\nlisten_addresses='127.0.0.2'\nunix_socket_directories='/tmp'\n"
                         "shared_buffers='8MB'\nwork_mem='1MB'\nmaintenance_work_mem='8MB'\n"
                         "max_connections=12\njit=off\nautovacuum=off\n"
                         "shared_preload_libraries='pg_stat_statements'\npg_stat_statements.track=all\n")
    call([PG + 'pg_ctl', '-D', DATA, '-l', '/evidence/postgres.log', '-w', 'start'])
    found = subprocess.check_output([PG + 'psql', '-h', '127.0.0.2', '-U', 'postgres', '-Atc',
                                    "SELECT count(*) FROM pg_roles WHERE rolname='b15_worker'"], text=True).strip()
    if found == '0':
        call([PG + 'psql', '-h', '127.0.0.2', '-U', 'postgres', '-c',
              'CREATE ROLE b15_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE '
              'NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'])
    else:
        require(found == '1', 'Fixture role census unresolved')
    children, logs = [], []
    for name, source in [('endpoint', 'import endpoints; endpoints.main("127.0.0.4", prewarm=True)'),
                         ('wire', 'import wire; wire.main("127.0.0.3")')]:
        log = open('/evidence/' + name + '.log', 'a', buffering=1)
        logs.append(log)
        children.append(subprocess.Popen([sys.executable, '-B', '-c', source],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True))
    deadline = time.monotonic() + 30
    while True:
        require(all(child.poll() is None for child in children), 'Inert service startup failed')
        try:
            with socket.create_connection(('127.0.0.4', 443), timeout=.2):
                pass
            with socket.create_connection(('127.0.0.3', 5432), timeout=.2):
                pass
            break
        except OSError:
            require(time.monotonic() < deadline, 'Inert service readiness timeout')
            time.sleep(.1)
    print('BOUNDED_FIXTURE_READY', flush=True)
    if os.environ['B27_MODE'] == 'service':
        for log in logs:
            log.close()
        os.execv(sys.executable, [sys.executable, '-B', '-m', 'social_worker_supervisor'])
    require(os.environ['B27_MODE'] == 'auxiliary', 'Fixed fixture mode required')
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        require(all(child.poll() is None for child in children), 'Inert service died')
        time.sleep(.1)
    for child in children:
        child.terminate()
        child.wait(timeout=3)
    call([PG + 'pg_ctl', '-D', DATA, '-m', 'fast', '-w', 'stop'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

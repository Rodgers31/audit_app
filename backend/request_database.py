"""Bounded serving and independent best-effort audit database profiles."""
import re
from time import monotonic

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError

if __package__:
    from .middleware.request_resources import request_deadline
else:
    from middleware.request_resources import request_deadline

STATEMENT_MS = 5000
LOCK_MS = 1000
POOL_SIZE = 5
POOL_TIMEOUT = 2
AUDIT_STATEMENT_MS = 2000
AUDIT_LOCK_MS = 500
AUDIT_POOL_SIZE = 1
AUDIT_POOL_TIMEOUT = .5
_STATE = '_request_database_transaction_limits'
_SETTINGS_CHANGE = re.compile(r'\b(?:SET|RESET|DISCARD|ROLLBACK)\b|\bset_config\s*\(', re.I)
_IDENTIFIER = r'(?:[A-Za-z_][A-Za-z0-9_$]*|"(?:[^"]|"")+")'
_CLEANUP_SQL = re.compile(
    rf'^\s*(?:ROLLBACK(?:\s+(?:WORK|TRANSACTION))?(?:\s+TO(?:\s+SAVEPOINT)?\s+{_IDENTIFIER})?'
    rf'|RELEASE(?:\s+SAVEPOINT)?\s+{_IDENTIFIER})\s*;?\s*$', re.I)
_LIMITS_SQL = "SELECT set_config('statement_timeout', CASE WHEN s.setting::bigint=0 THEN b.statement_ms ELSE LEAST(s.setting::bigint,b.statement_ms) END::text, %s), set_config('lock_timeout', CASE WHEN l.setting::bigint=0 THEN b.lock_ms ELSE LEAST(l.setting::bigint,b.lock_ms) END::text, %s), CASE WHEN s.setting::bigint=0 THEN b.statement_ms ELSE LEAST(s.setting::bigint,b.statement_ms) END, CASE WHEN l.setting::bigint=0 THEN b.lock_ms ELSE LEAST(l.setting::bigint,b.lock_ms) END FROM pg_settings s CROSS JOIN pg_settings l CROSS JOIN (SELECT %s::bigint AS statement_ms, %s::bigint AS lock_ms) b WHERE s.name='statement_timeout' AND l.name='lock_timeout'"
_PING_SQL = 'BEGIN READ ONLY; ' + _LIMITS_SQL + '; SELECT 1; ROLLBACK'


def _create_engine(url, connect_args, *, pool_size, pool_timeout, statement_ms, lock_ms, use_deadline, isolation_level=None):
    args = dict(connect_args)
    postgres = make_url(url).get_backend_name() == 'postgresql'
    if postgres:
        args.update(connect_timeout=3, keepalives=1, keepalives_idle=5,
                    keepalives_interval=1, keepalives_count=2, tcp_user_timeout=5000)
    isolation = {} if isolation_level is None else {'isolation_level': isolation_level}
    engine = create_engine(url, **isolation, pool_size=pool_size, max_overflow=0,
        pool_timeout=pool_timeout, pool_recycle=300, pool_pre_ping=True,
        connect_args=args)
    if not postgres:
        return engine

    def budgets():
        deadline = request_deadline.get() if use_deadline else None
        remaining = statement_ms if deadline is None else int((deadline - monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Request database time budget exceeded')
        return min(statement_ms, remaining), min(lock_ms, remaining)

    def bounded_ping(dbapi):
        # Transaction poolers do not retain backend affinity across commits.
        # Pin every ping control to one short read-only transaction, then leave
        # the connection idle for the application's SET TRANSACTION preamble.
        ping_statement, ping_lock = budgets()
        previous = dbapi.autocommit
        dbapi.autocommit = True
        try:
            with dbapi.cursor() as cursor:
                try:
                    # Constant SQL and validated integer budgets: one physical
                    # round trip, retaining transaction-pooler backend affinity.
                    cursor.execute(_PING_SQL, (True, True, ping_statement, ping_lock))
                    from psycopg2.extensions import TRANSACTION_STATUS_IDLE
                    if dbapi.get_transaction_status() == TRANSACTION_STATUS_IDLE:
                        return True
                    cursor.execute('ROLLBACK')
                    return False
                except BaseException:
                    try:
                        cursor.execute('ROLLBACK')
                    except engine.dialect.loaded_dbapi.Error:
                        pass  # A disconnected socket will be discarded by the pool.
                    raise
        finally:
            dbapi.autocommit = previous
    # Dialect instances belong to an engine; never alter the shared DBAPI or
    # the bootstrap/worker engine's ping implementation.
    engine.dialect.do_ping = bounded_ping

    def clear_transaction(connection, *args):
        # Do not touch Connection.info here: on a disconnect it can attempt a
        # new checkout while rollback is still resolving the failed transaction.
        connection.__dict__.pop(_STATE, None)
    event.listen(engine, 'commit', clear_transaction)
    event.listen(engine, 'rollback', clear_transaction)

    @event.listens_for(engine, 'after_cursor_execute')
    def changed_settings(connection, cursor, statement, parameters, context, executemany):
        if _SETTINGS_CHANGE.search(statement):
            clear_transaction(connection)

    @event.listens_for(engine, 'before_cursor_execute')
    def request_limits(connection, cursor, statement, parameters, context, executemany):
        # An aborted savepoint permits only recovery SQL. Neither a settings
        # query nor an expired application deadline may prevent that cleanup.
        # Match one complete control statement; work after a semicolon does
        # not get this exception. The next work statement rechecks its budget.
        if _CLEANUP_SQL.fullmatch(statement):
            clear_transaction(connection)
            return
        wanted_statement, wanted_lock = budgets()
        # The committed reader declaration remains the first statement in its
        # transaction. The separate ping transaction is already rolled back.
        if statement.lstrip().upper().startswith('SET TRANSACTION '):
            return
        installed = getattr(connection, _STATE, None)
        transaction = connection.get_transaction()
        if (installed is not None and installed[0] is transaction
                and wanted_statement >= installed[1] and wanted_lock >= installed[2]):
            return
        # One settings RPC per transaction, and again only after an explicit
        # settings change or when the final remaining deadline needs tightening.
        cursor.execute(_LIMITS_SQL, (True, True, wanted_statement, wanted_lock))
        actual_statement, actual_lock = (int(value) for value in cursor.fetchone()[2:])
        setattr(connection, _STATE, (transaction, actual_statement, actual_lock))
    return engine


def create_request_engine(url, connect_args):
    """API pool; the bootstrap/seeding/worker SessionLocal stays unchanged."""
    return _create_engine(url, connect_args, pool_size=POOL_SIZE,
        pool_timeout=POOL_TIMEOUT, statement_ms=STATEMENT_MS, lock_ms=LOCK_MS,
        use_deadline=True)


def create_audit_engine(url, connect_args):
    """One independent HTTP audit slot; failure still follows recorder policy."""
    return _create_engine(url, connect_args, pool_size=AUDIT_POOL_SIZE,
        pool_timeout=AUDIT_POOL_TIMEOUT, statement_ms=AUDIT_STATEMENT_MS,
        lock_ms=AUDIT_LOCK_MS, use_deadline=False)


def install_database_exception_handlers(app):
    """Expose exhausted DB admission as retryable, including legacy wrappers."""
    from fastapi.exception_handlers import http_exception_handler
    from starlette.exceptions import HTTPException
    from starlette.responses import JSONResponse

    def admission_failure(error):
        pending, seen = [error], set()
        while pending and len(seen) < 16:
            value = pending.pop()
            if id(value) in seen:
                continue
            seen.add(id(value))
            if isinstance(value, TimeoutError):
                return True
            pending.extend(item for item in (value.__cause__, value.__context__) if item is not None)
        return False

    def unavailable():
        return JSONResponse({'detail': 'Database request capacity unavailable'}, status_code=503,
            headers={'Retry-After': '1', 'Cache-Control': 'no-store'})

    async def timeout_handler(request, error):
        return unavailable()

    async def http_handler(request, error):
        if error.status_code >= 500 and admission_failure(error):
            return unavailable()
        return await http_exception_handler(request, error)

    app.add_exception_handler(TimeoutError, timeout_handler)
    app.add_exception_handler(HTTPException, http_handler)

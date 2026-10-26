"""Serving-only database pool and transaction budgets; no seeding profile change."""
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


def create_request_engine(url, connect_args):
    """A distinct bounded pool; existing engine/SessionLocal keep their contract."""
    args = dict(connect_args)
    postgres = make_url(url).get_backend_name() == 'postgresql'
    if postgres:
        args.update(connect_timeout=3, keepalives=1, keepalives_idle=5,
                    keepalives_interval=1, keepalives_count=2, tcp_user_timeout=5000)
    engine = create_engine(url, pool_size=POOL_SIZE, max_overflow=0,
        pool_timeout=POOL_TIMEOUT, pool_recycle=300, pool_pre_ping=False,
        connect_args=args)

    @event.listens_for(engine, 'before_cursor_execute')
    def request_limits(connection, cursor, statement, parameters, context, executemany):
        if not postgres:
            return
        # Fresh committed readers must issue SET TRANSACTION before any query.
        # Do not start a transaction from get_db or before that declaration.
        if statement.lstrip().upper().startswith('SET TRANSACTION '):
            return
        deadline = request_deadline.get()
        remaining = STATEMENT_MS if deadline is None else int((deadline - monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Request database time budget exceeded')
        # Direct DBAPI execution avoids event recursion. Local settings survive
        # this transaction only, including through a transaction pooler.
        cursor.execute("SELECT set_config('statement_timeout', CASE WHEN s.setting::bigint=0 THEN b.statement_ms ELSE LEAST(s.setting::bigint,b.statement_ms) END::text, true), set_config('lock_timeout', CASE WHEN l.setting::bigint=0 THEN b.lock_ms ELSE LEAST(l.setting::bigint,b.lock_ms) END::text, true) FROM pg_settings s CROSS JOIN pg_settings l CROSS JOIN (SELECT %s::bigint AS statement_ms, %s::bigint AS lock_ms) b WHERE s.name='statement_timeout' AND l.name='lock_timeout'",
                       (str(min(STATEMENT_MS, remaining)), str(min(LOCK_MS, remaining))))
    return engine

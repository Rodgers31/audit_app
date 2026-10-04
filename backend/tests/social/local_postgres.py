"""Test-only assigned PostgreSQL targets; never permit libpq redirection."""
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


ASSIGNED_DATABASES = frozenset({
    'social_domain_test', 'social_worker_test', 'auditgava_social_test',
})


def local_postgres_url(value, database):
    message = 'Use only the assigned loopback test database on port 62124 without connection query options'
    # make_url drops blank query values, so inspect raw syntax as well. A
    # literal question mark in a password must be percent-encoded in this DSN.
    if not isinstance(value, str) or '?' in value or database not in ASSIGNED_DATABASES:
        raise ValueError(message)
    try:
        url = make_url(value)
        valid = (
            url.drivername in {'postgresql', 'postgresql+psycopg2'}
            and url.host in {'localhost', '127.0.0.1', '::1'}
            and url.port == 62124 and url.database == database and not url.query
        )
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(message) from None
    if not valid:
        raise ValueError(message)
    # Explicit libpq hostaddr also defeats a remote PGHOSTADDR default. No
    # caller-supplied service, host list, database or driver option survives.
    return url.set(drivername='postgresql+psycopg2', host='127.0.0.1',
                   query={'hostaddr': '127.0.0.1'})

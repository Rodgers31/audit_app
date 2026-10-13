"""Independent cleanup of exactly registered owned epoch fixture resources."""
import json
import re
import sys

from sqlalchemy import text


def database_identity(connection, name):
    row=connection.execute(text("""SELECT oid,pg_get_userbyid(datdba),
        (SELECT system_identifier::text FROM pg_control_system())
        FROM pg_database WHERE datname=:name"""),{'name':name}).one_or_none()
    if row is None:return None
    value=tuple(row)
    if (len(value)!=3 or type(value[0]) is not int or not 0<value[0]<2**32
            or value[1]!='inert' or type(value[2]) is not str or not value[2].isascii()
            or not value[2].isdigit() or not 0<int(value[2])<2**64):
        raise RuntimeError('Owned audit database identity unavailable')
    return value


def role_identity(connection, name):
    row=connection.execute(text('SELECT oid,rolsuper,rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=:name'),{'name':name}).one_or_none()
    if row is None:return None
    value=tuple(row)
    if (len(value)!=4 or type(value[0]) is not int or value[0]<=0
            or value[1] is not False or value[2] is not False or value[3] is not True):
        raise RuntimeError('Owned audit role identity unavailable')
    return value


def cleanup_owned(admin, engines, name, created, expected_database, registered_roles):
    primary=sys.exception()
    errors=[]
    attempts=[]
    def attempt(label, action):
        try:
            action();attempts.append({'resource':label,'verified':True})
        except BaseException as error:
            errors.append(error);attempts.append({'resource':label,'verified':False,'error_type':type(error).__name__})
    def bind(c):
        u=admin.url
        if (u.drivername!='postgresql+psycopg2' or u.host!='127.0.0.1'
                or u.port not in (55534,55545) or u.username!='inert' or u.password!='inert'
                or u.database!='issue611' or u.query
                or tuple(c.execute(text('SELECT current_database(),current_user')).one())!=('issue611','inert')):
            raise RuntimeError('Owned audit control connection mismatch')
        cluster=c.scalar(text('SELECT system_identifier::text FROM pg_control_system()'))
        if (expected_database is None or type(cluster) is not str
                or cluster!=expected_database[2]):
            raise RuntimeError('Owned audit control cluster identity changed')
    def drop_database():
        if not re.fullmatch(r'batch12_audit_(?:storage|browser)_[0-9a-f]{32}',name):
            raise RuntimeError('Owned audit database registration mismatch')
        if not created:return
        if expected_database is None:raise RuntimeError('Owned audit CREATE outcome unverified')
        with admin.connect() as c:
            bind(c);actual=database_identity(c,name)
            if actual is not None:
                if actual!=expected_database:raise RuntimeError('Owned audit database identity changed')
                c.execute(text(f'DROP DATABASE "{name}"'))
            if database_identity(c,name) is not None:raise RuntimeError('Owned audit database remains')
    def drop_role(role,expected):
        if role not in (name+'_r',name+'_w') or expected is None:
            raise RuntimeError('Owned audit role registration unverified')
        with admin.connect() as c:
            bind(c);actual=role_identity(c,role)
            if actual is not None:
                if actual!=expected:raise RuntimeError('Owned audit role identity changed')
                c.execute(text(f'DROP ROLE "{role}"'))
            if role_identity(c,role) is not None:raise RuntimeError('Owned audit role remains')
    try:
        for index,engine in enumerate(engines):
            if engine is not None:attempt('engine_'+str(index),engine.dispose)
        attempt(name,drop_database)
        for role,expected in registered_roles.items():
            attempt(role,lambda role=role,expected=expected:drop_role(role,expected))
    finally:
        attempt('control_engine',admin.dispose)
    print('AUDIT_OWNED_CLEANUP '+json.dumps({'cleanup':not errors,'attempts':attempts}),flush=True)
    if errors:
        cleanup=BaseExceptionGroup('Owned audit cleanup remains unverified',errors)
        if primary is not None:
            raise BaseExceptionGroup('Owned audit execution and cleanup failed',[primary,cleanup])
        raise cleanup

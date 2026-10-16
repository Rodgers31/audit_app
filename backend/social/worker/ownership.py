"""Sticky whole-budget authority. Time never grants a successor permission."""
from dataclasses import dataclass
import os
import weakref
import threading
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


class AuthorityLost(RuntimeError):
    pass


_issued = weakref.WeakValueDictionary()
_bound = weakref.WeakValueDictionary()
_registry_lock = threading.Lock()


def _locally_issued(authority):
    return _issued.get((os.getpid(), id(authority))) is authority


def bind_runtime(authority, runtime):
    if not _locally_issued(authority):
        raise AuthorityLost('GLOBAL_WORKER_RUNTIME_ALREADY_BOUND')
    with _registry_lock:
        if id(authority) in _bound:
            raise AuthorityLost('GLOBAL_WORKER_RUNTIME_ALREADY_BOUND')
        _bound[id(authority)] = runtime


def unbind_runtime(authority, runtime):
    with _registry_lock:
        if _bound.get(id(authority)) is runtime:
            del _bound[id(authority)]


@dataclass(frozen=True)
class RuntimeAuthority:
    owner_id: UUID
    generation: int

    def __post_init__(self):
        if type(self.owner_id) is not UUID or type(self.generation) is not int or self.generation < 1:
            raise ValueError('Explicit worker owner and positive generation required')


def check_authority(conn, authority, *, owner_id=None, require_local=True):
    """First lock in every admission transaction; never hold across provider IO."""
    row = conn.execute(text('SELECT owner_id,generation FROM social_worker_runtime_ownership WHERE id=1 FOR UPDATE')).one_or_none()
    if (type(authority) is not RuntimeAuthority or (require_local and not _locally_issued(authority))
            or (owner_id is not None and str(authority.owner_id) != str(owner_id))):
        raise AuthorityLost('GLOBAL_WORKER_AUTHORITY_REQUIRED')
    if row is None or (str(row.owner_id), row.generation) != (str(authority.owner_id), authority.generation):
        raise AuthorityLost('GLOBAL_WORKER_AUTHORITY_LOST')


def acquire_authority(engine, owner_id, deployment_version):
    if type(owner_id) is not UUID or type(deployment_version) is not str or not 1 <= len(deployment_version) <= 128:
        raise ValueError('Explicit bounded worker identity required')
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout='2s'"))
            conn.execute(text("SET LOCAL statement_timeout='5s'"))
            conn.execute(text('SELECT id FROM social_worker_runtime_ownership LIMIT 0'))
            valid = conn.execute(text('''SELECT
                EXISTS(SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid
                    AND a.attname='id' WHERE i.indrelid='social_worker_runtime_ownership'::regclass
                    AND i.indisprimary AND i.indisunique AND i.indisvalid AND i.indisready
                    AND i.indpred IS NULL AND i.indnkeyatts=1 AND i.indkey[0]=a.attnum)
                AND EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='social_worker_runtime_ownership'::regclass
                    AND contype='c' AND convalidated AND pg_get_constraintdef(oid)='CHECK ((id = 1))')
                AND NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.oid='social_worker_runtime_ownership'::regclass AND n.nspname LIKE 'pg_temp_%')
                AND (SELECT count(*) FROM pg_trigger WHERE tgrelid='social_worker_runtime_ownership'::regclass
                    AND tgname IN ('social_worker_owner_guard','social_worker_owner_acquired')
                    AND tgenabled IN ('O','A') AND NOT tgisinternal)=2
            ''')).scalar_one()
            if valid is not True:
                raise AuthorityLost('GLOBAL_WORKER_SCHEMA_UNAVAILABLE')
            # Trigger validates the monotonic generation and atomically records
            # acquisition. A concurrent insert loses the singleton PK race.
            generation = conn.execute(text('''
                INSERT INTO social_worker_runtime_ownership(id,owner_id,generation,deployment_version)
                SELECT 1,CAST(:owner AS uuid),COALESCE(MAX(generation),0)+1,:version
                FROM social_worker_runtime_history RETURNING generation
            '''), {'owner': str(owner_id), 'version': deployment_version}).scalar_one()
            conn.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            stored = conn.execute(text('''SELECT
                o.owner_id=CAST(:owner AS uuid) AND o.generation=:generation
                AND o.deployment_version=:version AND h.owner_id=o.owner_id
                AND h.deployment_version=o.deployment_version AND h.proof='{}'::jsonb
                FROM social_worker_runtime_ownership o JOIN social_worker_runtime_history h
                  ON h.generation=o.generation AND h.event='acquired' WHERE o.id=1
            '''), {'owner':str(owner_id),'generation':generation,'version':deployment_version}).scalar_one_or_none()
            if stored is not True:
                raise AuthorityLost('GLOBAL_WORKER_ACQUISITION_UNVERIFIED')
        authority = RuntimeAuthority(owner_id, generation)
        _issued[(os.getpid(), id(authority))] = authority
        return authority
    except IntegrityError:
        raise AuthorityLost('GLOBAL_WORKER_OWNED') from None


def release_authority(engine, authority, proof):
    """Privileged operator only; receipt is positive evidence, never a timeout.

    The operator must authenticate receipt custody to the exact old launcher.
    A database cannot independently prove a remote host or provider is closed.
    This API deliberately offers no force/expiry path.
    """
    required = {'version', 'owner_id', 'generation', 'process_joined', 'worker_exit_code',
                'providers_closed', 'executor_closed', 'claims_drained'}
    if (type(authority) is not RuntimeAuthority or type(proof) is not dict or set(proof) != required
            or type(proof['version']) is not int or proof['version'] != 1
            or proof['owner_id'] != str(authority.owner_id)
            or type(proof['generation']) is not int or proof['generation'] != authority.generation
            or type(proof['worker_exit_code']) is not int or proof['worker_exit_code'] != 0
            or any(proof[key] is not True for key in ('process_joined', 'providers_closed', 'executor_closed', 'claims_drained'))):
        raise AuthorityLost('GLOBAL_WORKER_RELEASE_PROOF_REQUIRED')
    import json
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout='2s'"))
        conn.execute(text("SET LOCAL statement_timeout='5s'"))
        check_authority(conn, authority, require_local=False)
        # Global lock excludes all new claims/intents. Locks also exclude
        # operator queue changes while checking the no-unknown-work condition.
        conn.execute(text('LOCK TABLE social_post_targets,social_accounts,social_publish_attempts IN SHARE MODE'))
        unresolved = conn.execute(text('''SELECT
            EXISTS(SELECT 1 FROM social_post_targets WHERE lease_token IS NOT NULL
                OR state IN ('claimed','dispatching','processing','reconciling','outcome_unknown'))
            OR EXISTS(SELECT 1 FROM social_accounts WHERE hold_reason IS NOT NULL OR publish_lease_token IS NOT NULL)
            OR EXISTS(SELECT 1 FROM social_publish_attempts WHERE completed_at IS NULL)
        ''')).scalar_one()
        if unresolved:
            raise AuthorityLost('GLOBAL_WORKER_UNRESOLVED_WORK')
        conn.execute(text('''INSERT INTO social_worker_runtime_history
            (generation,event,owner_id,deployment_version,proof)
            SELECT generation,'released',owner_id,deployment_version,CAST(:proof AS jsonb)
            FROM social_worker_runtime_ownership WHERE id=1'''), {'proof': json.dumps(proof, allow_nan=False)})
        if conn.execute(text('DELETE FROM social_worker_runtime_ownership WHERE id=1')).rowcount != 1:
            raise AuthorityLost('GLOBAL_WORKER_RELEASE_FAILED')

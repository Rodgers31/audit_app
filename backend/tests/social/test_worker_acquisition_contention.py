"""Force the real BEFORE-trigger snapshot race; no providers or resident workers."""
from concurrent.futures import ThreadPoolExecutor
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from social.worker.ownership import AuthorityLost, acquire_authority
from worker_ownership_support import role_database


def test_stale_insert_generation_refuses_existing_owner_without_retry(role_database):
    owner, _, schema, _ = role_database
    loser = uuid4()
    key = int(uuid4().hex[:7], 16)
    # The first INSERT takes its statement snapshot before this test-only
    # trigger blocks. A second INSERT commits generation one, then the real
    # volatile guard sees that history while the first still proposes one.
    with owner.begin() as conn:
        conn.exec_driver_sql(f'''CREATE FUNCTION {schema}.acquisition_barrier()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.owner_id='{loser}'::uuid THEN
                PERFORM pg_advisory_xact_lock({key},1);
            END IF; RETURN NEW; END $$''')
        conn.exec_driver_sql(f'''CREATE TRIGGER aa_acquisition_barrier
            BEFORE INSERT ON {schema}.social_worker_runtime_ownership
            FOR EACH ROW EXECUTE FUNCTION {schema}.acquisition_barrier()''')
    barrier = create_engine(owner.url, pool_size=1, max_overflow=0)
    try:
        with barrier.connect() as control, ThreadPoolExecutor(max_workers=1) as pool:
            control.execute(text('SELECT pg_advisory_lock(:key,1)'), {'key': key})
            control.commit()
            future = pool.submit(acquire_authority, owner, loser, 'losing-contender')
            try:
                deadline = time.monotonic() + 5
                while True:
                    waiting = control.execute(text('''SELECT EXISTS(SELECT 1 FROM pg_locks
                        WHERE locktype='advisory' AND classid=:key AND objid=1
                        AND NOT granted)'''), {'key': key}).scalar_one()
                    if waiting:
                        break
                    if time.monotonic() >= deadline:
                        pytest.fail('Contender did not reach the actual PostgreSQL barrier')
                    time.sleep(.01)
                winner = acquire_authority(owner, uuid4(), 'winning-contender')
            finally:
                control.execute(text('SELECT pg_advisory_unlock(:key,1)'), {'key': key})
                control.commit()
            with pytest.raises(AuthorityLost, match='^GLOBAL_WORKER_OWNED$'):
                future.result(timeout=8)
        with owner.connect() as conn:
            assert conn.execute(text('SELECT owner_id,generation FROM social_worker_runtime_ownership')).one() == (winner.owner_id, 1)
            assert conn.execute(text("SELECT generation,event,owner_id FROM social_worker_runtime_history")).all() == [(1, 'acquired', winner.owner_id)]
    finally:
        barrier.dispose()


@pytest.mark.parametrize('message,sqlstate', [
    ('Global worker generation mismatch', 'P0001'),
    ('Different guard refusal', 'P0001'),
    ('Global worker generation mismatch', '22023'),
])
def test_trigger_diagnostic_without_durable_owner_is_not_ownership(role_database, message, sqlstate):
    owner, _, schema, _ = role_database
    with owner.begin() as conn:
        conn.exec_driver_sql(f'''CREATE FUNCTION {schema}.acquisition_refusal()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION '{message}' USING ERRCODE='{sqlstate}'; END $$''')
        conn.exec_driver_sql(f'''CREATE TRIGGER aa_acquisition_refusal
            BEFORE INSERT ON {schema}.social_worker_runtime_ownership
            FOR EACH ROW EXECUTE FUNCTION {schema}.acquisition_refusal()''')
    with pytest.raises(DBAPIError) as error:
        acquire_authority(owner, uuid4(), 'refused-contender')
    assert error.value.orig.pgcode == sqlstate
    with owner.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_ownership')).scalar_one() == 0
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() == 0

"""Real public executor; operation deadline begins after owned app startup."""
import base64
import json
import os
from pathlib import Path
import signal
import sys
import time
from uuid import UUID

settings = json.loads(sys.stdin.buffer.read())
sys.path.insert(0, settings['app_root'])
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from social.connections import verification_execution as execution
from social.connections.config import MetaConfig
from social.connections.service import ConnectionService
from social.connections.verification import SavedGrantVerificationAuthority
from middleware.request_resources import request_deadline

execution.ENTRYPOINT = Path(settings['entrypoint'])
directory = execution.ENTRYPOINT.parent
def publish(name, value):
    temporary = directory / (name + '.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(directory / name)

config = MetaConfig(enabled=True, app_configuration_validated=True, app_id='123',
    app_secret='inert-fixture-material', access_mode='owned_standard',
    redirect_uris=('https://example.test/admin/social/accounts/callback',), active_key_version='v1',
    encryption_keys={'v1': base64.urlsafe_b64encode(b'x' * 32).decode()})
engine = create_engine('postgresql+psycopg2://fixture@127.0.0.1:9/fixture')
db = Session(engine)
service = ConnectionService(db, config, verification_authority=SavedGrantVerificationAuthority(config))
original = execution.subprocess.Popen
def spawn(*args, **kwargs):
    child = original(*args, **kwargs)
    publish('spawn.json', {'pid': child.pid,
        'pgid': child.pid, 'parent': os.getpid()})
    if settings['phase'] == 'input':
        os.kill(os.getpid(), signal.SIGSTOP)
    return child
execution.subprocess.Popen = spawn
deadline = time.monotonic() + settings['seconds']
publish('ready.json', {'deadline': deadline, 'parent': os.getpid()})
token = request_deadline.set(deadline + execution.CLEANUP_SECONDS)
try:
    account = UUID('22222222-2222-4222-8222-222222222222')
    service.verify_existing_grant(account, UUID('11111111-1111-4111-8111-111111111111'), 'c' * 64,
        f'POST /api/v1/admin/social/accounts/{account}/verify-publishing-access',
        UUID('33333333-3333-4333-8333-333333333333'),
        {'expected_controls_version': 1, 'expected_state': 'a' * 64, 'reason': 'Owned API lifecycle boundary'},
        UUID('44444444-4444-4444-8444-444444444444'))
finally:
    request_deadline.reset(token)
    db.close()
    engine.dispose()

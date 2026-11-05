"""Fixed private entrypoint for one saved-grant command; no command-line data."""
from pathlib import Path
import os
import sys

# Isolated interpreter imports only the installed application tree. No caller
# path, module, transport, test mode or executable is accepted by the protocol.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def arm_lifecycle(value):
    """Linux kernel guards survive loss or suspension of the API supervisor.

    Install after exec, never in a threaded parent's preexec_fn. Validate the
    parent's captured identity both before and after installing SIGKILL so an
    already adopted child cannot bind itself to a replacement/reaper instead.
    """
    import ctypes
    import math
    import signal
    from time import monotonic
    from social.connections.verification_protocol import OPERATION_SECONDS

    if (sys.platform != 'linux' or type(value) is not dict
            or type(value.get('owner_pid')) is not int
            or not 0 < value['owner_pid'] <= 2147483647
            or os.getppid() != value['owner_pid']
            or type(value.get('deadline')) not in (int, float)
            or not math.isfinite(value['deadline'])):
        raise ValueError('Invalid private lifecycle')
    remaining = value['deadline'] - monotonic()
    if not 0 < remaining <= OPERATION_SECONDS:
        raise ValueError('Invalid private deadline')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(1, ctypes.c_ulong(signal.SIGKILL), 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise ValueError('Private owner guard unavailable')
    observed = ctypes.c_int()
    if (libc.prctl(2, ctypes.byref(observed), 0, 0, 0) != 0  # PR_GET_PDEATHSIG
            or observed.value != signal.SIGKILL or os.getppid() != value['owner_pid']):
        raise ValueError('Private owner guard unavailable')
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
    remaining = value['deadline'] - monotonic()
    if remaining <= 0:
        raise ValueError('Private deadline expired')
    signal.setitimer(signal.ITIMER_REAL, remaining)


def run(value):
    from dataclasses import fields
    import base64
    import hashlib
    import math
    import re
    from time import monotonic
    from uuid import UUID
    from sqlalchemy.orm import sessionmaker
    from social.connections.config import MetaConfig
    from social.connections.contracts import ExistingGrantVerificationCommand
    from social.connections.verification_budget import VerificationBudget
    from social.connections.verification_execution import database_target, encode, _ERROR_STATUSES

    if (type(value) is not dict
            or set(value) != {'version', 'nonce', 'deadline', 'owner_pid', 'database_url', 'runtime', 'command'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['nonce']) is not str or re.fullmatch('[a-f0-9]{64}', value['nonce']) is None
            or type(value['deadline']) not in (int, float) or not math.isfinite(value['deadline'])):
        raise ValueError('Invalid private command')
    budget = VerificationBudget(deadline=value['deadline'])
    target, tls = database_target(value['database_url'])
    runtime, command = value['runtime'], value['command']
    if (type(runtime) is not dict or set(runtime) != {'config', 'native', 'privacy'}
            or type(runtime['config']) is not dict
            or set(runtime['config']) != {f.name for f in fields(MetaConfig)}
            or type(command) is not dict
            or set(command) != {'account_id', 'actor', 'binding', 'route', 'key', 'body', 'request_id'}
            or any(type(command[k]) is not str for k in ('account_id', 'actor', 'binding', 'route', 'key', 'request_id'))
            or re.fullmatch('[a-f0-9]{64}', command['binding']) is None):
        raise ValueError('Invalid private command')
    account_id, actor, key, request_id = (UUID(command[k]) for k in ('account_id', 'actor', 'key', 'request_id'))
    route = re.fullmatch(r'POST /api/v1/admin/social/accounts/([0-9a-fA-F-]{36})/verify-publishing-access', command['route'])
    if route is None or UUID(route[1]) != account_id:
        raise ValueError('Invalid private route')
    body = ExistingGrantVerificationCommand.model_validate(command['body'])
    config_values = dict(runtime['config'])
    for name in ('redirect_uris', 'verified_callback_ingress_uris'):
        if type(config_values[name]) is not list or any(type(v) is not str for v in config_values[name]):
            raise ValueError('Invalid private configuration')
        config_values[name] = tuple(config_values[name])
    config = MetaConfig(**config_values)
    config.require_ready()
    # Model imports may construct lazy application engines. They must never
    # resolve a default/local target or inherit a caller's environment instead.
    os.environ['DATABASE_URL'] = target
    from request_database import create_verification_engine
    from middleware.request_resources import request_deadline
    from social.connections.service import ConnectionService
    from social.connections.verification import SavedGrantVerificationAuthority
    from social.service import SocialError
    from social.adapters import MetaAdapterConfig, FacebookPageAdapter, InstagramFacebookLoginAdapter
    from social.privacy.ownership import OwnershipRecorder
    from social.privacy.subjects import SubjectDigester
    import httpx

    class NoDelivery(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise ValueError('Delivery is unavailable in saved-grant verification')

    native = {}
    if type(runtime['native']) is not list or len(runtime['native']) > 2:
        raise ValueError('Invalid native registry')
    for item in runtime['native']:
        if (type(item) is not dict or set(item) != {'platform', 'config'}
                or item['platform'] not in ('facebook', 'instagram') or type(item['config']) is not dict
                or set(item['config']) != {f.name for f in fields(MetaAdapterConfig)}):
            raise ValueError('Invalid native registry')
        adapter_config = MetaAdapterConfig(**item['config'])
        cls, product = ((FacebookPageAdapter, 'facebook_pages') if item['platform'] == 'facebook'
            else (InstagramFacebookLoginAdapter, 'instagram_graph_facebook_login'))
        identity = (item['platform'], product)
        if identity in native:
            raise ValueError('Duplicate native registry')
        native[identity] = cls(adapter_config, transport=NoDelivery())
    owner = None
    if runtime['privacy'] is not None:
        privacy = runtime['privacy']
        if (type(privacy) is not dict or set(privacy) != {'app_id', 'active_version', 'keys'}
                or privacy['app_id'] != config.app_id or type(privacy['keys']) is not dict):
            raise ValueError('Invalid private ownership')
        keys = {k: base64.b64decode(v, validate=True) for k, v in privacy['keys'].items()}
        owner = OwnershipRecorder(config.app_id, SubjectDigester(privacy['active_version'], keys))
    engine = create_verification_engine(target, tls)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    token = request_deadline.set(value['deadline'])
    result = {'version': 1, 'nonce': value['nonce'],
        'command_hash': hashlib.sha256(encode(command)).hexdigest()}
    try:
        with budget.activate():
            service = ConnectionService(session, config, available_adapters=native,
                ownership_recorder=owner, verification_authority=SavedGrantVerificationAuthority(config))
            try:
                response = service._verify_existing_grant(account_id, actor, command['binding'],
                    command['route'], key, body, request_id)
            except SocialError as error:
                if error.code not in _ERROR_STATUSES or error.status not in _ERROR_STATUSES[error.code]:
                    raise
                result.update(kind='error', code=error.code, status=error.status)
            else:
                result.update(kind='success', value=response)
        return result
    finally:
        session.close()
        engine.dispose()
        request_deadline.reset(token)
        # These are capability-validation objects with a rejecting transport,
        # not delivery ports. A stuck close is also inside the owned process.
        import asyncio
        for adapter in native.values():
            asyncio.run(adapter.close())


def main():
    # Only this private descriptor emits protocol. Suppress foreign import,
    # driver, telemetry and unexpected print output, including native fd writes.
    protocol = os.dup(1)
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.close(sink)
    try:
        from social.connections.verification_protocol import MAX_INPUT, MAX_OUTPUT, decode, encode
        # Only two fixed nonsecret lifecycle values cross the explicit launch
        # environment. Arm before waiting for pipe input, including lost EOF.
        owner = os.environ['AUDITGAVA_META_OWNER_PID']
        startup = {'owner_pid': int(owner),
            'deadline': float(os.environ['AUDITGAVA_META_DEADLINE'])}
        if str(startup['owner_pid']) != owner:
            return 2
        arm_lifecycle(startup)
        import logging
        logging.disable(logging.CRITICAL)
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not raw or len(raw) > MAX_INPUT:
            return 2
        value = decode(raw)
        if (type(value) is not dict or value.get('owner_pid') != startup['owner_pid']
                or value.get('deadline') != startup['deadline']):
            return 2
        arm_lifecycle(value)
        from sqlalchemy.engine import make_url
        if (type(value) is not dict or type(value.get('database_url')) is not str
                or len(value['database_url']) > 8192
                or make_url(value['database_url']).drivername != 'postgresql+psycopg2'):
            return 2
        os.environ['DATABASE_URL'] = value['database_url']
        output = encode(run(value))
        if len(output) > MAX_OUTPUT:
            return 2
        offset = 0
        while offset < len(output):
            offset += os.write(protocol, output[offset:])
        return 0
    except BaseException:
        # No exception text, query, credential, response body or partial success.
        return 2
    finally:
        os.close(protocol)


if __name__ == '__main__':
    raise SystemExit(main())

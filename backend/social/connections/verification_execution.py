"""Request-scoped saved-grant execution, with bounded pipes and positive reap.

The child owns all SQL and HTTP for this command. A timeout is an unknown
outcome: a database commit may have settled before its response was lost.
Initial OS process creation and an unresponsive kernel cannot be made into a
mathematical wall-clock guarantee; failure to confirm reap closes admission.
"""
from dataclasses import asdict
import base64
from collections.abc import Mapping
import hashlib
import ipaddress
import math
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import subprocess
import sys
import threading
from time import monotonic, monotonic as _cleanup_clock, sleep
from uuid import UUID

from sqlalchemy.engine import Engine, make_url

from ..account_publishing import AccountPublishingDTO
from ..service import SocialError
from .contracts import ExistingGrantVerificationCommand
from .verification_budget import CLEANUP_SECONDS, OPERATION_SECONDS
from .verification_protocol import MAX_INPUT, MAX_OUTPUT, encode, decode

ENTRYPOINT = Path(__file__).with_name('verification_process.py')
_admission = threading.BoundedSemaphore(1)
_closure_failed = threading.Event()
_ERRORS = {
    'NOT_FOUND': 404, 'INVALID_REQUEST': 422, 'VERSION_CONFLICT': 409,
    'IDEMPOTENCY_CONFLICT': 409, 'RECONNECT_IDENTITY_MISMATCH': 409,
    'CREDENTIAL_UNREADABLE': 503, 'CREDENTIAL_METADATA_CHANGED': 409,
    'PERMISSIONS_REQUIRED': 409, 'GRANT_REVOKED': 409,
    'PRIVACY_GRANT_BLOCKED': 409, 'PRIVACY_CONFIGURATION_INVALID': 503,
    'PRIVACY_OWNERSHIP_UNRESOLVED': 409, 'ACCOUNT_CONTROL_FAILED': 503,
    'COMMAND_RECEIPT_FAILED': 503, 'NATIVE_ADMISSION_UNAVAILABLE': 503,
    'GRANT_VERIFICATION_UNAVAILABLE': 503, 'PROVIDER_UNAVAILABLE': 502,
    'PROVIDER_RESPONSE_INVALID': 502, 'PROVIDER_REJECTED': 502,
    'DISCOVERY_LIMIT_EXCEEDED': 409, 'GRANT_VERIFICATION_BUDGET_EXCEEDED': 503,
    'ACCOUNT_MUST_BE_PAUSED': 409, 'ACCOUNT_DISCONNECTED': 409,
    'ACCOUNT_BUSY': 409, 'ACCOUNT_HELD': 409, 'CREDENTIAL_BUSY': 409,
    'CREDENTIAL_UNAVAILABLE': 409, 'PLATFORM_CONTROLS_UNAVAILABLE': 503,
    'PRIVACY_STATE_UNAVAILABLE': 503, 'DELIVERY_UNRESOLVED': 503,
}
_ERROR_STATUSES = {code: frozenset((status,)) for code, status in _ERRORS.items()}
# Initial semantic checks use conflict responses. A subsequent readiness read
# can discover the same changed condition as unavailable. Preserve both actual
# service contracts without accepting an arbitrary child's status or message.
for _code in ('ACCOUNT_DISCONNECTED', 'ACCOUNT_HELD', 'CREDENTIAL_UNAVAILABLE', 'PRIVACY_GRANT_BLOCKED'):
    _ERROR_STATUSES[_code] = frozenset((409, 503))
_MESSAGES = {
    'ACCOUNT_MUST_BE_PAUSED': 'Pause every account sharing this Page grant before verifying publishing access.',
    'ACCOUNT_DISCONNECTED': 'Reconnect this Meta account before verifying access.',
    'ACCOUNT_BUSY': 'Resolve retained publication ownership before verifying this Page grant.',
    'ACCOUNT_HELD': 'Resolve the retained account hold before verifying this Page grant.',
    'CREDENTIAL_BUSY': 'A related credential is being renewed. Check its state before retrying this command.',
    'CREDENTIAL_UNAVAILABLE': 'The saved grant is incomplete, revoked or has unresolved renewal ownership. Review its state before reconnecting.',
    'PLATFORM_CONTROLS_UNAVAILABLE': 'Platform controls could not be verified. Keep publishing paused and review their state.',
    'PRIVACY_STATE_UNAVAILABLE': 'Saved privacy ownership could not be verified. Review the retained privacy state before retrying.',
    'DELIVERY_UNRESOLVED': 'Resolve retained publication ownership before verifying this Page grant.',
}


def unavailable():
    return SocialError('GRANT_VERIFICATION_UNAVAILABLE',
        'Bounded saved-grant verification is unavailable. Publishing remains paused.', 503)


def unconfirmed():
    return SocialError('GRANT_VERIFICATION_UNCONFIRMED',
        'Verification did not return a confirmed result. Keep this command key '
        'when checking or retrying; publishing remains paused.', 503, retryable=False)


def database_target(value):
    """Preserve one parent-selected PostgreSQL target; forbid driver options."""
    if type(value) is not str or not 1 <= len(value) <= 8192:
        raise unavailable()
    url = make_url(value)
    if (url.drivername != 'postgresql+psycopg2' or not url.host
            or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}', url.host)
            or not url.username or len(url.username) > 128
            or url.password is not None and len(url.password) > 1024
            or not url.database or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', url.database)
            or url.port is not None and not 1 <= url.port <= 65535
            or not set(url.query) <= {'sslmode', 'sslrootcert'}
            or any(type(v) is not str for v in url.query.values())):
        raise unavailable()
    try:
        loopback = ipaddress.ip_address(url.host).is_loopback
    except ValueError:
        loopback = False
    if loopback:
        # Literal loopback fixtures/local installations use no DNS or remote TLS.
        tls = {'sslmode': url.query.get('sslmode', 'disable')}
        if tls['sslmode'] not in ('disable', 'require', 'verify-full'):
            raise unavailable()
    else:
        # The existing deployment already provisions this trust anchor. Missing
        # custody/configuration refuses rather than falling back to require.
        root = url.query.get('sslrootcert', '/etc/secrets/supabase-root-ca.crt')
        if (type(root) is not str or not Path(root).is_absolute()
                or not Path(root).is_file()
                or url.query.get('sslmode', 'require') not in ('require', 'verify-full')):
            raise unavailable()
        tls = {'sslmode': 'verify-full', 'sslrootcert': root}
    return value, tls


def runtime_snapshot(service):
    from .config import MetaConfig
    from ..adapters import FacebookPageAdapter, InstagramFacebookLoginAdapter, MetaAdapterConfig
    from ..privacy.ownership import OwnershipRecorder
    from ..privacy.subjects import SubjectDigester
    if type(service.config) is not MetaConfig:
        raise unavailable()
    service.config.require_ready()
    registry = service.base.available_adapters
    native = []
    if isinstance(registry, Mapping):
        for (platform, product), adapter in registry.items():
            expected = {('facebook', 'facebook_pages'): FacebookPageAdapter,
                ('instagram', 'instagram_graph_facebook_login'): InstagramFacebookLoginAdapter}.get((platform, product))
            if expected is None:
                continue
            if type(adapter) is not expected or type(adapter.config) is not MetaAdapterConfig:
                raise unavailable()
            native.append({'platform': platform, 'config': asdict(adapter.config)})
    elif registry:
        # A name set is not actual server-injected native authority.
        raise unavailable()
    privacy = None
    if service.ownership_recorder is not None:
        owner = service.ownership_recorder
        if type(owner) is not OwnershipRecorder or type(owner.digester) is not SubjectDigester:
            raise unavailable()
        privacy = {'app_id': owner.app_id, 'active_version': owner.digester.active_version,
            'keys': {k: base64.b64encode(v).decode('ascii') for k, v in owner.digester.keys.items()}}
    return {'config': asdict(service.config), 'native': native, 'privacy': privacy}


def _group_gone(process):
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _reap(process, *, kill):
    deadline = _cleanup_clock() + CLEANUP_SECONDS
    if kill:
        try:
            # The leader may already have exited while an owned descendant
            # still holds stdout or a socket. Its session/group is still ours.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=max(.001, deadline - _cleanup_clock()))
    except subprocess.TimeoutExpired:
        return False
    while not _group_gone(process):
        remaining = deadline - _cleanup_clock()
        if remaining <= 0:
            return False
        sleep(min(.01, remaining))
    return True


def run_child(payload, deadline):
    """Only the fixed trusted entrypoint; no caller-selected code or shell."""
    raw = encode(payload)
    if len(raw) > MAX_INPUT or monotonic() >= deadline:
        raise unavailable()
    if _closure_failed.is_set() or not _admission.acquire(blocking=False):
        raise unavailable()
    process = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    reaped = False
    try:
        command = [sys.executable, '-I', '-B']
        if sys.flags.optimize:
            command.append('-O')
        command.append(str(ENTRYPOINT))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            cwd=str(ENTRYPOINT.parents[2]), bufsize=0,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                 'PYTHON_DOTENV_DISABLED': '1',
                 'AUDITGAVA_META_OWNER_PID': str(os.getpid()),
                 'AUDITGAVA_META_DEADLINE': repr(deadline)})
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE)
        selector.register(process.stdout, selectors.EVENT_READ)
        offset = 0
        while selector.get_map() or process.poll() is None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise unconfirmed()
            events = selector.select(min(remaining, .05))
            for key, _ in events:
                if key.fileobj is process.stdin:
                    try:
                        written = os.write(key.fd, raw[offset:offset + 16384])
                    except BlockingIOError:
                        continue
                    offset += written
                    if offset == len(raw):
                        selector.unregister(key.fileobj)
                        process.stdin.close()
                else:
                    try:
                        chunk = os.read(key.fd, min(8192, MAX_OUTPUT - len(output) + 1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        process.stdout.close()
                    else:
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT:
                            raise unconfirmed()
        if monotonic() >= deadline or process.returncode != 0:
            raise unconfirmed()
        # poll() above already positively reaped this exact child with waitpid.
        reaped = process.returncode is not None and _group_gone(process)
        if not reaped:
            raise unconfirmed()
        return bytes(output)
    except SocialError:
        raise
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        raise unconfirmed() from None
    finally:
        cleanup_ok = True
        try:
            selector.close()
        except BaseException:
            cleanup_ok = False
        if process is not None:
            try:
                if not reaped:
                    reaped = _reap(process, kill=True)
            except BaseException:
                reaped = cleanup_ok = False
            finally:
                for pipe in (process.stdin, process.stdout):
                    try:
                        if pipe is not None:
                            pipe.close()
                    except BaseException:
                        cleanup_ok = False
        if not cleanup_ok or process is not None and not reaped:
            # No replacement can be admitted after uncertain owned-process closure.
            _closure_failed.set()
            raise unconfirmed() from None
        else:
            _admission.release()


def execute(service, account_id, actor, binding, route, key, body, request_id):
    from .service import ConnectionService
    if __package__.startswith('backend.'):
        from ...middleware.request_resources import request_deadline
    else:
        from middleware.request_resources import request_deadline
    now = monotonic()
    outer = request_deadline.get()
    deadline = now + OPERATION_SECONDS
    if outer is not None:
        if type(outer) not in (int, float) or not math.isfinite(outer):
            raise unavailable()
        deadline = min(deadline, outer - CLEANUP_SECONDS)
    if (sys.platform != 'linux' or type(service) is not ConnectionService or service.db.in_transaction()
            or service.db.new or service.db.dirty or service.db.deleted
            or not isinstance(service.db.get_bind(), Engine) or deadline <= now):
        raise unavailable()
    service._require_verification_authority().require_process_ready(service.config)
    try:
        target, _ = database_target(service.db.get_bind().url.render_as_string(hide_password=False))
        body = ExistingGrantVerificationCommand.model_validate(body.model_dump(mode='json') if isinstance(body, ExistingGrantVerificationCommand) else body)
        payload = {'version': 1, 'nonce': secrets.token_hex(32), 'deadline': deadline,
            'owner_pid': os.getpid(),
            'database_url': target, 'runtime': runtime_snapshot(service),
            'command': {'account_id': str(account_id), 'actor': str(actor), 'binding': binding,
                'route': route, 'key': str(key), 'body': body.model_dump(mode='json'),
                'request_id': str(request_id)}}
        result = decode(run_child(payload, deadline))
        if (type(result) is not dict or type(result.get('version')) is not int or result['version'] != 1
                or result.get('nonce') != payload['nonce']
                or result.get('command_hash') != hashlib.sha256(encode(payload['command'])).hexdigest()
                or monotonic() >= deadline):
            raise unconfirmed()
        if result.get('kind') == 'error' and set(result) == {'version', 'nonce', 'command_hash', 'kind', 'code', 'status'}:
            code = result['code']
            status = result['status']
            if (type(code) is not str or code not in _ERROR_STATUSES
                    or type(status) is not int or status not in _ERROR_STATUSES[code]):
                raise unconfirmed()
            message = _MESSAGES.get(code, 'Saved-grant verification was refused. Review account status '
                'and keep this command key when checking or retrying.')
            raise SocialError(code, message, status, retryable=False)
        if result.get('kind') != 'success' or set(result) != {'version', 'nonce', 'command_hash', 'kind', 'value'}:
            raise unconfirmed()
        value = AccountPublishingDTO.model_validate(result['value'])
        if (value.account_id != UUID(str(account_id)) or value.publishing_enabled is not False
                or value.controls_version != body.expected_controls_version + 1
                or value.state_token == body.expected_state):
            raise unconfirmed()
        response = value.model_dump(mode='json')
        if monotonic() >= deadline:
            raise unconfirmed()
        return response
    except SocialError:
        raise
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise unconfirmed() from None

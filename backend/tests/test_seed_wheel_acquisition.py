"""Exercise exact wheel acquisition through a transient TLS handshake timeout."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request
import zipfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def runtime(monkeypatch):
    module_path = Path(__file__).resolve().parents[2] / 'tools/nightly_acceptance_20261105/runtime.py'
    spec = importlib.util.spec_from_file_location('nightly_wheel_runtime', module_path)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as imports:
        imports.setattr(sys, 'dont_write_bytecode', True)
        imports.syspath_prepend(str(module_path.parent))
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def wheel(tmp_path, monkeypatch, runtime):
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, 'w') as archive:
        archive.writestr('pip-1.dist-info/METADATA', 'Name: pip\nVersion: 1\n')
    filename = 'pip-1-py3-none-any.whl'
    url = f'https://files.pythonhosted.org/packages/owned/{filename}'
    lock = runtime.load_lock()
    lock['packages'] = [{'name': 'pip', 'version': '1', 'filename': filename,
                         'sha256': hashlib.sha256(contents.getvalue()).hexdigest(), 'url': url}]
    monkeypatch.setattr(runtime, 'APPROVED_LOCK_IDS', {runtime.identity(lock)})
    monkeypatch.setattr(time, 'sleep', Mock())
    lock_path = tmp_path / 'lock.json'
    lock_path.write_text(json.dumps(lock))
    response = io.BytesIO(contents.getvalue())
    response.status = 200
    response.url = url
    opener = Mock()
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *_: opener)
    return lock_path, url, opener, response


def test_acquisition_recovers_from_handshake_timeout(tmp_path, wheel, runtime):
    lock, url, opener, response = wheel
    opener.open.side_effect = [urllib.error.URLError(TimeoutError('TLS handshake timed out')), response]
    wheelhouse = tmp_path / 'wheels'

    assert runtime.acquire(lock, wheelhouse) == runtime.identity(runtime.load_lock(lock))
    assert [call.args for call in opener.open.call_args_list] == [(url,), (url,)]


def test_acquisition_bounds_repeated_handshake_timeouts(tmp_path, wheel, runtime):
    lock, _, opener, _ = wheel
    opener.open.side_effect = urllib.error.URLError(TimeoutError('TLS handshake timed out'))
    wheelhouse = tmp_path / 'wheels'

    with pytest.raises(urllib.error.URLError, match='TLS handshake timed out'):
        runtime.acquire(lock, wheelhouse)
    assert opener.open.call_count == 3
    assert not list(wheelhouse.iterdir())


def test_acquisition_keeps_the_shared_deadline(tmp_path, monkeypatch, wheel, runtime):
    lock, url, opener, _ = wheel
    monkeypatch.setattr(runtime.time, 'monotonic', Mock(side_effect=[0, 299.5, 299.5]))
    opener.open.side_effect = urllib.error.URLError(TimeoutError('TLS handshake timed out'))

    with pytest.raises(urllib.error.URLError, match='TLS handshake timed out'):
        runtime.acquire(lock, tmp_path / 'wheels')
    opener.open.assert_called_once_with(url, timeout=0.5)
    runtime.time.sleep.assert_not_called()


def test_acquisition_refuses_certificate_failure_without_retrying(tmp_path, wheel, runtime):
    lock, _, opener, _ = wheel
    opener.open.side_effect = urllib.error.URLError(ssl.SSLCertVerificationError('certificate rejected'))

    with pytest.raises(urllib.error.URLError, match='certificate rejected'):
        runtime.acquire(lock, tmp_path / 'wheels')
    opener.open.assert_called_once()


def test_acquisition_refuses_altered_bytes_after_retry(tmp_path, wheel, runtime):
    lock, _, opener, response = wheel
    response.write(b'altered')
    response.seek(0)
    opener.open.side_effect = [urllib.error.URLError(TimeoutError('TLS handshake timed out')), response]

    with pytest.raises(runtime.Refusal, match='acquired wheel hash differs'):
        runtime.acquire(lock, tmp_path / 'wheels')
    assert opener.open.call_count == 2

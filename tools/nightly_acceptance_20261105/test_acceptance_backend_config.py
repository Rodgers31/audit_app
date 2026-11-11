"""Closed supported recorder configuration and original-family accounting."""
import copy
from pathlib import Path

import pytest
from common import Refusal
import record
from acceptance_backend_config import PG_URL, PLUGINS, validate_config


def config():
    return dict(schema='nightly-backend-config-v1', plugins=list(PLUGINS),
                pg_url=PG_URL, fixture_token='a' * 32, original_family='none')


@pytest.mark.parametrize('field,value', [('plugins', []), ('plugins', ['unknown']),
    ('plugins', ['../evil.py']), ('plugins', ['pytest_asyncio.plugin', 'acceptance_backend', 'os']),
    ('pg_url', PG_URL+'?host=evil.invalid'), ('pg_url', PG_URL.replace('55432','5432')),
    ('fixture_token', True), ('fixture_token', ''), ('original_family', 'all'),
    ('schema', 'unknown')])
def test_backend_configuration_rejects_unknown_plugins_targets_and_shapes(field, value):
    data = config(); data[field] = value
    with pytest.raises(Refusal): validate_config(data)


def test_recorder_has_supported_backend_and_optimized_entry(tmp_path):
    import inspect
    params = inspect.signature(record.run).parameters
    assert 'backend_config' in params and 'optimized' in params and 'native_profile' in params


@pytest.mark.parametrize('target', ['/tmp/evil.py', '../evil.py', 'backend/tests/../../evil.py',
                                     '-p', 'backend/tests//test_x.py', 'other/test_x.py'])
def test_backend_selectors_cannot_escape(target):
    from acceptance_backend_config import selectors
    with pytest.raises(Refusal): selectors([target])


def test_programmatic_plugin_allowlist_uses_exact_primitives():
    class PretendAllowed(str):
        def __eq__(self, other): return True
    data=config();data['plugins']=[PretendAllowed('unapproved.plugin'),PretendAllowed('unapproved.second')]
    with pytest.raises(Refusal):validate_config(data)

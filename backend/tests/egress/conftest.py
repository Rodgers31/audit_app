"""No application startup or production configuration in the egress lane."""
import os

import pytest

from harness import isolated_engine, local_url


@pytest.fixture
def pg_fixture(monkeypatch):
    dsn = os.environ.get('EGRESS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set explicit local EGRESS_TEST_DATABASE_URL')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    with isolated_engine(dsn) as fixture:
        # The import-only engine gets the same pinned address as the fixture.
        monkeypatch.setenv('DATABASE_URL',local_url(dsn).render_as_string(hide_password=False))
        yield fixture

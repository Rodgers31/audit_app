"""Hosted preparation rejects nonadmitted writer contexts before side effects."""
import pytest

from common import Refusal
import hosted_parser


@pytest.fixture
def writer(monkeypatch, tmp_path):
    values = {
        'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
        'GITHUB_REPOSITORY': 'Rodgers31/audit_app', 'GITHUB_REF': 'refs/heads/main',
        'GITHUB_JOB': 'seed', 'GITHUB_WORKFLOW_REF': 'Rodgers31/audit_app/.github/workflows/seed.yml@refs/heads/main',
        'GITHUB_EVENT_NAME': 'schedule', 'NIGHTLY_ENABLED': 'true', 'GITHUB_SHA': 'a' * 40,
        'GITHUB_WORKFLOW_SHA': 'a' * 40, 'APPROVED_SHA': 'a' * 40, 'RUNNER_TEMP': str(tmp_path),
    }
    monkeypatch.setattr(hosted_parser, 'checkout_revision', lambda: 'a' * 40)
    monkeypatch.setattr(hosted_parser.os, 'environ', values)
    return values


@pytest.mark.parametrize(('name', 'value'), [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_JOB', 'notify'), ('RUNNER_ENVIRONMENT', 'self-hosted'),
    ('GITHUB_REF', 'refs/heads/topic'), ('GITHUB_WORKFLOW_REF', 'another-workflow'),
    ('GITHUB_EVENT_NAME', 'pull_request'), ('NIGHTLY_ENABLED', 'false'),
    ('APPROVED_SHA', 'b' * 40), ('GITHUB_WORKFLOW_SHA', 'b' * 40),
    ('DATABASE_URL', 'synthetic'), ('DATABASE_POOLER_URL', 'synthetic'),
    ('SUPABASE_SERVICE_ROLE_KEY', 'synthetic'), ('RECEIPT_SUPABASE_SECRET_KEY', 'synthetic'),
    ('RECEIPT_R2_ACCESS_KEY_ID', 'synthetic'), ('RECEIPT_R2_SECRET_ACCESS_KEY', 'synthetic'),
    ('RECEIPT_R2_CONTROL_TOKEN', 'synthetic'),
])
def test_nonadmitted_writer_never_provisions(writer, tmp_path, name, value):
    writer[name] = value
    with pytest.raises(Refusal):
        hosted_parser.main()
    assert not list(tmp_path.iterdir())

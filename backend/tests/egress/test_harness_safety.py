"""Benchmark targets must be explicit and local before any connection exists."""
import pytest

from harness import local_url


@pytest.mark.parametrize('url',[
    '', 'sqlite://', 'mysql://localhost/social_worker_test',
    'postgresql+asyncpg://localhost:62124/social_worker_test',
    'postgresql://user:PRIVATE@production.invalid:62124/social_worker_test',
    'postgresql://localhost:5432/social_worker_test',
    'postgresql://localhost:62124/audit_app',
    'postgresql://localhost:62124/social_domain_test',
])
def test_benchmark_rejects_every_unassigned_target_without_connecting(url):
    with pytest.raises(ValueError):
        local_url(url)


def test_benchmark_names_synchronous_driver_for_explicit_assigned_target():
    assert local_url('postgresql://localhost:62124/social_worker_test').drivername=='postgresql+psycopg2'

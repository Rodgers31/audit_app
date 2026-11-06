"""Explicit, closed backend configuration. No arbitrary environment or plugins."""
from pathlib import Path
import re

from common import Refusal, fields, require, string

PLUGINS = ('pytest_asyncio.plugin', 'acceptance_backend')
PG_URL = 'postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture'
FISCAL_URL = 'postgresql+psycopg2://postgres@127.0.0.1:55432/fiscal_fixture'
OFF = ('AUTO_SEED_ENABLED', 'AUTO_SEEDER_ENABLED', 'SOCIAL_NATIVE_ENABLED',
       'SOCIAL_PUBLISHING_ENABLED', 'SOCIAL_MEDIA_ENABLED', 'SOCIAL_MEDIA_UPLOADS_ENABLED',
       'SOCIAL_WORKER_SUPERVISOR_ENABLED', 'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED',
       'SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'SOCIAL_GENERATION_HOOK_ENABLED',
       'SOCIAL_REPORT_GENERATION_ENABLED', 'SOCIAL_STUDIO_ENABLED', 'ADMIN_ETL_DISPATCH_ENABLED')


def validate_config(value):
    fields(value, ('schema', 'plugins', 'pg_url', 'fixture_token', 'original_family'))
    require(type(value['schema']) is str and value['schema'] == 'nightly-backend-config-v1', 'unknown backend configuration')
    require(type(value['plugins']) is list and all(type(plugin) is str for plugin in value['plugins'])
            and value['plugins'] == list(PLUGINS),
            'only the explicit supported backend plugin inventory is allowed')
    require(type(value['pg_url']) is str and value['pg_url'] == PG_URL, 'dedicated query-free owned PostgreSQL URL required')
    require(type(value['fixture_token']) is str
            and re.fullmatch('[0-9a-f]{32}', value['fixture_token']) is not None,
            'owned fixture token required')
    require(type(value['original_family']) is str and value['original_family'] in ('none', 'original36'),
            'unknown backend source family')
    return value


def selectors(targets):
    for target in targets:
        name = string(target).split('::', 1)[0]
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts
                and path.as_posix() == name and name != '.'
                and (name.startswith('backend/tests/') or name.startswith('tools/nightly_acceptance_20261105/')),
                'backend selector must stay inside the owned source test roots')


def environment(repo, output, config):
    validate_config(config)
    return {'PYTHONPATH': ':'.join(str(p) for p in
            (Path(__file__).absolute().parent, repo / 'backend', repo / 'backend/tests')),
            'PYTHON_DOTENV_DISABLED': '1', 'ENVIRONMENT': 'test', 'SECRET_BACKEND': 'env',
            'SECRET_KEY': 'inert-acceptance-fixture-key-20261105',
            'JWT_SECRET_KEY': 'inert-acceptance-fixture-key-20261105', 'REDIS_URL': '',
            'DATABASE_URL': FISCAL_URL,
            'REFRESH_FIXTURE_PG_URL': PG_URL, 'REFRESH_FIXTURE_OWNED': 'true',
            'REFRESH_FIXTURE_TOKEN': config['fixture_token'],
            'FISCAL_TEST_POSTGRES_URL': FISCAL_URL, 'AUDIT_TEST_POSTGRES_URL': FISCAL_URL,
            'NIGHTLY_BACKEND_REPORT': str(output / 'backend.json'),
            'NIGHTLY_ORIGINAL_FAMILY': config['original_family'], **{key: 'false' for key in OFF}}


def validate_report(report, config, expected):
    from acceptance_inventory import ORIGINAL_PG, ORIGINAL_CONSTANT
    fields(report, ('schema', 'exitstatus', 'databases', 'canonical_pg_cases',
                    'closed_schemas', 'schema_scope', 'original_family'))
    require(report['schema'] == 'nightly-backend-observations-v1'
            and type(report['exitstatus']) is int and report['exitstatus'] == 0,
            'backend observer did not complete')
    require(report['databases'] == [[db, 'postgres', 'postgres', '127.0.0.1', 55432, 'postgres']
            for db in ('auditgava_refresh_fixture', 'fiscal_fixture')], 'backend database observations differ')
    cases = report['canonical_pg_cases']
    require(type(cases) is list and all(type(node) is str and node in expected for node in cases)
            and len(set(cases)) == len(cases), 'invalid actual PG case inventory')
    require(report['schema_scope'] == 'isolated-model-fixtures-not-migrated-production'
            and report['original_family'] == config['original_family'], 'backend scope differs')
    require(type(report['closed_schemas']) is list and bool(report['closed_schemas']),
            'positive owned schema cleanup observations required')
    names = set()
    for row in report['closed_schemas']:
        fields(row, ('schema', 'database', 'schema_absent'))
        require(type(row['schema']) is str
                and re.fullmatch('acceptance_' + config['fixture_token'][:16] + '_[0-9a-f]{12}', row['schema']) is not None
                and row['schema'] not in names and row['database'] == 'auditgava_refresh_fixture'
                and row['schema_absent'] is True, 'owned schema cleanup incomplete or duplicated')
        names.add(row['schema'])
    if config['original_family'] == 'original36':
        require(set(ORIGINAL_PG) | {ORIGINAL_CONSTANT} <= set(expected)
                and set(ORIGINAL_PG) <= set(cases) and ORIGINAL_CONSTANT not in cases,
                'original36 is 35 actual PG cases plus one constant')
    return report

"""Public inert configuration contract; no production value is accepted."""
import base64
import json
import re


def inert_environment(values, *, controller=False):
    if type(controller) is not bool:
        raise ValueError('Explicit controller mode required')
    if type(values) is not dict or not all(type(k) is str and type(v) is str for k, v in values.items()):
        raise ValueError('String fixture environment required')
    if any(k in values for k in ('B29_SANDBOX', 'LD_PRELOAD', 'NSS_WRAPPER_HOSTS')):
        allowed = {'/usr/lib/x86_64-linux-gnu/libnss_wrapper.so',
                   '/usr/lib/aarch64-linux-gnu/libnss_wrapper.so'}
        if (values.get('B29_SANDBOX') != 'landlock-seccomp-v1'
                or values.get('LD_PRELOAD') not in allowed
                or values.get('NSS_WRAPPER_HOSTS') != '/etc/b29-hosts'):
            raise ValueError('Exact mountless fixture resolver required')
        values = {k:v for k,v in values.items()
                  if k not in ('B29_SANDBOX', 'LD_PRELOAD', 'NSS_WRAPPER_HOSTS')}
    fixed = dict(META_CONNECTIONS_ENABLED='true', META_APP_CONFIGURATION_VALIDATED='true',
        META_APP_ID='123', META_APP_SECRET='inert-rehearsal-app', META_ACCESS_MODE='owned_standard',
        META_REDIRECT_URIS='["https://admin.example.test/admin/social/accounts/callback"]',
        SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION='v1', META_PRIVACY_ENABLED='true',
        META_DEAUTHORIZATION_ENABLED='true',
        META_PRIVACY_STATUS_URL='https://admin.example.test/api/v1/social/privacy/meta/data-deletion/status',
        META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION='v1', SOCIAL_MEDIA_ENABLED='false',
        SOCIAL_WORKER_MEDIA_READS_ENABLED='true', SOCIAL_MEDIA_RETAINED_WRITES_ENABLED='false',
        SOCIAL_MEDIA_R2_ENDPOINT='https://' + 'a' * 32 + '.r2.cloudflarestorage.com',
        SOCIAL_MEDIA_BUCKET='media-test', SOCIAL_MEDIA_ACCESS_KEY='inert-rehearsal-access',
        SOCIAL_MEDIA_SECRET_KEY='inert-rehearsal-secret', AWS_EC2_METADATA_DISABLED='true')
    for key, expected in fixed.items():
        if values.get(key) != expected:
            raise ValueError('Inert configuration mismatch: ' + key)
    for key, content in [('SOCIAL_CREDENTIAL_KEYS', b'0' * 32), ('META_PRIVACY_SUBJECT_KEYS', b'1' * 32)]:
        if values.get(key) != json.dumps({'v1': base64.urlsafe_b64encode(content).decode()}):
            raise ValueError('Inert keyring required: ' + key)
    optional = dict(PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8',
        HOME='/tmp', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH='/harness:/app:/app/tests/social', PORT='33501', WEB_CONCURRENCY='1',
        ENVIRONMENT='test', SECRET_KEY='inert-rehearsal-signing-key', AUTO_SEEDER_ENABLED='false',
        SUPABASE_URL='https://auth.fixture.test', SUPABASE_SERVICE_ROLE_KEY='inert-profile-service',
        SUPABASE_JWT_SECRET='inert-rehearsal-admin-jwt', REDIS_URL='',
        SSL_CERT_FILE='/evidence/ca.pem', AWS_CA_BUNDLE='/evidence/ca.pem',
        B27_FIXTURE='isolated', B15_REHEARSAL='isolated', B15_START_DELAY='0', B15_CLOSE_DELAY='0',
        SOCIAL_WORKER_ROLE='b15_worker', SOCIAL_WORKER_DATABASE_SCHEMA='public',
        SOCIAL_WORKER_SHUTDOWN_SECONDS='60')
    for key, expected in optional.items():
        if controller and ((key == 'PYTHONPATH' and values.get(key) == '/app:/app/tests/social')
                           or (key == 'B15_REHEARSAL' and values.get(key) == '')):
            continue
        if key in values and values[key] != expected:
            raise ValueError('Inert configuration mismatch: ' + key)
    dynamic = {'SOCIAL_CREDENTIAL_KEYS', 'META_PRIVACY_SUBJECT_KEYS', 'B27_MODE',
               'PYTHONOPTIMIZE', 'SOCIAL_NATIVE_ENABLED', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED',
               'SOCIAL_WORKER_SUPERVISOR_ENABLED', 'B15_START_GATE', 'B15_CLOSE_GATE', 'B15_RUN_GATE',
               'B15_ENDPOINT_RUN_ID', 'RENDER_GIT_COMMIT', 'DATABASE_URL', 'SOCIAL_WORKER_DATABASE_URL'}
    if set(values) - (set(fixed) | set(optional) | dynamic):
        raise ValueError('Unknown fixture environment')
    for key in ('SOCIAL_NATIVE_ENABLED', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED',
                'SOCIAL_WORKER_SUPERVISOR_ENABLED', 'B15_START_GATE', 'B15_CLOSE_GATE', 'B15_RUN_GATE'):
        if key in values and values[key] not in ('true', 'false'):
            raise ValueError('Boolean fixture flag required')
    if values.get('PYTHONOPTIMIZE') not in ('0', '1'):
        raise ValueError('Explicit interpreter mode required')
    if 'B27_MODE' in values and values['B27_MODE'] not in ('service', 'auxiliary'):
        raise ValueError('Fixed fixture mode required')
    for key in ('B15_ENDPOINT_RUN_ID', 'RENDER_GIT_COMMIT'):
        if key in values and not re.fullmatch('[0-9a-f]{12}', values[key]):
            raise ValueError('Owned fixture identity required')
    for key, prefix in [('DATABASE_URL', 'postgresql+psycopg2://postgres@b15-worker-db:5432/'),
                        ('SOCIAL_WORKER_DATABASE_URL', 'postgresql+psycopg2://b15_worker@b15-worker-wire:5432/')]:
        if key in values and not re.fullmatch(re.escape(prefix) + 'b15_worker_[a-z_]{1,24}', values[key]):
            raise ValueError('Owned inert database required')


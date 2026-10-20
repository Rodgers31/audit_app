"""All fixture credentials are fixed public test values; no ambient values."""
import base64
import json
import re


def environment(run_id):
    if type(run_id) is not str or not re.fullmatch('[0-9a-f]{12}', run_id):
        raise ValueError('Owned run identity required')
    db = 'b15_worker_capacity'
    return dict(PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', HOME='/tmp',
        PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', PYTHONOPTIMIZE='0',
        PYTHONPATH='/harness:/app:/app/tests/social', PORT='33501', WEB_CONCURRENCY='1',
        ENVIRONMENT='test', SECRET_KEY='inert-rehearsal-signing-key', AUTO_SEEDER_ENABLED='false',
        SUPABASE_URL='https://auth.fixture.test', SUPABASE_SERVICE_ROLE_KEY='inert-profile-service',
        SUPABASE_JWT_SECRET='inert-rehearsal-admin-jwt', REDIS_URL='',
        SSL_CERT_FILE='/evidence/ca.pem', AWS_CA_BUNDLE='/evidence/ca.pem',
        AWS_EC2_METADATA_DISABLED='true', DATABASE_URL='postgresql+psycopg2://postgres@b15-worker-db:5432/' + db,
        SOCIAL_WORKER_DATABASE_URL='postgresql+psycopg2://b15_worker@b15-worker-wire:5432/' + db,
        SOCIAL_WORKER_ROLE='b15_worker', SOCIAL_WORKER_DATABASE_SCHEMA='public',
        SOCIAL_WORKER_SUPERVISOR_ENABLED='true', SOCIAL_WORKER_SHUTDOWN_SECONDS='60',
        SOCIAL_NATIVE_ENABLED='true', SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED='true',
        META_CONNECTIONS_ENABLED='true', META_APP_CONFIGURATION_VALIDATED='true', META_APP_ID='123',
        META_APP_SECRET='inert-rehearsal-app', META_ACCESS_MODE='owned_standard',
        META_REDIRECT_URIS='["https://admin.example.test/admin/social/accounts/callback"]',
        SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION='v1',
        SOCIAL_CREDENTIAL_KEYS=json.dumps({'v1': base64.urlsafe_b64encode(b'0' * 32).decode()}),
        META_PRIVACY_ENABLED='true', META_DEAUTHORIZATION_ENABLED='true',
        META_PRIVACY_STATUS_URL='https://admin.example.test/api/v1/social/privacy/meta/data-deletion/status',
        META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION='v1',
        META_PRIVACY_SUBJECT_KEYS=json.dumps({'v1': base64.urlsafe_b64encode(b'1' * 32).decode()}),
        SOCIAL_MEDIA_ENABLED='false', SOCIAL_WORKER_MEDIA_READS_ENABLED='true',
        SOCIAL_MEDIA_RETAINED_WRITES_ENABLED='false',
        SOCIAL_MEDIA_R2_ENDPOINT='https://' + 'a' * 32 + '.r2.cloudflarestorage.com',
        SOCIAL_MEDIA_BUCKET='media-test', SOCIAL_MEDIA_ACCESS_KEY='inert-rehearsal-access',
        SOCIAL_MEDIA_SECRET_KEY='inert-rehearsal-secret',
        B15_REHEARSAL='isolated', B15_START_DELAY='0', B15_CLOSE_DELAY='0',
        B15_START_GATE='false', B15_CLOSE_GATE='false', B15_RUN_GATE='true',
        B15_ENDPOINT_RUN_ID=run_id, RENDER_GIT_COMMIT=run_id)

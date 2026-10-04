from dataclasses import replace
from urllib.parse import urlsplit, parse_qs

import pytest

from social.media.config import MediaConfig, config_from_environment
from social.media.runtime import media_runtime
from social.media.storage import R2Storage
from test_media_support import ENDPOINT


def test_defaults_and_environment_fail_closed(monkeypatch):
    assert not config_from_environment({}).enabled
    with pytest.raises(ValueError): config_from_environment({'SOCIAL_MEDIA_ENABLED':'yes'})
    monkeypatch.setattr('social.media.runtime.config_from_environment', lambda: (_ for _ in ()).throw(ValueError('private-secret-config')))
    media_runtime.cache_clear()
    runtime=media_runtime()
    assert runtime.available_mimes()==() and runtime.storage is None
    assert 'private-secret-config' not in runtime.unavailable_reason
    media_runtime.cache_clear()


@pytest.mark.parametrize('field,value', [('enabled',1), ('upload_ttl',True), ('preview_ttl',601), ('max_image_bytes',11*1024*1024), ('max_video_bytes',0), ('actor_quota_bytes',float('inf')), ('inspection_timeout',31), ('lease_seconds',30)])
def test_strict_resource_config(field,value):
    with pytest.raises(ValueError): replace(MediaConfig(),**{field:value}).validate()


@pytest.mark.parametrize('endpoint', ['http://localhost','https://localhost','https://example.org','https://user:secret@'+'a'*32+'.r2.cloudflarestorage.com',ENDPOINT+'?url=http://metadata',ENDPOINT+'/path',ENDPOINT+':9999'])
def test_only_explicit_private_account_storage_endpoint(endpoint):
    with pytest.raises(ValueError): MediaConfig(enabled=True,endpoint=endpoint,bucket='media-test',access_key='secret',secret_key='secret').validate()


def test_installed_sdk_offline_signs_exact_length_and_create_only_headers():
    boto3=pytest.importorskip('boto3')
    from botocore.config import Config
    client=boto3.client('s3',endpoint_url=ENDPOINT,region_name='auto',aws_access_key_id='fake-test',aws_secret_access_key='fake-test',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
    grant=R2Storage(client,'media-test',ENDPOINT).authorize_upload('quarantine/test/source',10,'image/png',300)
    headers=parse_qs(urlsplit(grant.url).query)['X-Amz-SignedHeaders'][0].split(';')
    assert {'host','content-length','content-type','if-none-match'} <= set(headers)
    assert 'fake-test' not in repr(grant)


def test_runtime_makes_only_one_sdk_wire_attempt_on_an_ambiguous_mutating_timeout(monkeypatch):
    import boto3
    from botocore.exceptions import ReadTimeoutError
    config=MediaConfig(enabled=True,endpoint=ENDPOINT,bucket='media-test',access_key='fake-test',secret_key='fake-test')
    monkeypatch.setattr('social.media.runtime.config_from_environment',lambda:config)
    media_runtime.cache_clear(); runtime=media_runtime()
    client=runtime.storage.client; calls=[]
    def timeout(request):
        calls.append('wire attempt')
        raise ReadTimeoutError(endpoint_url='https://fixture.invalid')
    monkeypatch.setattr(client._endpoint.http_session,'send',timeout)
    try:
        with pytest.raises(ReadTimeoutError): client.put_object(Bucket='media-test',Key='ready/fixture/original',Body=b'data',ContentLength=4,IfNoneMatch='*')
        assert calls==['wire attempt']
        assert client.meta.config.retries['total_max_attempts']==1
    finally: media_runtime.cache_clear()

from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from social.connections.crypto import CredentialCipher
from social.service import SocialError

def test_fernet_owner_purpose_tamper_and_rotation():
    owner = uuid4()
    keys = {'v1': Fernet.generate_key().decode(), 'v2':Fernet.generate_key().decode()}
    old = CredentialCipher('v1', keys)
    version, ciphertext = old.encrypt(owner, 'facebook_page', {'access_token':'fake-sensitive-token'})
    assert b'fake-sensitive-token' not in ciphertext
    assert old.decrypt(owner, 'facebook_page', version, ciphertext)['access_token'] == 'fake-sensitive-token'
    for other_owner,purpose,data in [(uuid4(),'facebook_page',ciphertext),(owner,'facebook_user',ciphertext),(owner,'facebook_page',ciphertext[:-1]+b'x')]:
        with pytest.raises(SocialError, match='CREDENTIAL_UNREADABLE'):
            old.decrypt(other_owner,purpose,version,data)
    new = CredentialCipher('v2', keys)
    new_version,new_cipher = new.rotate(owner,'facebook_page',version,ciphertext)
    assert new_version == 'v2' and new_cipher != ciphertext
    assert CredentialCipher('v2',{'v2':keys['v2']}).decrypt(owner,'facebook_page',new_version,new_cipher)['access_token'] == 'fake-sensitive-token'
    with pytest.raises(SocialError,match='CREDENTIAL_UNREADABLE'):
        CredentialCipher('v2',{'v2':keys['v2']}).decrypt(owner,'facebook_page',version,ciphertext)

@pytest.mark.parametrize('version,keys',[('',{}),('v2',{'v1':Fernet.generate_key().decode()}),('v1',{'v1':'not-a-fernet-key'}),('invalid key',{'invalid key':Fernet.generate_key().decode()})])
def test_missing_malformed_keys_fail_closed(version,keys):
    with pytest.raises(SocialError,match='ENCRYPTION_UNAVAILABLE'):
        CredentialCipher(version,keys)

@pytest.mark.parametrize('flag',[1,'true','false',None])
def test_config_flags_must_be_real_true(config,flag):
    from dataclasses import replace
    assert replace(config,enabled=flag).blockers()
    assert replace(config,app_configuration_validated=flag).blockers()

@pytest.mark.parametrize('url',['https://example.test:99999/admin/social/accounts/callback','https://[invalid/admin/social/accounts/callback','https://example.test\\evil/admin/social/accounts/callback','https://example.test/admin/social/accounts/callback?code=x','http://example.test/admin/social/accounts/callback'])
def test_registered_redirect_parser_rejects_malformed_urls(url):
    from social.connections.config import valid_redirect
    assert not valid_redirect(url)
from test_connections_support import config

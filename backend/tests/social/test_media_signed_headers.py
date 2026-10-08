import pytest
from test_media_storage_adversary import SDK, storage, signed_url, KEY, GOOD
from social.media.storage import StorageFailure

@pytest.mark.parametrize('headers', [
    'host;host;content-length;content-type;if-none-match',
    'host;content-length;content-type;if-none-match;*',
    'host;content-length;content-type;if-none-match;',
    'host;;content-length;content-type;if-none-match',
    'Host;Content-Length;Content-Type;If-None-Match',
    'if-none-match;host;content-length;content-type',
])
def test_noncanonical_signed_header_list_is_rejected(headers):
    with pytest.raises(StorageFailure):
        storage(SDK(url=signed_url(headers=headers))).authorize_upload(KEY, len(GOOD), 'image/png', 300)

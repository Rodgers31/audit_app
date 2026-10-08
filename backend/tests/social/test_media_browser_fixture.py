"""Loopback fixture controls, distinct from the manually executed browser lane."""
from http.client import HTTPConnection
from urllib.parse import urlsplit

import pytest

from scripts.social_media_browser_fixture import MAX_BODY, browser_fixture, image_bytes, main


def request(origin, method, path, body=None, headers=None):
    address = urlsplit(origin)
    connection = HTTPConnection(address.hostname, address.port, timeout=3)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally: connection.close()


def test_fixture_enforces_create_only_type_length_origin_and_private_access():
    with browser_fixture() as (origins, objects, observations):
        data = image_bytes('PNG')
        headers = {'Origin': origins['app'], 'Content-Type': 'image/png', 'If-None-Match': '*'}
        target = origins['objects']
        assert request(target, 'PUT', '/png?fixture_grant=controlled', data, headers)[0] == 200
        assert request(target, 'PUT', '/png?fixture_grant=controlled', data, headers)[0] == 412
        assert request(target, 'PUT', '/type?fixture_grant=controlled', data, {**headers, 'Content-Type':'image/jpeg'})[0] == 403
        assert request(target, 'PUT', '/length?fixture_grant=controlled', data + b'x', headers)[0] == 403
        assert request(target, 'PUT', '/guard?fixture_grant=controlled', data, {**headers, 'If-None-Match':''})[0] == 403
        assert request(target, 'PUT', '/foreign?fixture_grant=controlled', data, {**headers, 'Origin':'https://foreign.invalid'})[0] == 403
        # Reject the declared size before receiving/allocating a request body.
        assert request(target, 'PUT', '/foreign?fixture_grant=controlled', headers={**headers, 'Content-Length':str(MAX_BODY + 1)})[0] == 413
        assert request(target, 'GET', '/png')[0] == 403
        status, cors, returned = request(target, 'GET', '/png?fixture_grant=controlled', headers={'Origin':origins['app']})
        assert status == 200 and returned == data
        assert cors['Access-Control-Allow-Origin'] == origins['app']
        assert 'Access-Control-Allow-Credentials' not in cors
        assert list(objects) == ['/png']


@pytest.mark.parametrize('origin,headers,status', [
    ('exact', 'content-type, if-none-match', 204),
    ('https://foreign.invalid', 'content-type, if-none-match', 403),
    ('exact', '*', 403), ('exact', 'content-type, content-type', 403),
])
def test_fixture_preflight_has_exact_origin_and_no_wildcards_or_duplicate_headers(origin, headers, status):
    with browser_fixture() as (origins, objects, _):
        origin = origins['app'] if origin == 'exact' else origin
        actual, cors, _ = request(origins['objects'], 'OPTIONS', '/png?fixture_grant=controlled', headers={
            'Origin':origin, 'Access-Control-Request-Method':'PUT', 'Access-Control-Request-Headers':headers})
        assert actual == status and objects == {}
        if actual == 204:
            assert cors['Access-Control-Allow-Origin'] == origin
            assert cors['Access-Control-Allow-Headers'] == 'content-type, if-none-match'
        else: assert 'Access-Control-Allow-Methods' not in cors


@pytest.mark.parametrize('seconds', ['0', '-1', '121'])
def test_cli_lifetime_is_bounded_before_binding(monkeypatch, capsys, seconds):
    monkeypatch.setattr('scripts.social_media_browser_fixture.browser_fixture', lambda: (_ for _ in ()).throw(AssertionError('bound socket')))
    assert main(['--seconds', seconds]) == 2
    assert 'INVALID_FIXTURE_LIFETIME' in capsys.readouterr().out

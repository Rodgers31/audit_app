"""Real HTTPX streaming under an inert transport; not live grant acceptance."""
import json

import httpx
import pytest

from social.connections.provider import MetaProvider
from social.connections.verification_budget import VerificationBudget, current_budget
from social.service import SocialError
from test_connections_support import config


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks, clock=None, seconds=0):
        self.chunks, self.clock, self.seconds = chunks, clock, seconds
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            if self.clock is not None:
                self.clock.value += self.seconds
            yield chunk

    def close(self):
        self.closed = True


def invoke(provider, budget, function):
    token = current_budget.set(budget)
    try:
        return function()
    finally:
        current_budget.reset(token)
        provider.close()


@pytest.fixture
def provider_for(config):
    return lambda handler: MetaProvider(config, transport=httpx.MockTransport(handler))


def test_headers_consume_the_existing_operation_deadline(provider_for):
    clock = Clock()
    stream = Stream([b'{}'])

    def reply(request):
        clock.value = 21.0
        return httpx.Response(200, stream=stream)

    provider = provider_for(reply)
    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(clock=clock), lambda: provider._request('GET', 'me'))
    assert caught.value.code == 'GRANT_VERIFICATION_BUDGET_EXCEEDED'
    assert stream.closed


def test_raw_trickle_is_checked_without_16k_buffering(monkeypatch, provider_for):
    clock = Clock()
    monkeypatch.setattr('social.connections.provider.time.monotonic', clock)
    stream = Stream([b' ', b' ', b' ', b' ', b'{}'], clock, 8.0)
    provider = provider_for(lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(clock=clock), lambda: provider._request('GET', 'me'))
    assert caught.value.code == 'GRANT_VERIFICATION_BUDGET_EXCEEDED'
    assert clock.value == 24.0
    assert stream.closed


def test_all_requests_share_the_same_count_budget(provider_for):
    calls = []
    provider = provider_for(lambda request: calls.append(request) or httpx.Response(200, json={}))

    def read():
        for _ in range(45):
            provider._request('GET', 'me')

    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(), read)
    assert caught.value.code == 'GRANT_VERIFICATION_BUDGET_EXCEEDED'
    assert len(calls) == 44


def test_all_bodies_share_the_same_byte_budget(provider_for):
    calls, streams = [], []
    body = json.dumps({'data': 'a' * 949980}).encode()

    def reply(request):
        calls.append(request)
        stream = Stream([body])
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    provider = provider_for(reply)

    def read():
        for _ in range(9):
            provider._request('GET', 'me')

    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(), read)
    assert caught.value.code == 'GRANT_VERIFICATION_BUDGET_EXCEEDED'
    assert len(calls) == 9 and all(stream.closed for stream in streams)


@pytest.mark.parametrize('method', ['POST', 'DELETE', 'PUT', 'PATCH'])
def test_saved_budget_never_admits_a_mutation(method, provider_for):
    calls = []
    provider = provider_for(lambda request: calls.append(request) or httpx.Response(200, json={}))
    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(), lambda: provider._request(method, 'me'))
    assert caught.value.code == 'GRANT_VERIFICATION_BUDGET_EXCEEDED'
    assert not calls


@pytest.mark.parametrize('response', [
    lambda: httpx.Response(200, json={'data': {}}),
    lambda: httpx.Response(200, stream=Stream([b'{"data": {}}'])),
])
def test_preloaded_and_real_streaming_json_remain_supported(response, provider_for):
    provider = provider_for(lambda request: response())
    assert invoke(provider, VerificationBudget(), lambda: provider._request('GET', 'me')) == {'data': {}}


def test_compression_refuses_before_iteration(provider_for):
    stream = Stream([b'untrusted'])
    provider = provider_for(lambda request: httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=stream))
    with pytest.raises(SocialError) as caught:
        invoke(provider, VerificationBudget(), lambda: provider._request('GET', 'me'))
    assert caught.value.code == 'PROVIDER_RESPONSE_INVALID'
    assert stream.closed


@pytest.mark.parametrize('deadline', [True, False, float('nan'), float('inf'), -1, 0, 21.0, '20'])
def test_invalid_or_widened_deadlines_refuse(deadline):
    with pytest.raises(SocialError):
        VerificationBudget(deadline=deadline, clock=Clock())


def test_nested_budget_keeps_one_counter_and_restores_context():
    budget = VerificationBudget()
    assert current_budget.get() is None
    with budget.activate():
        budget.request('GET')
        with budget.activate():
            assert current_budget.get() is budget
            budget.request('GET')
        assert current_budget.get() is budget and budget.requests == 2
    assert current_budget.get() is None

"""Force the shared app/storage admission race at the final request slot."""
import builtins
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

from scripts import social_media_browser_fixture as fixture
from test_media_browser_hostility import raw_request


def test_app_and_storage_share_one_atomic_last_request_slot(monkeypatch):
    with fixture.browser_fixture() as (origins, objects, observations):
        observations.extend({} for _ in range(fixture.MAX_REQUESTS - 1))
        simultaneous_checks = Barrier(2)

        def gated_len(value):
            count = builtins.len(value)
            if value is observations and count == fixture.MAX_REQUESTS - 1:
                # On the old code both servers observe 63 before either appends.
                # With admission locked the second server cannot reach this
                # check until the first consumes the last slot.
                try:
                    simultaneous_checks.wait(timeout=0.5)
                except BrokenBarrierError:
                    pass
            return count

        monkeypatch.setattr(fixture, 'len', gated_len, raising=False)
        with ThreadPoolExecutor(max_workers=2) as workers:
            calls = [workers.submit(raw_request, origins[key], 'GET', '/png', [])
                     for key in ('app', 'objects')]
            statuses = [call.result(timeout=4)[0] for call in calls]
        assert builtins.len(observations) == fixture.MAX_REQUESTS
        assert statuses.count(429) == 1
        assert objects == {}

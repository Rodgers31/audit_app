"""Fresh OAG bodies with official origins checked before redirected connections."""
from ...native_report_authority import DOMAINS, official_url

LISTING_MAX_SECONDS = 45.0
LISTING_MAX_BYTES = 4 * 1024 * 1024
PDF_MAX_BYTES = 64 * 1024 * 1024
OFFICIAL_HOSTS = frozenset(DOMAINS['audits'][1])


def get_official_body(client, url, *, max_seconds=LISTING_MAX_SECONDS,
                      max_bytes=LISTING_MAX_BYTES):
    """Use the shared cumulative byte/attempt/deadline and per-hop origin gate.

    Discovery links are publisher input, not permission to contact another host.
    Content, edition, retention and publication checks remain with their owners.
    """
    if not official_url(url, 'audits'):
        raise ValueError('Official OAG HTTPS origin required')
    return client.get(url, raise_for_status=True, cache=False,
        max_seconds=max_seconds, max_bytes=max_bytes, allowed_hosts=OFFICIAL_HOSTS)


class OfficialListingClient:
    """Keep the shared discovery parser inside the same OAG acquisition gate.

    The parser needs only GET. Its discovered year-page and sitemap URLs are
    checked as untrusted publisher input on every call, before connection.
    """
    def __init__(self, client):
        self._client = client

    def get(self, url, *, raise_for_status=True):
        return get_official_body(self._client, url)

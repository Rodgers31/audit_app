"""One reviewed CRA edition; no discovery, redirects or arbitrary input URLs."""
from datetime import datetime, timezone
import time

import httpx

URL = "https://cra.go.ke/wp-content/uploads/2026/02/CRA-Recommendation-on-The-Basis-for-Equitable-Sharing-Of-Revenue-FY-2026-27.pdf"
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 30


class CraSourceRefused(ValueError):
    """The supported recommendation could not be validated; no fallback."""


def fetch_publication():
    started = time.monotonic()
    # Do not inherit proxy credentials, follow another publisher, or retry a
    # partial response as a different edition. The CLI adds its domain deadline.
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        with client.stream("GET", URL, headers={"User-Agent": "KenyaAuditAppSeeder/1.0"}) as response:
            if response.status_code != 200 or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/pdf":
                raise CraSourceRefused("CRA expected a 200 PDF response from the supported edition")
            payload = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() - started > MAX_SECONDS or len(payload) + len(chunk) > MAX_BYTES:
                    raise CraSourceRefused("CRA response exceeded its time or byte bound")
                payload.extend(chunk)
    return bytes(payload), datetime.now(timezone.utc)

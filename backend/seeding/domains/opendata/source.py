"""One pinned, public KNBS edition. No discovery, redirects or substitute source."""
from datetime import datetime, timezone
import time
import httpx

URL = 'https://www.knbs.or.ke/wp-content/uploads/2026/10/Chapter-5-Public-Finance.xlsx'
REPORT_URL = 'https://www.knbs.or.ke/reports/2026-economic-survey/'
PUBLISHER = 'Kenya National Bureau of Statistics'
SHA256 = '887712acdb8ec673f96d6d0fd14491a5861b0450d2ffcf49aedde093a257a5d5'
ARTIFACT_BYTES = 224617
MAX_BYTES = 1024 * 1024
MAX_SECONDS = 30
CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

class OpenDataSourceRefused(ValueError):
    """Unsupported source or semantic state; no fallback and no inferred values."""


def fetch_publication():
    started = time.monotonic()
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        with client.stream('GET', URL, headers={'User-Agent': 'KenyaAuditAppSeeder/1.0'}) as response:
            if response.status_code != 200 or response.headers.get('content-type', '').split(';', 1)[0].strip().lower() not in (CONTENT_TYPE, 'application/octet-stream'):
                raise OpenDataSourceRefused('OpenData expected a 200 official KNBS workbook response')
            payload = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() - started > MAX_SECONDS or len(payload) + len(chunk) > MAX_BYTES:
                    raise OpenDataSourceRefused('OpenData response exceeded its time or byte bound')
                payload.extend(chunk)
    if time.monotonic() - started > MAX_SECONDS:
        raise OpenDataSourceRefused('OpenData response exceeded its time bound')
    return bytes(payload), datetime.now(timezone.utc)

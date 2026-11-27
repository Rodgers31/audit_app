"""Bounded intake of the private, byte-pinned OAG county archive."""
from contextlib import contextmanager
import hashlib
import logging
import re
from tempfile import TemporaryFile
import time
from urllib.parse import parse_qs, urlsplit
from zipfile import BadZipFile, ZipFile

import httpx

ARCHIVE_URL_ENV = "SEED_OAG_COUNTY_ARCHIVE_URL"
ARCHIVE_SHA256 = "b2dd9d5859c758b5189484fbfd2eb95255e09f7400b90482dd338925378482e2"
ARCHIVE_BYTES = 130_624_671
ARCHIVE_FILENAME = "retained-oag-county-only.zip"
ARCHIVE_SECONDS = 120
ARCHIVE_CACHE_ORIGIN = "county_archive"
R2_HOST = r"[0-9a-f]{32}\.r2\.cloudflarestorage\.com"
R2_BUCKET = r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]"


class CountyArchiveRefused(ValueError):
    """The archive configuration or delivered bytes failed verification."""


def _require_private_url(url):
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, max_num_fields=16)
    except ValueError:
        raise CountyArchiveRefused("invalid county archive URL") from None
    path_style = re.fullmatch(R2_HOST, parsed.netloc) and re.fullmatch(
        rf"/{R2_BUCKET}/{re.escape(ARCHIVE_FILENAME)}", parsed.path
    )
    virtual_hosted = (
        re.fullmatch(rf"{R2_BUCKET}\.{R2_HOST}", parsed.netloc)
        and parsed.path == "/" + ARCHIVE_FILENAME
    )
    signature = query.get("X-Amz-Signature", [])
    if (
        parsed.scheme != "https"
        or parsed.fragment
        or not (path_style or virtual_hosted)
        or query.get("X-Amz-Algorithm") != ["AWS4-HMAC-SHA256"]
        or len(signature) != 1
        or re.fullmatch(r"[a-f0-9]{64}", signature[0]) is None
    ):
        raise CountyArchiveRefused("invalid county archive URL")


def _download(client, url, target, deadline):
    digest = hashlib.sha256()
    size = 0
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    # The httpx request log would include the bearer URL.
    logger = logging.getLogger("httpx")

    def suppress_request_log(_record):
        return False

    logger.addFilter(suppress_request_log)
    try:
        with client.stream(
            "GET",
            url,
            headers={"Accept-Encoding": "identity"},
            follow_redirects=False,
            timeout=httpx.Timeout(min(remaining, 15), connect=min(remaining, 10)),
        ) as response:
            if response.status_code in (401, 403, 404, 408, 410, 429) or (
                500 <= response.status_code < 600
            ):
                return False
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity").lower()
                != "identity"
            ):
                raise CountyArchiveRefused("county archive response refused")
            for chunk in response.iter_raw():
                if time.monotonic() >= deadline:
                    return False
                size += len(chunk)
                if size > ARCHIVE_BYTES:
                    raise CountyArchiveRefused("county archive byte cap exceeded")
                target.write(chunk)
                digest.update(chunk)
    except httpx.RequestError:
        return False
    finally:
        logger.removeFilter(suppress_request_log)
    if time.monotonic() >= deadline:
        return False
    if size != ARCHIVE_BYTES or digest.hexdigest() != ARCHIVE_SHA256:
        raise CountyArchiveRefused(
            "county archive does not match reviewed SHA-256 and size"
        )
    target.seek(0)
    return True


@contextmanager
def open_reviewed_archive(client, url, deadline):
    """Yield None on transport unavailability, or the authenticated ZIP."""
    _require_private_url(url)
    deadline = min(deadline, time.monotonic() + ARCHIVE_SECONDS)
    with TemporaryFile() as target:
        if not _download(client, url, target, deadline):
            yield None
            return
        try:
            with ZipFile(target) as archive:
                yield archive
        except BadZipFile:
            raise CountyArchiveRefused("county archive ZIP is invalid") from None

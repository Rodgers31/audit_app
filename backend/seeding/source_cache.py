"""Explicit preparation of reviewed retained PDFs; no DB mutation or parsing.

Default invocation inspects actual bytes and refuses missing/corrupt evidence.
--fetch permits bounded official downloads. --county-archive permits a pinned
private restore of county bytes. Coverage/public APIs never call this module.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import pdf_artifact
from .county_archive import (
    ARCHIVE_CACHE_ORIGIN,
    ARCHIVE_URL_ENV,
    CountyArchiveRefused,
    open_reviewed_archive,
)
from .domains.audits.observation import ACCEPTED_SHA256, accepted_editions

LEGACY_MANIFEST_SHA256 = (
    "1514ecb0cf0edd42dd57a8b28666dcde0aba4f0182fa59748361189357f88a82"
)
CACHE_PARTS = ("data", "seeding", "cache", "pdfs")
MAX_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 300


class SourceCacheRefused(ValueError):
    """Preparation did not establish the reviewed artifact identities."""


def reviewed_sources(profile="county"):
    if profile not in ("county", "reviewed"):
        raise SourceCacheRefused("unknown reviewed source profile")
    result = {
        url: {"url": url, "sha256": e["sha256"], "md5": e["md5"]}
        for url, e in accepted_editions().items()
    }
    if profile == "reviewed":
        raw = (
            Path(__file__).with_name("retained-audit-legacy-manifest.json").read_bytes()
        )
        if hashlib.sha256(raw).hexdigest() != LEGACY_MANIFEST_SHA256:
            raise SourceCacheRefused("reviewed legacy artifact authority changed")
        for entry in json.loads(raw):
            if entry["url"] in result:
                raise SourceCacheRefused("duplicate reviewed artifact URL")
            result[entry["url"]] = entry
    for url, entry in result.items():
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.oagkenya.go.ke"
            or not parsed.path.startswith("/wp-content/uploads/")
            or parsed.query
            or parsed.fragment
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
            or re.fullmatch(r"[0-9a-f]{32}", entry["md5"]) is None
        ):
            raise SourceCacheRefused("invalid reviewed public artifact authority")
    return result


def _cache_fd(root, create):
    """Open beneath the explicit root without following child symlinks."""
    fd = os.open(Path(root).resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in CACHE_PARTS:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass  # Existing directory is checked with O_NOFOLLOW below.
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                if not create:
                    return None
                raise
            os.close(fd)
            fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def _pdf_identity(source, size):
    if source.read(5) != b"%PDF-":
        raise SourceCacheRefused("retained artifact is not a PDF")
    source.seek(max(0, size - 2048))
    if not source.read().rstrip().endswith(b"%%EOF"):
        raise SourceCacheRefused("retained PDF is incomplete")
    source.seek(0)
    sha, md5 = hashlib.sha256(), hashlib.md5()
    for chunk in iter(lambda: source.read(1 << 20), b""):
        sha.update(chunk)
        md5.update(chunk)
    return {
        "sha256": sha.hexdigest(),
        "md5": md5.hexdigest(),
        "size_bytes": size,
    }


def _identity(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
        raise SourceCacheRefused("retained PDF is not a bounded regular file")
    with os.fdopen(os.dup(fd), "rb") as source:
        source.seek(0)
        identity = _pdf_identity(source, info.st_size)
    after = os.fstat(fd)
    if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SourceCacheRefused("retained PDF changed during verification")
    return identity


def _verify(cache_fd, name, expected):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=cache_fd)
    except FileNotFoundError:
        return None
    try:
        actual = _identity(fd)
        current = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
        opened = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise SourceCacheRefused("retained PDF locator changed during verification")
        if any(actual[k] != expected[k] for k in ("sha256", "md5")):
            raise SourceCacheRefused("retained PDF differs from reviewed edition")
        if "size_bytes" in expected and actual["size_bytes"] != expected["size_bytes"]:
            raise SourceCacheRefused("retained PDF differs from artifact binding")
        return actual
    finally:
        os.close(fd)


def _preflight(documents, authority):
    result = []
    by_url = {}
    for doc in documents:
        if doc.url in by_url:
            raise SourceCacheRefused("duplicate registered source URL")
        by_url[doc.url] = doc
    if set(by_url) != set(authority):
        raise SourceCacheRefused(
            "registered sources do not match exact reviewed profile"
        )
    for url, entry in authority.items():
        doc = by_url[url]
        name = hashlib.sha256(url.encode()).hexdigest() + ".pdf"
        locator = "/".join((*CACHE_PARTS, name))
        if (
            type(doc.id) is not int
            or doc.id <= 0
            or doc.publisher != "Office of the Auditor-General"
            or getattr(doc.doc_type, "name", doc.doc_type) != "AUDIT"
            or getattr(doc.status, "name", doc.status) != "AVAILABLE"
            or doc.md5 != entry["md5"]
            or doc.file_path != locator
            or not isinstance(doc.title, str)
            or not doc.title.strip()
            or not isinstance(doc.meta, dict)
        ):
            raise SourceCacheRefused("registered source identity/path changed")
        if "extracted_md5" in doc.meta and doc.meta["extracted_md5"] != doc.md5:
            raise SourceCacheRefused("registered extracted MD5 changed")
        expected = dict(entry)
        if pdf_artifact.ARTIFACT_KEY in doc.meta:
            artifact = doc.meta[pdf_artifact.ARTIFACT_KEY]
            if (
                not pdf_artifact.artifact_matches_document(artifact, doc)
                or artifact["sha256"] != entry["sha256"]
            ):
                raise SourceCacheRefused("registered PDF artifact binding changed")
            expected["size_bytes"] = artifact["size_bytes"]
        result.append((doc, name, locator, expected))
    return result


def _write_sidecar(cache_fd, name, metadata, *, from_archive):
    sidecar = name[:-4] + ".json"
    # An orphan sidecar may have existed before the archive PDF was installed.
    # Swap it atomically so archive bytes always carry the correct provenance.
    dest = ".retained-" + uuid.uuid4().hex + ".json" if from_archive else sidecar
    try:
        meta_fd = os.open(
            dest,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=cache_fd,
        )
    except FileExistsError:
        if from_archive:
            raise
        return
    try:
        with os.fdopen(meta_fd, "w") as meta:
            json.dump(metadata, meta, allow_nan=False)
            meta.flush()
            os.fsync(meta.fileno())
        if from_archive:
            os.replace(dest, sidecar, src_dir_fd=cache_fd, dst_dir_fd=cache_fd)
    finally:
        if from_archive:
            try:
                os.unlink(dest, dir_fd=cache_fd)
            except FileNotFoundError:
                pass


def _install(cache_fd, name, expected, deadline, chunks, *, from_archive=False):
    staging = ".retained-" + uuid.uuid4().hex + ".pdf"
    fd = os.open(
        staging,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=cache_fd,
    )
    try:
        size = 0
        with os.fdopen(os.dup(fd), "wb") as dest:
            for chunk in chunks:
                if time.monotonic() >= deadline:
                    raise SourceCacheRefused(
                        "source preparation total deadline exceeded"
                    )
                size += len(chunk)
                if size > MAX_BYTES:
                    raise SourceCacheRefused("retained artifact exceeds byte cap")
                dest.write(chunk)
            dest.flush()
            os.fsync(dest.fileno())
        actual = _identity(fd)
        if any(actual[k] != expected[k] for k in ("sha256", "md5")):
            raise SourceCacheRefused("delivered bytes differ from reviewed PDF edition")
        if "size_bytes" in expected and actual["size_bytes"] != expected["size_bytes"]:
            raise SourceCacheRefused("delivered bytes differ from artifact binding")
        if time.monotonic() >= deadline:
            raise SourceCacheRefused("source preparation total deadline exceeded")
        staged = os.stat(staging, dir_fd=cache_fd, follow_symlinks=False)
        opened = os.fstat(fd)
        if (staged.st_dev, staged.st_ino) != (opened.st_dev, opened.st_ino):
            raise SourceCacheRefused("staging PDF locator changed before installation")
        try:
            os.link(
                staging,
                name,
                src_dir_fd=cache_fd,
                dst_dir_fd=cache_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _verify(cache_fd, name, expected) is None:
                raise SourceCacheRefused("concurrent PDF installation disappeared")
        else:
            installed = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
            try:
                # Check the actual link before earning cache bookkeeping.
                _verify(cache_fd, name, expected)
                metadata = {
                    "url": expected["url"],
                    "created_at": time.time(),
                    "bytes": size,
                    "sha256": actual["sha256"],
                    "fingerprint": None,
                }
                if from_archive:
                    metadata["restored_from"] = ARCHIVE_CACHE_ORIGIN
                _write_sidecar(cache_fd, name, metadata, from_archive=from_archive)
            except Exception:
                current = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (
                    installed.st_dev,
                    installed.st_ino,
                ):
                    os.unlink(name, dir_fd=cache_fd)
                    os.fsync(cache_fd)
                raise
        os.fsync(cache_fd)
        return _verify(cache_fd, name, expected)
    finally:
        os.close(fd)
        try:
            os.unlink(staging, dir_fd=cache_fd)
        except FileNotFoundError:
            pass  # A removed staging locator cannot become a ready receipt.


def _download(client, cache_fd, name, expected, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SourceCacheRefused("source preparation total deadline exceeded")
    timeout = httpx.Timeout(min(remaining, 30), connect=min(remaining, 15))
    with client.stream(
        "GET", expected["url"], follow_redirects=False, timeout=timeout
    ) as response:
        if (
            response.status_code != 200
            or str(response.url) != expected["url"]
            or "html" in response.headers.get("content-type", "").lower()
        ):
            raise SourceCacheRefused(
                "publisher artifact response identity/type changed"
            )
        return _install(cache_fd, name, expected, deadline, response.iter_bytes())


def _verify_county_archive(archive, selected):
    names = archive.namelist()
    required = {"manifest.json", *(locator for _, _, locator, _ in selected)}
    if len(names) != len(required) or set(names) != required:
        raise SourceCacheRefused(
            "county archive does not contain the exact reviewed paths"
        )
    if archive.getinfo("manifest.json").file_size > 32 * 1024:
        raise SourceCacheRefused("county archive manifest exceeds byte cap")
    index = json.loads(archive.read("manifest.json"))
    if (
        index.get("version") != 1
        or index.get("kind") != "reviewed_pdf_bytes"
        or not isinstance(index.get("entries"), list)
        or len(index["entries"]) != len(selected)
    ):
        raise SourceCacheRefused("county archive manifest schema changed")
    entries = {entry["path"]: entry for entry in index["entries"]}
    if set(entries) != required - {"manifest.json"}:
        raise SourceCacheRefused("county archive manifest paths changed")
    for doc, _, locator, expected in selected:
        size = archive.getinfo(locator).file_size
        if not 0 < size <= MAX_BYTES:
            raise SourceCacheRefused("county archive PDF exceeds byte cap")
        if entries[locator] != {
            "source_id": doc.id,
            "source_url": doc.url,
            "path": locator,
            "sha256": expected["sha256"],
            "md5": expected["md5"],
            "bytes": size,
            "profile": "county",
        } or size != expected.get("size_bytes", size):
            raise SourceCacheRefused("county archive PDF binding changed")
        with archive.open(locator) as source:
            actual = _pdf_identity(source, size)
        if any(actual[key] != expected[key] for key in ("sha256", "md5")):
            raise SourceCacheRefused("county archive PDF differs from reviewed edition")


def prepare_sources(
    documents,
    *,
    root=None,
    profile="county",
    fetch=False,
    county_archive_url=None,
    client=None,
    max_seconds=MAX_SECONDS,
):
    if (
        type(fetch) is not bool
        or type(max_seconds) not in (int, float)
        or (not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS)
    ):
        raise SourceCacheRefused("typed fetch and bounded finite deadline required")
    if county_archive_url is not None and profile != "county":
        raise SourceCacheRefused("private archive requires the county profile")
    deadline = time.monotonic() + max_seconds
    selected = _preflight(documents, reviewed_sources(profile))
    receipt = {
        "schema": "retained_source_cache_preparation/v1",
        "profile": profile,
        "accepted_manifest_sha256": ACCEPTED_SHA256,
        "legacy_manifest_sha256": LEGACY_MANIFEST_SHA256
        if profile == "reviewed"
        else None,
        "ready": False,
        "database_mutations": False,
        "entries": [],
    }
    if county_archive_url is not None:
        receipt["county_archive"] = (
            "not_needed" if county_archive_url else "unconfigured"
        )
    explicit_root = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    root_before = explicit_root.stat()
    cache_fd = _cache_fd(explicit_root, False)
    owned_client = None
    try:
        missing = []
        for doc, name, locator, expected in selected:
            actual = _verify(cache_fd, name, expected) if cache_fd is not None else None
            item = {
                "source_id": doc.id,
                "url": doc.url,
                "file_path": locator,
                "state": "verified" if actual else "missing",
                "identity": actual,
            }
            receipt["entries"].append(item)
            if actual is None:
                missing.append((name, expected, item))
        if missing and (fetch or county_archive_url):
            if client is None:
                owned_client = httpx.Client(trust_env=False, follow_redirects=False)
                client = owned_client
        if missing and county_archive_url:
            with open_reviewed_archive(client, county_archive_url, deadline) as archive:
                if archive is None:
                    receipt["county_archive"] = "unavailable"
                else:
                    _verify_county_archive(archive, selected)
                    if cache_fd is None:
                        cache_fd = _cache_fd(explicit_root, True)
                    for name, expected, item in missing:
                        with archive.open(item["file_path"]) as source:
                            item["identity"] = _install(
                                cache_fd,
                                name,
                                expected,
                                deadline,
                                iter(lambda: source.read(1 << 20), b""),
                                from_archive=True,
                            )
                        item["state"] = "restored"
                    missing.clear()
                    receipt["county_archive"] = "restored"
        if missing and fetch:
            if cache_fd is None:
                cache_fd = _cache_fd(explicit_root, True)
            for name, expected, item in missing:
                item["identity"] = _download(client, cache_fd, name, expected, deadline)
                item["state"] = "restored"
        # Reopen declared locators after all downloads. An earlier verified
        # file or detached directory must never leave a stale ready claim.
        root_after = explicit_root.stat()
        if (root_before.st_dev, root_before.st_ino) != (
            root_after.st_dev,
            root_after.st_ino,
        ):
            raise SourceCacheRefused("explicit source root changed during preparation")
        final_fd = _cache_fd(explicit_root, False)
        try:
            if cache_fd is not None:
                if final_fd is None or (
                    os.fstat(cache_fd).st_dev,
                    os.fstat(cache_fd).st_ino,
                ) != (os.fstat(final_fd).st_dev, os.fstat(final_fd).st_ino):
                    raise SourceCacheRefused(
                        "cache directory changed during preparation"
                    )
            for (_, name, _, expected), item in zip(selected, receipt["entries"]):
                item["identity"] = (
                    _verify(final_fd, name, expected) if final_fd is not None else None
                )
                if item["identity"] is None:
                    if item["state"] != "missing":
                        raise SourceCacheRefused("verified retained PDF disappeared")
        finally:
            if final_fd is not None:
                os.close(final_fd)
        receipt["ready"] = all(e["identity"] is not None for e in receipt["entries"])
        return receipt
    finally:
        if owned_client is not None:
            owned_client.close()
        if cache_fd is not None:
            os.close(cache_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url-env",
        required=True,
        help="explicit environment variable holding the read-only connection URL",
    )
    parser.add_argument("--profile", choices=("county", "reviewed"), default="county")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument(
        "--county-archive",
        action="store_true",
        help="try the pinned private county archive before official downloads",
    )
    parser.add_argument("--max-seconds", type=float, default=MAX_SECONDS)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    from sqlalchemy import create_engine, inspect, select, text
    from sqlalchemy.orm import Session
    from models import Country, SourceDocument
    from db_url import with_explicit_driver
    from github_database_tls import connection_args as github_connection_args

    engine = None
    try:
        if args.receipt is not None and args.receipt.exists():
            raise SourceCacheRefused("receipt path already exists")
        authority = reviewed_sources(args.profile)
        engine = create_engine(
            with_explicit_driver(os.environ[args.database_url_env]),
            connect_args={"connect_timeout": 8, **github_connection_args()},
        )
        if engine.dialect.name != "postgresql":
            raise SourceCacheRefused(
                "explicit PostgreSQL read-only connection required"
            )
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout='15s'"))
            with Session(bind=connection, autoflush=False) as session:
                docs = (
                    session.execute(
                        select(SourceDocument)
                        .join(Country)
                        .where(
                            Country.iso_code == "KEN", SourceDocument.url.in_(authority)
                        )
                    )
                    .scalars()
                    .all()
                )

                def source_image(rows):
                    return json.dumps(
                        {
                            doc.id: {
                                column.key: copy.deepcopy(getattr(doc, column.key))
                                for column in inspect(SourceDocument).column_attrs
                            }
                            for doc in rows
                        },
                        sort_keys=True,
                        default=str,
                        allow_nan=False,
                    )

                before_image = source_image(docs)
                receipt = prepare_sources(
                    docs,
                    root=args.root,
                    profile=args.profile,
                    fetch=args.fetch,
                    county_archive_url=os.environ.get(ARCHIVE_URL_ENV, "")
                    if args.county_archive
                    else None,
                    max_seconds=args.max_seconds,
                )
                # Same current identity must remain available through preparation.
                session.expire_all()
                current = (
                    session.execute(
                        select(SourceDocument)
                        .join(Country)
                        .where(
                            Country.iso_code == "KEN", SourceDocument.url.in_(authority)
                        )
                    )
                    .scalars()
                    .all()
                )
                _preflight(current, authority)
                if source_image(current) != before_image:
                    raise SourceCacheRefused(
                        "whole source image changed during preparation"
                    )
        if args.receipt is not None:
            with args.receipt.open("x") as out:
                json.dump(receipt, out, sort_keys=True, indent=2, allow_nan=False)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
        print(json.dumps(receipt, sort_keys=True, allow_nan=False))
        return (
            0
            if receipt["ready"]
            or (
                args.county_archive
                and not args.fetch
                and receipt["county_archive"] in ("unconfigured", "unavailable")
            )
            else 1
        )
    except (SourceCacheRefused, CountyArchiveRefused) as exc:
        print(json.dumps({"ready": False, "status": "refused", "reason": str(exc)}))
        return 1
    except Exception as exc:
        # Connection/transport internals can contain deployment details; emit
        # the failure class, never the explicit connection URL or credentials.
        print(
            json.dumps({"ready": False, "status": "failed", "type": type(exc).__name__})
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

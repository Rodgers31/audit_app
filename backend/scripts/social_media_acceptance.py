"""Offline #490 declaration review. No environment defaults or live probes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from social.media.acceptance import MAX_JSON_BYTES, PacketError, evaluate_packet, parse_json


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise PacketError()


def _read(path):
    fd = None
    try:
        if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_NONBLOCK")):
            raise PacketError()
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_JSON_BYTES:
            raise PacketError()
        with os.fdopen(fd, "rb") as source:
            fd = None
            raw = source.read(MAX_JSON_BYTES + 1)
        return parse_json(raw)
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None):
    parser = _Arguments(prog="social_media_acceptance", description="Validate bounded declarations for #490 operator review; no receipts are authenticated and no storage is enabled.")
    parser.add_argument("--packet", type=Path, help="Explicit bounded JSON packet; no source-storage substitute")
    parser.add_argument("--scope", type=Path, help="Independent expected social scope JSON")
    parser.add_argument("--as-of", help="Explicit timezone-aware review time, including seconds")
    try:
        argv = sys.argv[1:] if argv is None else argv
        if (type(argv) is not list or len(argv) > 16 or any(type(item) is not str or len(item) > 2048
                or any(ord(c) < 32 or ord(c) == 127 for c in item) for item in argv)):
            raise PacketError()
        args = parser.parse_args(argv)
        # Default invocation does not read a file, environment or implicit clock.
        if not args.scope or not args.as_of:
            result = evaluate_packet(None, expected_scope=None, as_of=None)
            result["status"] = "MISSING_EVIDENCE"
            result["reason_codes"] = ["EXPLICIT_SCOPE_AND_AS_OF_REQUIRED"]
        else:
            scope = _read(args.scope)
            packet = _read(args.packet) if args.packet else None
            result = evaluate_packet(packet, expected_scope=scope, as_of=args.as_of)
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        result = evaluate_packet(None, expected_scope=None, as_of=None)
        result["reason_codes"] = ["MEDIA_ACCEPTANCE_INPUT_REFUSED"]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_OPERATOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())

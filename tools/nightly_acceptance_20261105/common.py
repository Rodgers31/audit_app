"""Strict, append-only evidence primitives; no application imports or credentials."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


class Refusal(ValueError):
    """An input cannot establish the requested evidence."""


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(raw):
    def invalid(value):
        raise Refusal(f"nonfinite JSON number: {value}")
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid)
    except (ValueError, TypeError) as exc:
        raise Refusal(f"invalid JSON: {exc}") from exc
    def finite(item):
        if type(item) is float:
            require(math.isfinite(item), "nonfinite JSON number")
        elif type(item) is list:
            for member in item:
                finite(member)
        elif type(item) is dict:
            for member in item.values():
                finite(member)
    finite(value)
    return value


def read_json(path):
    return loads(Path(path).read_bytes())


def fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), f"expected fields: {sorted(keys)}")


def string(value):
    require(type(value) is str and bool(value.strip()), "nonempty string required")
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, f"integer >= {minimum} required")
    return value


def digest(value, length=64):
    require(type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None,
            f"{length}-character hex digest required")
    return value


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def publish(path, value):
    """Fresh external destinations are checked by callers before launching work."""
    path = Path(path)
    data = canonical(value) + b'\n'
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
    # Equality alone lets False equal 0. Compare canonical serialized primitives.
    require(canonical(read_json(path)) == canonical(value), "receipt disk readback differs")
    return sha256(path)

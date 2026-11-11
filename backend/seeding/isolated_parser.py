"""Isolate document decoding from the credentialed ingestion process."""
from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from functools import cache, wraps
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import selectors
import socket
import stat
import struct
import subprocess
import tempfile
import time
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from uuid import uuid4

IMAGE = "sha256:157f663999af4028c94af9bee589e035bb32dff38f6d8a23d7a2f580cf368e6b"
IMAGE_CONFIG = "sha256:81e6c77d988633c08afdc01cd94aed3501ca4648071121aca655c2ceb72b92ae"
IMAGE_DIFF_ID = "sha256:21aadd0e7ab91a7f0030132975d24fee68b0f5e9c9dac7b1c04f333b3275a2d1"
IMAGE_TAG = "auditgava-native-qualification:915-20261111"
MAX_DOCUMENT = 120 * 1024**2
MAX_REQUEST = 512 * 1024
MAX_RESPONSE = 32 * 1024**2
CLIENT_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
WORKER_ENV = {"PATH": "/opt/ingestion/bin:/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
              "TMPDIR": "/tmp", "LC_ALL": "C.UTF-8", "OMP_THREAD_LIMIT": "1",
              "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1"}
_OPERATIONS = {}
_in_worker = False
_ALLOWED_MODULES = {
    "seeding.isolated_parser", "seeding.domains.county_borrowing.decoder", "seeding.domains.cra.decoder",
    "seeding.native_report_authority", "seeding.kra_report_catalogue",
    "seeding.native_ocr", "seeding.native_report_cover", "seeding.oag_report_catalogue",
    "seeding.pdf_parsers", "seeding.county_borrowing_contract",
    "seeding.county_borrowing_mapping_evidence",
    "seeding.extractors.oag_blue_book", "seeding.extractors.oag_county_audit",
    "seeding.extractors.oag_county_volume",
    "seeding.domains.audits.fetcher", "seeding.domains.counties_budget.publication",
    "seeding.domains.cra.parser", "seeding.domains.fiscal_summary.actuals",
    "seeding.domains.fiscal_summary.budget_estimates", "seeding.domains.fiscal_summary.fetcher",
    "seeding.domains.fiscal_summary.fiscal_framework", "seeding.domains.fiscal_summary.revenue_estimates",
    "seeding.domains.national_budget.fetcher", "seeding.domains.national_budget.headline",
    "seeding.domains.national_budget.pdf_parser", "seeding.domains.national_debt.cbk_bulletin",
    "seeding.domains.national_debt.wb_ids_xml",
    "seeding.domains.opendata.parser", "seeding.domains.pending_bills.aging",
    "seeding.domains.pending_bills.brop_parser", "seeding.domains.population.census_counties",
    "seeding.domains.revenue_by_source.fetcher", "seeding.domains.stalled_projects.cob_parser",
    "services.fiscal_authority",
}


class ParserIsolationError(ValueError):
    """The isolated decoder could not supply a usable result."""


def _require(condition, message):
    if not condition:
        raise ParserIsolationError(message)


def _pairs(pairs):
    result = dict(pairs)
    _require(len(result) == len(pairs), "duplicate parser JSON key")
    return result


def _load(data, limit):
    _require(0 < len(data) <= limit, "parser message exceeds its size limit")
    return json.loads(data, object_pairs_hook=_pairs)


def _dump(data, limit):
    value = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()
    _require(len(value) <= limit, "parser message exceeds its size limit")
    return value


def _encode(value, types):
    cls = type(value)
    if value is None or cls in (str, bool, int, float):
        return value
    if cls is list:
        return [_encode(item, types) for item in value]
    if cls is dict:
        return {"map": [[_encode(k, types), _encode(v, types)] for k, v in value.items()]}
    if cls is tuple:
        return {"tuple": [_encode(item, types) for item in value]}
    if cls is Decimal:
        _require(value.is_finite(), "nonfinite decimal from parser")
        return {"decimal": str(value)}
    if cls in (date, datetime):
        return {cls.__name__: value.isoformat()}
    _require(types.get(cls.__name__) is cls, "unsupported parser value type")
    return {"record": [cls.__name__, [_encode(getattr(value, f.name), types) for f in fields(cls)]]}


@cache
def _annotations(record):
    return get_type_hints(record)


def _shape(value, annotation):
    if annotation is Any:
        return True
    kind, parameters = get_origin(annotation), get_args(annotation)
    if kind in (Union, UnionType):
        return any(_shape(value, alternative) for alternative in parameters)
    if kind is Literal:
        return any(type(value) is type(choice) and value == choice for choice in parameters)
    if kind is list:
        return type(value) is list and all(_shape(item, parameters[0]) for item in value)
    if kind is dict:
        return type(value) is dict and all(_shape(k, parameters[0]) and _shape(v, parameters[1])
                                          for k, v in value.items())
    if kind is tuple:
        if type(value) is not tuple:
            return False
        if len(parameters) == 2 and parameters[1] is Ellipsis:
            return all(_shape(item, parameters[0]) for item in value)
        return len(value) == len(parameters) and all(_shape(v, t) for v, t in zip(value, parameters))
    if annotation is float:
        return type(value) in (float, int)
    return type(value) is annotation


def _decode(value, types):
    cls = type(value)
    if value is None or cls in (str, bool, int, float):
        _require(cls is not float or math.isfinite(value), "nonfinite parser number")
        return value
    if cls is list:
        return [_decode(item, types) for item in value]
    _require(cls is dict and len(value) == 1, "invalid parser value")
    (key, payload), = value.items()
    if key == "map":
        _require(type(payload) is list, "invalid parser mapping")
        result = {}
        for item in payload:
            _require(type(item) is list and len(item) == 2, "invalid parser mapping item")
            k, v = (_decode(member, types) for member in item)
            _require(type(k) in (str, int, tuple) and k not in result, "invalid parser mapping key")
            result[k] = v
        return result
    if key == "tuple":
        _require(type(payload) is list, "invalid parser tuple")
        return tuple(_decode(item, types) for item in payload)
    if key == "decimal":
        _require(type(payload) is str and len(payload) <= 128, "invalid parser decimal")
        number = Decimal(payload)
        _require(number.is_finite() and abs(number.adjusted()) <= 100,
                 "nonfinite or out-of-range parser decimal")
        return number
    if key in ("date", "datetime"):
        _require(type(payload) is str and len(payload) <= 64, "invalid parser date")
        return (date if key == "date" else datetime).fromisoformat(payload)
    if key == "record":
        _require(type(payload) is list and len(payload) == 2 and type(payload[0]) is str
                 and payload[0] in types and type(payload[1]) is list, "invalid parser record")
        record = types[payload[0]]
        names = fields(record)
        _require(len(names) == len(payload[1]), "invalid parser record field count")
        values = {f.name: _decode(v, types) for f, v in zip(names, payload[1])}
        _require(all(_shape(v, _annotations(record)[k]) for k, v in values.items()),
                 "parser record field type differs")
        return record(**values)
    raise ParserIsolationError("unknown parser value")


def _capture(document, destination):
    digest = hashlib.sha256()
    size = 0
    with destination.open("xb") as out:
        if type(document) is bytes:
            size = len(document)
            _require(0 < size <= MAX_DOCUMENT, "document exceeds parser size limit")
            digest.update(document)
            out.write(document)
        else:
            fd = os.open(document, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                before = os.fstat(source.fileno())
                _require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_DOCUMENT,
                         "document exceeds parser size limit or is not a regular file")
                while block := source.read(1024 * 1024):
                    size += len(block)
                    _require(size <= MAX_DOCUMENT, "document exceeds parser size limit")
                    digest.update(block)
                    out.write(block)
                after = os.fstat(source.fileno())
                _require(size == before.st_size == after.st_size
                         and before.st_mtime_ns == after.st_mtime_ns
                         and before.st_ctime_ns == after.st_ctime_ns, "document changed during capture")
    destination.chmod(0o444)
    return digest.hexdigest()


def _docker_command(root):
    # Trusted launcher creates this empty config, so Docker never uses a
    # credential helper, context or proxy settings from the writer's home.
    config = root / "docker"
    _require((config / "config.json").read_bytes() == b"{}\n", "parser Docker configuration differs")
    return ["docker", "--host", "unix:///var/run/docker.sock", "--config", str(config)]


def parser_identity():
    """Identify a hosted parser for persisted-cache separation."""
    root = os.environ.get("SEED_PARSER_ROOT")
    if root is None:
        _require(os.environ.get("AUDIT_GITHUB_DATABASE_TLS") != "1" or _in_worker,
                 "credentialed ingestion requires the isolated parser")
        return None
    source = Path(root) / "source" / "backend"
    fingerprint = hashlib.sha256(IMAGE.encode())
    for relative in ("ingestion-runtime.lock.json", "seeding/isolated_parser.py",
                     "seeding/parser_worker.py", "seeding/native_ocr.py", "seeding/native_parser_child.py"):
        with (source / relative).open("rb") as stream:
            fingerprint.update(hashlib.file_digest(stream, "sha256").digest())
    return fingerprint.hexdigest()


def _control(docker, *arguments):
    return subprocess.run([*docker, *arguments], env=CLIENT_ENV, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=20, check=True).stdout


def _read_worker(docker, name, timeout):
    deadline = time.monotonic() + timeout
    with subprocess.Popen([*docker, "start", "--attach", name], env=CLIENT_ENV,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as child:
        data = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    left = deadline - time.monotonic()
                    _require(left > 0 and selector.select(left), "isolated parser timed out")
                    block = os.read(child.stdout.fileno(), 65536)
                    if not block:
                        break
                    data.extend(block)
                    _require(len(data) <= MAX_RESPONSE, "isolated parser output exceeds its size limit")
            _require(child.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                     "isolated parser exited unsuccessfully")
        finally:
            if child.poll() is None:
                child.kill()
        return bytes(data)


def _verified_image(docker):
    image = _load(_control(docker, "image", "inspect", IMAGE_TAG), MAX_REQUEST)
    _require(type(image) is list and len(image) == 1, "parser image identity unavailable")
    image = image[0]
    _require(image["Id"] in (IMAGE, IMAGE_CONFIG)
             and (not image.get("Descriptor") or image["Descriptor"]["digest"] == IMAGE)
             and image["RootFS"]["Layers"] == [IMAGE_DIFF_ID]
             and image["Os"] == "linux" and image["Architecture"] == "amd64",
             "parser image identity differs")
    return image["Id"]


def _worker(root, request, timeout):
    docker = _docker_command(root)
    image = _verified_image(docker)
    name = "auditgava-parser-" + uuid4().hex
    mounts = {"/source": root / "source", "/opt/ingestion": root / "runtime", "/input": request}
    options = []
    for target, origin in mounts.items():
        _require("," not in str(origin) and origin.is_dir() and not origin.is_symlink(),
                 "parser mount differs")
        options += ["--mount", f"type=bind,source={origin},target={target},readonly"]
    argv = ["/usr/bin/env", "-i", *(f"{k}={v}" for k, v in WORKER_ENV.items()),
            "/opt/ingestion/bin/python", "-I", "-B", "/source/backend/seeding/parser_worker.py"]
    try:
        _control(docker, "create", "--name", name, "--platform=linux/amd64",
                 "--pull=never", "--network=none", "--entrypoint", argv[0],
                 "--read-only", "--user=65534:65534", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges", "--memory=2g", "--memory-swap=2g",
                 "--cpus=1", "--pids-limit=64", "--ipc=private",
                 "--log-driver=none", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,mode=1777,size=192m",
                 *options, image, *argv[1:])
        state, = _load(_control(docker, "inspect", name), MAX_REQUEST)
        limits = state["HostConfig"]
        _require(state["Image"] == image and state["Path"] == argv[0]
                 and state["Args"] == argv[1:] and state["Config"]["User"] == "65534:65534"
                 and limits["NetworkMode"] == "none" and limits["ReadonlyRootfs"] is True
                 and limits["Privileged"] is False and limits["CapDrop"] == ["ALL"]
                 and limits["SecurityOpt"] == ["no-new-privileges"]
                 and limits["Memory"] == limits["MemorySwap"] == 2 * 1024**3
                 and limits["NanoCpus"] == 10**9 and limits["PidsLimit"] == 64
                 and limits["IpcMode"] == "private" and limits["PidMode"] == ""
                 and not limits["Devices"] and limits["LogConfig"]["Type"] == "none"
                 and limits["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,nodev,mode=1777,size=192m"}
                 and len(state["Mounts"]) == len(mounts)
                 and {m["Destination"]: m["Source"] for m in state["Mounts"]
                      if m["Type"] == "bind" and m["RW"] is False}
                     == {target: str(origin) for target, origin in mounts.items()},
                 "isolated parser container differs")
        return _read_worker(docker, name, timeout)
    finally:
        matches = _control(docker, "ps", "-aq", "--filter", f"name=^/{name}$").strip()
        if matches:
            _control(docker, "rm", "-f", name)
            _require(not _control(docker, "ps", "-aq", "--filter", f"name=^/{name}$").strip(),
                     "isolated parser cleanup could not be verified")


def _call(operation, document, arguments, types, errors, timeout, root, *, returns=Any):
    _require(root.is_absolute() and root.is_dir() and not root.is_symlink(),
             "verified isolated parser runtime is unavailable")
    with tempfile.TemporaryDirectory(prefix="auditgava-parser-", dir=root) as directory:
        request = Path(directory)
        # Files are read-only for the worker. A private parent directory keeps
        # the staged copy away from other users of the host.
        request.chmod(0o755)
        try:
            digest = _capture(document, request / "document")
            kind = "bytes" if type(document) is bytes else "path"
            filename = "document" if kind == "bytes" else Path(document).name
            _require(filename not in ("", ".", "..")
                     and len(filename) <= 240 and not re.search(r"[\x00-\x1f/\\]", filename),
                     "invalid parser document name")
            raw = _dump({"operation": operation, "sha256": digest, "kind": kind,
                         "name": filename, "arguments": _encode(arguments, {})}, MAX_REQUEST)
            message = request / "request.json"
            message.write_bytes(raw)
            message.chmod(0o444)
            result = _load(_worker(root, request, timeout), MAX_RESPONSE)
            _require(type(result) is dict and result.get("sha256") == digest,
                     "parser result does not bind the document")
            if set(result) == {"sha256", "value"}:
                value = _decode(result["value"], types)
                _require(_shape(value, returns), "isolated parser result type differs")
                return value
            _require(set(result) == {"sha256", "error", "args", "reason", "detail"}
                     and type(result["error"]) is str and result["error"] in errors
                     and type(result["args"]) is list and all(type(v) is str for v in result["args"])
                     and all(v is None or type(v) is str for v in (result["reason"], result["detail"])),
                     "isolated decoder refused the document")
        except ParserIsolationError:
            raise
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError, RecursionError,
                subprocess.SubprocessError) as exc:
            raise ParserIsolationError("isolated parser request failed") from exc
    kind = errors[result["error"]]
    error = kind.__new__(kind)
    BaseException.__init__(error, *result["args"])
    for name in ("reason", "detail"):
        if result[name] is not None:
            setattr(error, name, result[name])
    raise error


def isolated(source, *, types=(), errors=(), method=False, timeout=300):
    """Route a fixed decoder using one path or byte input and plain arguments."""
    def decorate(function):
        operation = function.__module__ + ":" + function.__qualname__
        signature = inspect.signature(function)
        result_types = {t.__name__: t for t in types}
        known_errors = {t.__name__: t for t in (*errors, ValueError)}
        _OPERATIONS[operation] = (function, source, method, result_types, known_errors)

        @wraps(function)
        def invoke(*args, **kwargs):
            if _in_worker:
                return function(*args, **kwargs)
            root = os.environ.get("SEED_PARSER_ROOT")
            if root is None and os.environ.get("AUDIT_GITHUB_DATABASE_TLS") != "1":
                return function(*args, **kwargs)
            _require(root, "credentialed ingestion requires the isolated parser")
            inputs = dict(signature.bind(*args, **kwargs).arguments)
            document = getattr(inputs.pop("self"), source) if method else inputs.pop(source)
            returns = _annotations(function).get("return", Any)
            return _call(operation, document, inputs, result_types, known_errors, timeout, Path(root),
                         returns=returns)

        return invoke

    return decorate


@isolated("pdf_path")
def _containment_probe(pdf_path, writer_only):
    """A synthetic owned file tests runtime behavior on each runner."""
    import fcntl

    from .native_ocr import page_count, read_page

    status = Path("/proc/self/status").read_text()
    no_credentials = set(os.environ) <= set(WORKER_ENV) and not Path(writer_only).exists()
    no_socket = not Path("/var/run/docker.sock").exists()
    # Some kernels instantiate inactive fallback tunnel devices in a new
    # network namespace. Only loopback may be up.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        up = {name for _, name in socket.if_nameindex()
              if struct.unpack_from("H", fcntl.ioctl(
                  probe, 0x8913, struct.pack("256s", name.encode())), 16)[0] & 1}
    only_loopback = up == {"lo"}
    no_privilege = ("CapEff:\t0000000000000000" in status and "NoNewPrivs:\t1" in status
                    and "Seccomp:\t2" in status
                    and os.getuid() == os.getgid() == 65534)
    return {"pages": page_count(pdf_path), "ocr": "AUDIT 310327" in read_page(pdf_path, 1),
            "writer_isolated": no_credentials and no_socket and only_loopback and no_privilege}


def worker_main(input_dir):
    """Dispatch only trusted registered operations inside the sandbox."""
    global _in_worker
    request = _load((input_dir / "request.json").read_bytes(), MAX_REQUEST)
    _require(type(request) is dict and set(request) == {"operation", "kind", "name", "sha256", "arguments"}
             and request["kind"] in ("bytes", "path") and type(request["operation"]) is str,
             "invalid parser request")
    key = request["operation"]
    module, sep, name = key.partition(":")
    _require(sep == ":" and module in _ALLOWED_MODULES and re.fullmatch(r"[\w.]+", name),
             "unknown parser operation")
    importlib.import_module(module)
    _require(key in _OPERATIONS, "unregistered parser operation")
    function, source, method, types, errors = _OPERATIONS[key]
    with (input_dir / "document").open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    _require(digest == request["sha256"], "parser document hash differs")
    filename = request["name"]
    _require(type(filename) is str and filename not in ("", ".", "..")
             and len(filename) <= 240 and not re.search(r"[\x00-\x1f/\\]", filename),
             "invalid parser document name")
    document = input_dir / "document"
    args = _decode(request["arguments"], {})
    _require(type(args) is dict and all(type(k) is str for k in args), "invalid parser arguments")
    _in_worker = True
    try:
        if request["kind"] == "bytes":
            value = document.read_bytes()
        else:
            # Preserve the original basename for deterministic reader logic.
            value = Path(tempfile.mkdtemp(prefix="parser-input-")) / filename
            value.symlink_to(document)
        if method:
            owner = getattr(importlib.import_module(module), function.__qualname__.split(".")[0])
            args["self"] = owner(value)
        else:
            args[source] = value
        result = {"sha256": digest, "value": _encode(function(**args), types)}
    except Exception as exc:
        kind = type(exc).__name__
        _require(errors.get(kind) is type(exc), "isolated decoder failed")
        result = {"sha256": digest, "error": kind, "args": [str(v)[:600] for v in exc.args],
                  "reason": getattr(exc, "reason", None), "detail": getattr(exc, "detail", None)}
    finally:
        _in_worker = False
    return _dump(result, MAX_RESPONSE)

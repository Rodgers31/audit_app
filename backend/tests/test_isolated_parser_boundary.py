"""The credentialed parser must fail closed on untrusted input and output."""
import json
from pathlib import Path

import pytest

from seeding import isolated_parser as parser
from seeding.extractors.oag_blue_book import PageText


def test_writer_cannot_use_local_parser(monkeypatch, tmp_path):
    monkeypatch.delenv("SEED_PARSER_ROOT", raising=False)
    monkeypatch.setenv("AUDIT_GITHUB_DATABASE_TLS", "1")
    invoked = []

    @parser.isolated("path")
    def parse(path):
        invoked.append(path)

    with pytest.raises(parser.ParserIsolationError, match="requires the isolated parser"):
        parse(tmp_path / "report.pdf")
    assert not invoked


@pytest.mark.parametrize("kind", ["wrong_hash", "duplicate", "bad_record", "oversized_decimal", "outage"])
def test_worker_results_are_validated(monkeypatch, tmp_path, kind):
    def worker(_root, request, _timeout):
        digest = json.loads((request / "request.json").read_bytes())["sha256"]
        if kind == "wrong_hash":
            return b'{"sha256":"wrong","value":[]}'
        if kind == "duplicate":
            return ('{"sha256":"%s","value":[],"value":[]}' % digest).encode()
        if kind == "outage":
            raise OSError("synthetic transport error")
        value = ({"record": ["PageText", [False, "table text", "pdfplumber"]]}
                 if kind == "bad_record" else {"decimal": "1E+700"})
        return json.dumps({"sha256": digest, "value": value}).encode()

    monkeypatch.setattr(parser, "_worker", worker)
    with pytest.raises(parser.ParserIsolationError):
        parser._call("owned:fixture", b"owned", {}, {"PageText": PageText}, {}, 1, tmp_path)
    assert not list(tmp_path.iterdir())


def test_path_snapshot_preserves_name_and_rejects_symlinks(monkeypatch, tmp_path):
    path = tmp_path / "document"
    path.write_bytes(b"owned bytes")
    observed = []

    def worker(_root, request, _timeout):
        msg = json.loads((request / "request.json").read_bytes())
        observed.append((msg["kind"], msg["name"], (request / "document").read_bytes()))
        return json.dumps({"sha256": msg["sha256"], "value": 1}).encode()

    monkeypatch.setattr(parser, "_worker", worker)
    assert parser._call("owned:fixture", path, {}, {}, {}, 1, tmp_path) == 1
    assert observed == [("path", "document", b"owned bytes")]
    symlink = Path(tmp_path, "link.pdf")
    symlink.symlink_to(path)
    with pytest.raises(parser.ParserIsolationError):
        parser._call("owned:fixture", symlink, {}, {}, {}, 1, tmp_path)
    assert len(observed) == 1

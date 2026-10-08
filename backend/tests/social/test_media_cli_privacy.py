"""Observed-red parse leakage and argument bounds before any I/O."""
import json

import pytest

from scripts.social_media_browser_fixture import main as fixture_main
from social.media.maintenance import main as maintenance_main


@pytest.mark.parametrize('main,argv', [
    (maintenance_main, ['--database-url', 'fixture-private', '--limit', 'fixture-private-secret']),
    (maintenance_main, ['--database-url', 'fixture-private', '--unknown', 'fixture-private-secret']),
    (fixture_main, ['--seconds', 'fixture-private-secret']),
])
def test_bad_parse_does_not_echo_private_values(main, argv, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid arguments reached I/O')
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', forbidden)
    monkeypatch.setattr('scripts.social_media_browser_fixture.browser_fixture', forbidden)
    # Baseline argparse exits; the private parser instead returns a safe code.
    try:
        status = main(argv)
    except SystemExit as error:
        status = error.code
    captured = capsys.readouterr()
    assert status != 0
    assert 'fixture-private' not in captured.out + captured.err
    assert list(json.loads(captured.out)) == ['error_code']
    assert captured.err == ''


@pytest.mark.parametrize('argv', [
    (), None, True, [True], ['x'] * 17, ['x' * 2049], ['private\nvalue'], ['private\x7fvalue'],
])
@pytest.mark.parametrize('main', [maintenance_main, fixture_main])
def test_direct_cli_argument_bounds_before_io(main, argv, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid arguments reached I/O')
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', forbidden)
    monkeypatch.setattr('scripts.social_media_browser_fixture.browser_fixture', forbidden)
    # None means real process arguments; supply a malformed explicit process argv.
    monkeypatch.setattr('sys.argv', ['media', '--unknown', 'private-secret'])
    assert main(argv) != 0
    captured = capsys.readouterr()
    assert list(json.loads(captured.out)) == ['error_code']
    assert 'private' not in captured.out + captured.err


@pytest.mark.parametrize('mode', [[], ['--prepare-reconciliation'], ['--allow-cleanup']])
def test_explicit_empty_cursor_is_refused_before_engine(mode, monkeypatch, capsys):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Invalid cursor reached engine creation')
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', forbidden)
    assert maintenance_main(['--database-url', 'fixture-private', '--after-asset-id', '', *mode]) == 1
    assert calls == []
    assert list(json.loads(capsys.readouterr().out)) == ['error_code']

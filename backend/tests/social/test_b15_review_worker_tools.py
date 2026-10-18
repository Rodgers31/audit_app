"""Capacity evidence cannot omit lost operations or leak failed proxy clients."""
import ast
import importlib.util
from pathlib import Path
import socket
import pytest

ROOT = Path(__file__).resolve().parents[3]


def qualification():
    spec = importlib.util.spec_from_file_location('review_qualification', ROOT/'tools/worker_rehearsal/qualification.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_every_started_operation_needs_exactly_one_completion():
    starts = [{'request_id':'a','path':'/publish','started':10}, {'request_id':'b','path':'/publish','started':11}]
    completed = [{'request_id':'a','path':'/publish','completed':12}]
    with pytest.raises(ValueError): qualification().pairs(starts, completed, 1, 20)
    completed.append({'request_id':'b','path':'/publish','completed':13})
    assert len(qualification().pairs(starts, completed, 1, 20)) == 2


def test_failed_upstream_closes_accepted_socket_and_records_failure(monkeypatch):
    path = ROOT/'tools/worker_rehearsal/wire.py'
    tree = ast.parse(path.read_text())
    tree.body = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
        or isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'totals','lock'} for t in n.targets)]
    scope = {}; exec(compile(tree,str(path),'exec'),scope)
    def unavailable(*args, **kwargs): raise ConnectionRefusedError('inert upstream unavailable')
    monkeypatch.setattr(scope['socket'], 'create_connection', unavailable)
    client, peer = socket.socketpair()
    try:
        scope['serve'](client)
        assert client.fileno() == -1
        assert scope['totals']['connections'] == 1 and scope['totals']['active'] == 0
        assert scope['totals']['upstream_failures'] == 1
    finally: client.close(); peer.close()


@pytest.mark.parametrize('missing', [False, True])
def test_capacity_cannot_ignore_upstream_failure_measurement(missing):
    from test_worker_rehearsal_guards import evidence
    value = evidence()
    if missing:
        value[3].pop('upstream_failures', None)
        value[4].pop('upstream_failures', None)
    else:
        value[3]['upstream_failures'] = 0
        value[4]['upstream_failures'] = 1
    with pytest.raises((ValueError, KeyError)):
        qualification().assess(*value)

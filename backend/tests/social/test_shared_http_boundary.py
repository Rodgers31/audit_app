"""Feature routers share HTTP policy without importing each other's routes."""
import subprocess
import sys
from pathlib import Path


def test_social_http_policy_is_shared_without_a_router_cycle():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, '-c', '''
import socket
socket.socket.connect=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('Network disabled'))
from social import api, http_boundary
assert api.SocialRoute is http_boundary.SocialRoute
assert api.social_admin is http_boundary.social_admin
assert api.IdempotencyKey is http_boundary.IdempotencyKey
assert api.get_db is http_boundary.get_db
assert api.require_admin is http_boundary.require_admin
assert not hasattr(http_boundary, 'router')
print('shared boundary verified')
'''], cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'shared boundary verified'

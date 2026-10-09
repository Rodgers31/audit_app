"""Run lane tests with socket transports refused before application imports."""
import socket
import sys

import pytest


def refuse_socket(*args, **kwargs):
    raise AssertionError("Socket transport is forbidden in the helper lane")


socket.socket.connect = refuse_socket
socket.socket.connect_ex = refuse_socket
sys.exit(pytest.main(sys.argv[1:]))

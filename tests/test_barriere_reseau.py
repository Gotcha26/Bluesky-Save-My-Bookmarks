"""La barrière réseau de conftest.py bloque aussi urllib3 (donc requests) vers l'extérieur."""

import socket

import pytest
from urllib3.util import connection as urllib3_connection


def test_socket_externe_interdit():
    with pytest.raises(AssertionError, match="accès réseau réel interdit"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_urllib3_externe_interdit():
    with pytest.raises(AssertionError, match="accès réseau réel interdit"):
        urllib3_connection.create_connection(("example.com", 80), timeout=1)

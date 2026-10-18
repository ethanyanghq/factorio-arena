"""Checks for rcon.py that need no Factorio server.

Run:  uv run pytest tests/test_rcon.py -q

Each test is one behavior, named for it. A method still raising NotImplementedError
shows as a failure with that name, which is the TODO list. Fix the method, rerun.
"""

import os

import pytest

from factorio_arena import rcon
from factorio_arena.rcon import (
    AUTH_FAILED_ID,
    COMMAND,
    LOGIN,
    REPLY,
    RconClient,
    build_packet,
    parse_packet,
    recv_exactly,
)

PASSWORD = "secret"


class FakeServer:
    """Stands in for the socket to a Factorio server.

    sendall() records each packet and queues the reply the real server would send:
    login replies echo the request id, or AUTH_FAILED_ID if the password is wrong;
    command replies echo the id and carry the next scripted response as the body.
    recv() hands the queued bytes out at most `chunk_size` at a time, like a real
    socket may, and returns b"" when nothing is left, like a closed connection.
    """

    def __init__(self, responses=(), chunk_size=3):
        self.responses = list(responses)
        self.chunk_size = chunk_size
        self.sent = []
        self.inbox = b""
        self.is_closed = False

    def sendall(self, packet):
        request_id, packet_type, body = parse_packet(packet[4:])
        self.sent.append((request_id, packet_type, body))
        if packet_type == LOGIN:
            reply_id = request_id if body == PASSWORD else AUTH_FAILED_ID
            self.inbox += build_packet(reply_id, 2, "")
        elif packet_type == COMMAND:
            self.inbox += build_packet(request_id, REPLY, self.responses.pop(0))

    def recv(self, n):
        chunk = self.inbox[: min(n, self.chunk_size)]
        self.inbox = self.inbox[len(chunk) :]
        return chunk

    def close(self):
        self.is_closed = True


@pytest.fixture
def fake_server(monkeypatch):
    """Make socket.create_connection inside rcon.py return a FakeServer.

    The test gets the FakeServer back so it can script responses and inspect what the
    client sent.
    """
    server = FakeServer()
    monkeypatch.setattr(rcon.socket, "create_connection", lambda address: server)
    return server


# ---- packet functions ---------------------------------------------------------------


def test_build_packet_lays_out_fields_in_spec_order():
    assert build_packet(1, 2, "hi") == b"\x0c\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00hi\x00\x00"


def test_parse_packet_reverses_build_packet():
    assert parse_packet(build_packet(7, 3, "secret")[4:]) == (7, 3, "secret")


def test_recv_exactly_collects_across_small_chunks():
    server = FakeServer(chunk_size=3)
    server.inbox = b"abcdefg"
    assert recv_exactly(server, 7) == b"abcdefg"


def test_recv_exactly_leaves_unrequested_bytes_in_the_socket():
    server = FakeServer(chunk_size=100)
    server.inbox = b"abcdefg"
    assert recv_exactly(server, 4) == b"abcd"
    assert server.inbox == b"efg"


def test_recv_exactly_raises_when_connection_closes_early():
    server = FakeServer()
    server.inbox = b"ab"
    with pytest.raises(ConnectionError):
        recv_exactly(server, 5)


# ---- client -------------------------------------------------------------------------


def test_init_logs_in_with_the_password(fake_server):
    RconClient("127.0.0.1", 27015, PASSWORD)
    assert fake_server.sent == [(1, LOGIN, PASSWORD)]


def test_init_raises_when_password_is_rejected(fake_server):
    with pytest.raises(PermissionError):
        RconClient("127.0.0.1", 27015, "wrong")


def test_send_uses_a_fresh_id_each_time(fake_server):
    fake_server.responses = ["", ""]
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    first = client._send(COMMAND, "a")
    second = client._send(COMMAND, "b")
    assert (first, second) == (2, 3)
    assert fake_server.sent[1:] == [(2, COMMAND, "a"), (3, COMMAND, "b")]


def test_read_packet_returns_id_type_and_body(fake_server):
    fake_server.responses = ["pong"]
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    client._send(COMMAND, "ping")
    assert client._read_packet() == (2, REPLY, "pong")


def test_read_packet_survives_a_reply_split_one_byte_at_a_time(fake_server):
    fake_server.chunk_size = 1
    fake_server.responses = ["pong"]
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    client._send(COMMAND, "ping")
    assert client._read_packet() == (2, REPLY, "pong")


def test_command_returns_the_reply_body(fake_server):
    fake_server.responses = ["2.0.77"]
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    assert client.command("/version") == "2.0.77"


def test_command_returns_empty_string_when_server_prints_nothing(fake_server):
    fake_server.responses = [""]
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    assert client.command("/c x = 1") == ""


def test_close_closes_the_socket(fake_server):
    client = RconClient("127.0.0.1", 27015, PASSWORD)
    client.close()
    assert fake_server.is_closed


# ---- live server (opt-in: `make test-server`) ----------------------------------------


@pytest.mark.server
def test_version_round_trips_against_a_live_server():
    password = os.environ.get("FACTORIO_RCON_PASSWORD")
    assert password, "set FACTORIO_RCON_PASSWORD to the value in .env before running"
    client = RconClient("127.0.0.1", 27015, password)
    try:
        assert client.command("/version").startswith("2.0")
    finally:
        client.close()

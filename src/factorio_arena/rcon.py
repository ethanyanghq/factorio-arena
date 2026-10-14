"""RCON client for a headless Factorio server.

RCON is a TCP protocol: send a console command as text, get text back. Every message
in either direction is one packet with this layout:

    size   4 bytes, little-endian int: how many bytes follow this field
    id     4 bytes, little-endian int: we pick it; the server's reply echoes it back
    type   4 bytes, little-endian int: 3 = login, 2 = run a command, 0 = reply
    body   the text as bytes, then one zero byte
    pad    one more zero byte

Usage:

    client = RconClient("127.0.0.1", 27015, "password")
    print(client.command("/version"))
    client.close()

The module-level functions are copied from scratch/practice.py and work. The class
methods have a body of `raise NotImplementedError`; each is a few of those functions
glued together.
"""

import socket
import struct
from typing import Protocol

LOGIN = 3
COMMAND = 2
REPLY = 0
AUTH_FAILED_ID = -1
SIZE_FIELD_LENGTH = 4


# ---- packet encoding and decoding: pure functions, no socket --------------------------


def encode_int(n: int) -> bytes:
    """Int to 4 little-endian bytes. encode_int(1) returns b"\\x01\\x00\\x00\\x00"."""
    return struct.pack("<i", n)


def decode_int(b: bytes) -> int:
    """4 little-endian bytes to an int. Reverse of encode_int."""
    return struct.unpack("<i", b)[0]


def encode_body(s: str) -> bytes:
    """Text to bytes, plus the zero byte RCON puts after a body.

    encode_body("hi") returns b"hi\\x00"
    """
    sb = s.encode()
    return sb + b"\x00"


def split_first_four(b: bytes) -> tuple[bytes, bytes]:
    """Return (first four bytes, the rest).

    split_first_four(b"abcdefg") returns (b"abcd", b"efg")
    """
    a = b[:4]
    b = b[4:]
    return (a, b)


def build_packet(request_id: int, packet_type: int, body: str) -> bytes:
    """Return one bytes object: a complete packet, ready to send.

    build_packet(1, 2, "hi") returns the 16-byte value
    b"\\x0c\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00hi\\x00\\x00"
    """
    id_bytes = encode_int(request_id)
    type_bytes = encode_int(packet_type)
    body_bytes = encode_body(body)
    pad = b"\x00"

    after_size = id_bytes + type_bytes + body_bytes + pad
    size_bytes = encode_int(len(after_size))

    return size_bytes + after_size


def parse_packet(payload: bytes) -> tuple[int, int, str]:
    """Take apart everything after the size field. Return (request_id, packet_type, body).

    parse_packet(b"\\x05\\x00\\x00\\x00\\x00\\x00\\x00\\x00ok\\x00\\x00") returns (5, 0, "ok")
    """
    id_bytes, rest = split_first_four(payload)
    type_bytes, body_bytes = split_first_four(rest)
    return (decode_int(id_bytes), decode_int(type_bytes), body_bytes[:-2].decode())


class Receiver(Protocol):
    """Anything with a socket-style recv: a real socket, or a fake one in tests."""

    def recv(self, n: int, /) -> bytes: ...


def recv_exactly(sock: Receiver, n: int) -> bytes:
    """Return exactly n bytes read from sock, as one bytes object.

    sock.recv(k) returns up to k bytes, or b"" once the connection has closed. Loop until
    you have n. If the connection closes first, raise ConnectionError saying how many
    bytes you wanted and how many you got.
    """
    chunks = []
    received = 0
    while received < n:
        chunk = sock.recv(n - received)
        if chunk == b"":
            raise ConnectionError(f"wanted {n} bytes, got {received}")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


# ---- the client: one object per connection ------------------------------------------


class RconClient:
    """One open RCON connection, logged in and ready to run commands.

    Attributes:
        link: the socket for this connection.
        next_id: the request id to put in the next packet sent. Starts at 1 and goes
            up by one with every packet, so each packet has a different id.
    """

    def __init__(self, host: str, port: int, password: str) -> None:
        """Connect to the server and log in.

        Args:
            host: the server's address, e.g. "127.0.0.1".
            port: the server's RCON port, e.g. 27015.
            password: the RCON password.

        Raises:
            PermissionError: if the server rejects the password.
        """
        self.link = socket.create_connection((host, port))
        self.next_id = 1
        self._login(password)

    def command(self, text: str) -> str:
        """Run one console command on the server and give back what it printed.

        Args:
            text: the command, e.g. "/version".

        Returns:
            The server's reply, as a str. May be empty for commands that print nothing.
        """
        self._send(COMMAND, text)
        return self._read_packet()[2]

    def close(self) -> None:
        """Close the connection. The client cannot be used after this."""
        self.link.close()

    def _login(self, password: str) -> None:
        """Send the password to the server and check that it was accepted.

        Args:
            password: the RCON password.

        Raises:
            PermissionError: if the reply's request id is AUTH_FAILED_ID, which is how
                the server says the password was wrong.
        """
        self._send(LOGIN, password)
        if self._read_packet()[0] == AUTH_FAILED_ID:
            raise PermissionError("The password is wrong.")

    def _send(self, packet_type: int, body: str) -> int:
        """Send one packet to the server, using a fresh request id.

        Args:
            packet_type: LOGIN or COMMAND.
            body: the packet's text.

        Returns:
            The request id the packet was sent with, so the caller can match the reply.
        """
        id_request = self.next_id
        self.next_id += 1
        packet = build_packet(id_request, packet_type, body)
        self.link.sendall(packet)
        return id_request

    def _read_packet(self) -> tuple[int, int, str]:
        """Read one whole packet from the server.

        Returns:
            A tuple (request_id, packet_type, body), the same as parse_packet gives.
        """
        size = decode_int(recv_exactly(self.link, 4))
        packet = parse_packet(recv_exactly(self.link, size))
        return packet

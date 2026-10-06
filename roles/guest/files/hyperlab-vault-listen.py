#!/usr/bin/python3
"""hyperlab-vault-listen - the key vault's only door (ADR 0048).

Runs inside the vault Machine, which has no network interface. Listens on
one vsock port, accepts only the host (context id 2), and passes to the
local ssh-agent the same two requests the host relay passes: list
identities, and sign. Anything else is refused here too, so a host relay
that went wrong still could not add, remove or lock keys.
"""

from __future__ import annotations

import os
import socket
import struct
import sys
import threading

REQUEST_IDENTITIES = 11
SIGN_REQUEST = 13
FAILURE = 5
FRAME_LIMIT = 256 << 10
HOST_CID = 2
AGENT = os.environ.get("HYPERLAB_VAULT_AGENT", "/run/hyperlab-vault/agent.sock")
PORT = int(os.environ.get("HYPERLAB_VAULT_PORT", "7401"))


class Refused(RuntimeError):
    pass


def read_exact(sock, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError("connection closed")
        data += chunk
    return data


def read_frame(sock) -> bytes:
    (length,) = struct.unpack(">I", read_exact(sock, 4))
    if length == 0 or length > FRAME_LIMIT:
        raise Refused(f"frame of {length} bytes")
    return read_exact(sock, length)


def write_frame(sock, payload: bytes) -> None:
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def serve(client, agent_connect) -> None:
    try:
        while True:
            request = read_frame(client)
            if request[0] not in (REQUEST_IDENTITIES, SIGN_REQUEST):
                write_frame(client, bytes([FAILURE]))
                continue
            agent = agent_connect()
            try:
                write_frame(agent, request)
                answer = read_frame(agent)
            finally:
                agent.close()
            write_frame(client, answer)
    except (EOFError, Refused, OSError):
        pass
    finally:
        client.close()


def agent_connect():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(AGENT)
    return sock


def main() -> int:
    server = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    server.bind((socket.VMADDR_CID_ANY, PORT))
    server.listen(4)
    while True:
        client, (cid, _port) = server.accept()
        if cid != HOST_CID:
            client.close()
            continue
        threading.Thread(target=serve, args=(client, agent_connect), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())

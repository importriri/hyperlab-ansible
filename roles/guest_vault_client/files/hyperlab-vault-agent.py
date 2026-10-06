#!/usr/bin/python3
"""hyperlab-vault-agent - a key vault client's SSH agent socket (ADR 0048).

Listens on a UNIX socket in the user's runtime directory and carries each
connection, byte for byte, to the host relay's vsock port. It decides
nothing: the host relay names this Machine by its vsock context id, asks
the operator before every signature, and refuses everything else.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

HOST_CID = 2
PORT = int(os.environ.get("HYPERLAB_VAULT_RELAY_PORT", "7400"))


def pump(source, target) -> None:
    try:
        while chunk := source.recv(65536):
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def carry(client, relay_connect) -> None:
    try:
        relay = relay_connect()
    except OSError:
        client.close()
        return
    back = threading.Thread(target=pump, args=(relay, client), daemon=True)
    back.start()
    pump(client, relay)
    back.join()
    relay.close()
    client.close()


def relay_connect():
    sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    sock.connect((HOST_CID, PORT))
    return sock


def listen(path: Path):
    path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.is_socket():
        path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(old)
    server.listen(8)
    return server


def main() -> int:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        print("hyperlab-vault-agent: XDG_RUNTIME_DIR is not set", file=sys.stderr)
        return 2
    server = listen(Path(runtime) / "hyperlab-vault.sock")
    while True:
        client, _ = server.accept()
        threading.Thread(target=carry, args=(client, relay_connect), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())

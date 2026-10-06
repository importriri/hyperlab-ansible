#!/usr/bin/python3
"""hyperlab-vault-relay - the host side of the key vault (ADR 0048).

A client Machine's SSH agent socket forwards over virtio-vsock to this
relay. The relay names the client by the vsock context id libvirt assigned
to its domain, never by anything the guest says, and passes only two agent
requests to the vault Machine: list identities, and sign. Every sign
request waits for the operator's confirmation; no answer is a refusal.
Every other request (add, remove, lock, extensions) is refused here and
never reaches the vault.

Configuration: /etc/hyperlab/vault.json
  {"listen_port": 7400, "vault_domain": "vault", "vault_port": 7401,
   "confirm_command": ["/usr/local/bin/hyperlab-vault-confirm"],
   "confirm_timeout": 30, "allow_minutes_max": 10}
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REQUEST_IDENTITIES = 11
IDENTITIES_ANSWER = 12
SIGN_REQUEST = 13
SIGN_RESPONSE = 14
FAILURE = 5
FRAME_LIMIT = 256 << 10
CONFIG = Path(os.environ.get("HYPERLAB_VAULT_CONFIG", "/etc/hyperlab/vault.json"))
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")


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


def failure() -> bytes:
    return bytes([FAILURE])


def read_string(payload: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(payload):
        raise Refused("truncated string length")
    (length,) = struct.unpack(">I", payload[offset:offset + 4])
    end = offset + 4 + length
    if end > len(payload):
        raise Refused("truncated string")
    return payload[offset + 4:end], end


def fingerprint(key_blob: bytes) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(key_blob).digest()).decode().rstrip("=")


def identities(answer: bytes) -> dict[str, str]:
    """Fingerprint to comment, from an identities answer."""
    if not answer or answer[0] != IDENTITIES_ANSWER or len(answer) < 5:
        return {}
    (count,) = struct.unpack(">I", answer[1:5])
    offset, found = 5, {}
    for _ in range(min(count, 1000)):
        blob, offset = read_string(answer, offset)
        comment, offset = read_string(answer, offset)
        found[fingerprint(blob)] = comment.decode("utf-8", "replace")[:200]
    return found


class Allowances:
    """Time-limited allowances, per Machine and key, granted by the operator."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.until: dict[tuple[str, str], float] = {}
        self.lock = threading.Lock()

    def granted(self, machine: str, key: str) -> bool:
        with self.lock:
            return self.until.get((machine, key), 0) > self.clock()

    def grant(self, machine: str, key: str, minutes: float) -> None:
        with self.lock:
            self.until[(machine, key)] = self.clock() + minutes * 60


class Relay:
    def __init__(self, config: dict, vault_connect, confirm, allowances: Allowances | None = None):
        self.config = config
        self.vault_connect = vault_connect
        self.confirm = confirm
        self.allowances = allowances or Allowances()
        self.known: dict[str, str] = {}
        # One question on screen at a time: a client cannot stack prompts.
        self.asking = threading.Lock()

    def ask_vault(self, request: bytes) -> bytes:
        vault = self.vault_connect()
        # A vault that stops answering ends this request, not the thread.
        vault.settimeout(float(self.config.get("vault_timeout", 30)))
        try:
            write_frame(vault, request)
            return read_frame(vault)
        finally:
            vault.close()

    def decide(self, machine: str, key: str) -> bool:
        if self.allowances.granted(machine, key):
            return True
        with self.asking:
            if self.allowances.granted(machine, key):
                return True
            answer = self.confirm(machine, key, self.known.get(key, "unknown key"))
        if answer == "deny" or answer is None:
            return False
        if answer.startswith("allow-minutes:"):
            minutes = min(float(answer.split(":", 1)[1]), float(self.config.get("allow_minutes_max", 10)))
            self.allowances.grant(machine, key, minutes)
        return answer == "allow-once" or answer.startswith("allow-minutes:")

    def handle(self, request: bytes, machine: str) -> bytes:
        kind = request[0]
        if kind == REQUEST_IDENTITIES:
            answer = self.ask_vault(request)
            self.known.update(identities(answer))
            return answer
        if kind == SIGN_REQUEST:
            blob, offset = read_string(request, 1)
            read_string(request, offset)  # the data must be well formed
            key = fingerprint(blob)
            if not self.decide(machine, key):
                log(f"{machine}: signature with {key} refused")
                return failure()
            log(f"{machine}: signature with {key} allowed")
            return self.ask_vault(request)
        log(f"{machine}: agent request {kind} refused at the host")
        return failure()

    def serve(self, client, machine: str) -> None:
        try:
            while True:
                request = read_frame(client)
                write_frame(client, self.handle(request, machine))
        except (EOFError, Refused, OSError) as exc:
            if not isinstance(exc, EOFError):
                log(f"{machine}: connection closed: {exc}")
        finally:
            client.close()


def log(message: str) -> None:
    print(f"hyperlab-vault-relay: {message}", flush=True)


def vsock_domains(run=subprocess.run) -> dict[int, str]:
    """Each running domain's vsock context id, from libvirt's own definition."""
    listing = run(["virsh", "--connect", "qemu:///system", "-r", "list", "--name"],
                  capture_output=True, text=True, check=False)
    found = {}
    for name in listing.stdout.split():
        if not DOMAIN_RE.fullmatch(name):
            continue
        xml = run(["virsh", "--connect", "qemu:///system", "-r", "dumpxml", name],
                  capture_output=True, text=True, check=False).stdout
        try:
            cid = ET.fromstring(xml).find("./devices/vsock/cid")
        except ET.ParseError:
            continue
        if cid is not None and str(cid.get("address", "")).isdigit():
            found[int(cid.get("address"))] = name
    return found


def confirm_command(config: dict):
    """Ask the helper; anything but a reviewed answer in time is no answer."""
    def confirm(machine: str, key: str, comment: str):
        try:
            helper = subprocess.Popen([*config["confirm_command"], machine, key, comment], stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True,
                                      start_new_session=True)
        except OSError:
            return None
        try:
            output, _ = helper.communicate(timeout=int(config.get("confirm_timeout", 30)))
        except subprocess.TimeoutExpired:
            # The whole group, so a dialog the helper started closes too.
            os.killpg(helper.pid, signal.SIGKILL)
            helper.wait()
            return None
        answer = output.strip()
        if helper.returncode != 0 or not re.fullmatch(r"deny|allow-once|allow-minutes:[0-9]{1,2}", answer):
            return None
        return answer
    return confirm


def main() -> int:
    config = json.loads(CONFIG.read_text())
    relay_vault_domain = config["vault_domain"]

    def vault_connect():
        cids = {name: cid for cid, name in vsock_domains().items()}
        if relay_vault_domain not in cids:
            raise Refused("the vault Machine is not running")
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        sock.connect((cids[relay_vault_domain], int(config["vault_port"])))
        return sock

    relay = Relay(config, vault_connect, confirm_command(config))
    server = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    server.bind((socket.VMADDR_CID_HOST, int(config["listen_port"])))
    server.listen(8)
    log(f"listening on vsock port {config['listen_port']}")
    while True:
        client, (cid, _port) = server.accept()
        machine = vsock_domains().get(cid)
        if machine is None or machine == relay_vault_domain:
            log(f"connection from unknown or vault context id {cid} refused")
            client.close()
            continue
        threading.Thread(target=relay.serve, args=(client, machine), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The key vault's host relay passes only what it must (ADR 0048).

Run against a fake vault agent over socket pairs:

  1. a client's identity list reaches the vault and comes back;
  2. a signature is forwarded only after the operator allows it: once (and
     asked again next time) or for a few minutes, capped, per Machine and
     key; a refusal or no answer never reaches the vault;
  3. adding, removing or locking keys and extensions are refused at the
     host and never reach the vault;
  4. an oversized or malformed request ends the connection without
     reaching the vault, and a vault that stops answering ends it in time;
  5. the client is named by the vsock context id in its domain's own
     definition, and the confirmation helper's answer must be one of the
     reviewed words, in time: a late helper is killed with what it started;
  6. one question at a time: requests waiting behind a question see its
     allowance instead of asking again;
  7. the dialog shows the Machine, key and comment as plain text, and
     anything but a known button is a refusal;
  8. the role installs a user unit that starts on the hardened kernel (no
     sandboxing that needs a user namespace) and is a registered brick.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vault_relay", ROOT / "roles/host_vault/files/hyperlab-vault-relay.py")
relay_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay_module)
R = relay_module
spec = importlib.util.spec_from_file_location("vault_confirm", ROOT / "roles/host_vault/files/hyperlab-vault-confirm.py")
confirm_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(confirm_module)

KEY = b"\x00\x00\x00\x0bssh-ed25519" + b"\x00\x00\x00\x20" + b"k" * 32


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def string(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def sign_request() -> bytes:
    return bytes([R.SIGN_REQUEST]) + string(KEY) + string(b"data to sign") + struct.pack(">I", 0)


class FakeVault:
    def __init__(self):
        self.received: list[int] = []

    def connect(self):
        ours, theirs = socket.socketpair()

        def answer():
            try:
                request = R.read_frame(theirs)
            except EOFError:
                return
            self.received.append(request[0])
            if request[0] == R.REQUEST_IDENTITIES:
                payload = bytes([R.IDENTITIES_ANSWER]) + struct.pack(">I", 1) + string(KEY) + string(b"sid@vault")
            else:
                payload = bytes([R.SIGN_RESPONSE]) + string(b"signature")
            R.write_frame(theirs, payload)
            theirs.close()

        threading.Thread(target=answer, daemon=True).start()
        return ours


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(answers):
    vault = FakeVault()
    asked = []

    def confirm(machine, key, comment):
        asked.append((machine, key, comment))
        return answers.pop(0) if answers else None

    clock = Clock()
    relay = R.Relay({"allow_minutes_max": 10}, vault.connect, confirm, R.Allowances(clock=clock))
    return relay, vault, asked, clock


def main() -> int:
    relay, vault, asked, clock = make(["deny", "allow-once", None, "allow-minutes:99"])
    answer = relay.handle(bytes([R.REQUEST_IDENTITIES]), "dev-01")
    require(answer[0] == R.IDENTITIES_ANSWER and vault.received == [R.REQUEST_IDENTITIES],
            "the identity list did not reach the vault")
    key = R.fingerprint(KEY)
    require(relay.known.get(key) == "sid@vault", "the key's comment is not known for the confirmation")

    require(relay.handle(sign_request(), "dev-01") == R.failure() and R.SIGN_REQUEST not in vault.received,
            "a refused signature reached the vault")
    require(asked[-1] == ("dev-01", key, "sid@vault"), "the confirmation does not name the Machine and key")
    require(relay.handle(sign_request(), "dev-01")[0] == R.SIGN_RESPONSE, "an allowed signature was not forwarded")
    require(relay.handle(sign_request(), "dev-01") == R.failure(), "no answer was taken as consent")
    require(len(asked) == 3, "allow-once was remembered")

    require(relay.handle(sign_request(), "dev-01")[0] == R.SIGN_RESPONSE, "allow-minutes did not allow")
    asked_before = len(asked)
    clock.now += 5 * 60
    require(relay.handle(sign_request(), "dev-01")[0] == R.SIGN_RESPONSE and len(asked) == asked_before,
            "an allowance within its minutes asked again")
    require(relay.handle(sign_request(), "srv-01") == R.failure() and len(asked) == asked_before + 1,
            "an allowance for one Machine was used by another")
    clock.now += 6 * 60
    relay.handle(sign_request(), "dev-01")
    require(len(asked) == asked_before + 2, "an allowance outlived its cap of 10 minutes")

    relay, vault, asked, _ = make(["allow-once"] * 10)
    for kind in (17, 18, 19, 22, 23, 25, 27):
        require(relay.handle(bytes([kind]) + b"\x00" * 8, "dev-01") == R.failure(), f"agent request {kind} passed")
    require(vault.received == [] and asked == [], "a refused request reached the vault or asked the operator")

    for frame in (struct.pack(">I", R.FRAME_LIMIT + 1), struct.pack(">I", 0),
                  struct.pack(">I", 6) + bytes([R.SIGN_REQUEST]) + b"\x00\x00\x00\x09\x01"):
        relay, vault, asked, _ = make(["allow-once"])
        client, server = socket.socketpair()
        client.sendall(frame)
        client.shutdown(socket.SHUT_WR)
        relay.serve(server, "dev-01")
        require(vault.received == [], f"a malformed frame reached the vault: {frame!r}")
        client.close()

    held = []

    def silent_vault():
        ours, theirs = socket.socketpair()
        held.append(theirs)
        return ours

    relay = R.Relay({"vault_timeout": 0.5}, silent_vault, lambda *_: "allow-once")
    client, server = socket.socketpair()
    R.write_frame(client, bytes([R.REQUEST_IDENTITIES]))
    started = time.monotonic()
    relay.serve(server, "dev-01")
    require(time.monotonic() - started < 5, "a silent vault held the client's connection")
    client.close()

    xml = ("<domain><devices><vsock model='virtio'><cid auto='yes' address='{cid}'/></vsock>"
           "</devices></domain>")

    def fake_run(argv, **_):
        if "list" in argv:
            return SimpleNamespace(stdout="dev-01\nvault\n../evil\n", returncode=0)
        name = argv[-1]
        return SimpleNamespace(stdout=xml.format(cid={"dev-01": 3, "vault": 4}.get(name, 9)), returncode=0)

    require(R.vsock_domains(run=fake_run) == {3: "dev-01", 4: "vault"}, "the context ids are not read from libvirt")

    with tempfile.TemporaryDirectory() as td:
        for output, expected in (("allow-once\n", "allow-once"), ("allow-minutes:5", "allow-minutes:5"),
                                 ("yes", None), ("allow-minutes:999", None), ("deny", "deny")):
            helper = Path(td) / "confirm"
            helper.write_text(f"#!/bin/sh\nprintf '%s' '{output}'\n")
            helper.chmod(0o755)
            confirm = R.confirm_command({"confirm_command": [str(helper)], "confirm_timeout": 5})
            require(confirm("dev-01", "SHA256:x", "c") == expected, f"the helper answer {output!r} was misread")

        marker = Path(td) / "child"
        helper.write_text(f"#!/bin/sh\nsleep 30 & echo $! > {marker}\nwait\n")
        started = time.monotonic()
        confirm = R.confirm_command({"confirm_command": [str(helper)], "confirm_timeout": 1})
        require(confirm("dev-01", "SHA256:x", "c") is None and time.monotonic() - started < 10,
                "a late helper was waited for or taken as an answer")
        child = int(marker.read_text())
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("the late helper's own child was left running")

    relay, vault, asked, _ = make([])

    def slow_confirm(machine, key, comment):
        asked.append(machine)
        time.sleep(0.3)
        return "allow-minutes:5"

    relay.confirm = slow_confirm
    relay.known[R.fingerprint(KEY)] = "sid@vault"
    workers = [threading.Thread(target=relay.handle, args=(sign_request(), "dev-01")) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    require(asked == ["dev-01"], f"waiting requests asked again: {asked}")

    shown = []

    def fake_dialog(argv, **_):
        shown.append(argv[argv.index("--text") + 1])
        return SimpleNamespace(stdout=fake_dialog.button + "\n", returncode=0)

    for button, expected in (("Deny", "deny"), ("Allow once", "allow-once"), ("Allow 5 minutes", "allow-minutes:5"),
                             ("", "deny"), ("allow-once", "deny")):
        fake_dialog.button = button
        got = confirm_module.answer(["dev-01", "SHA256:x", "<b>me</b>\x1b[2J"], run=fake_dialog)
        require(got == expected, f"the button {button!r} gave {got!r}")
    require("<b>" not in shown[-1] and "&lt;b&gt;me&lt;/b&gt;" in shown[-1] and "\x1b" not in shown[-1],
            "the comment reached the dialog as markup or with control characters")
    require(confirm_module.answer(["dev-01"], run=fake_dialog) == "deny", "a malformed call was not refused")

    for code in (1, -15):
        for button in ("Allow once", "Allow 5 minutes"):
            def failed_dialog(argv, *, output=button, status=code, **_):
                return SimpleNamespace(stdout=output + "\n", returncode=status)

            require(confirm_module.answer(["dev-01", "SHA256:x", "c"], run=failed_dialog) == "deny",
                    f"a failed dialog (exit {code}) authorized {button!r}")

    def missing_dialog(argv, **_):
        raise FileNotFoundError(argv[0])

    require(confirm_module.answer(["dev-01", "k", "c"], run=missing_dialog) == "deny", "no dialog was not a refusal")

    unit = (ROOT / "roles/host_vault/templates/hyperlab-vault-relay.service.j2").read_text()
    for needs_userns in ("PrivateTmp", "ProtectSystem", "ProtectHome", "PrivateUsers", "PrivateDevices"):
        require(f"{needs_userns}=" not in unit, f"the user unit uses {needs_userns}, which needs a user namespace")
    require("RestrictAddressFamilies=AF_VSOCK AF_UNIX" in unit and "NoNewPrivileges=yes" in unit,
            "the relay unit lost its restrictions")
    bricks = (ROOT / "group_vars/all/bricks.yml").read_text()
    require("  host_vault: [kvm_host]" in bricks and "  host_vault: playbooks/host-vault.yml" in bricks,
            "host_vault is not a registered brick")
    print("Key vault relay contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

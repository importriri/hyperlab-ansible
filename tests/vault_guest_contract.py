#!/usr/bin/env python3
"""The key vault's two guest ends (ADR 0048).

  1. The vault's listener passes only identity listing and signing to its
     ssh-agent; anything else is refused without reaching the agent, and an
     oversized frame ends the connection.
  2. A client's agent socket carries bytes both ways and decides nothing;
     its socket is the user's alone, and a relay it cannot reach closes the
     client's connection.
  3. Only the vault's cloud-init carries the listener, verbatim, its agent
     unit (the key made on first boot, loaded into an agent whose socket the
     listener uses) and its listener unit, with shell dollars escaped from
     systemd; the ports agree between the vault, the host relay and the
     client.
  4. A client keeps its own default agent unless the vault is asked for.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import stat
import struct
import sys
import tempfile
import threading
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import guest_contract  # noqa: E402


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LISTEN = load("vault_listen", "roles/guest/files/hyperlab-vault-listen.py")
AGENT = load("vault_agent", "roles/guest_vault_client/files/hyperlab-vault-agent.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_listener() -> None:
    seen = []

    def agent_connect():
        ours, theirs = socket.socketpair()

        def answer():
            request = LISTEN.read_frame(theirs)
            seen.append(request[0])
            LISTEN.write_frame(theirs, bytes([request[0] + 1]))
            theirs.close()

        threading.Thread(target=answer, daemon=True).start()
        return ours

    client, server = socket.socketpair()
    worker = threading.Thread(target=LISTEN.serve, args=(server, agent_connect), daemon=True)
    worker.start()
    answers = []
    for kind in (11, 13, 17, 19, 22, 25):
        LISTEN.write_frame(client, bytes([kind]) + b"\0\0\0\0")
        answers.append(LISTEN.read_frame(client)[0])
    require(seen == [11, 13], f"the listener passed {seen} to the agent")
    require(answers == [12, 14, 5, 5, 5, 5], f"the listener answered {answers}")
    client.sendall(struct.pack(">I", LISTEN.FRAME_LIMIT + 1))
    worker.join(5)
    require(not worker.is_alive(), "an oversized frame did not end the connection")
    client.close()
    source = (ROOT / "roles/guest/files/hyperlab-vault-listen.py").read_text()
    require("if cid != HOST_CID" in source and "VMADDR_CID_ANY" in source,
            "the listener does not accept only the host")


def check_agent() -> None:
    relay_side = []

    def relay_connect():
        ours, theirs = socket.socketpair()
        relay_side.append(theirs)
        return ours

    client, server = socket.socketpair()
    worker = threading.Thread(target=AGENT.carry, args=(server, relay_connect), daemon=True)
    worker.start()
    client.sendall(b"\0\0\0\1\x0b")
    for _ in range(100):
        if relay_side:
            break
        threading.Event().wait(0.01)
    relay = relay_side[0]
    require(relay.recv(16) == b"\0\0\0\1\x0b", "the request did not reach the relay unchanged")
    relay.sendall(b"\0\0\0\1\x0c")
    require(client.recv(16) == b"\0\0\0\1\x0c", "the answer did not come back unchanged")
    client.shutdown(socket.SHUT_WR)
    relay.close()
    worker.join(5)
    require(not worker.is_alive(), "the connection outlived both ends")
    client.close()

    def unreachable():
        raise ConnectionRefusedError("no relay")

    client, server = socket.socketpair()
    AGENT.carry(server, unreachable)
    require(client.recv(16) == b"", "an unreachable relay left the client waiting")
    client.close()

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "run" / "hyperlab-vault.sock"
        server = AGENT.listen(path)
        mode = stat.S_IMODE(path.stat().st_mode)
        require(mode & 0o077 == 0, f"the agent socket is open to others: {oct(mode)}")
        require(stat.S_IMODE(path.parent.stat().st_mode) == 0o700, "the socket directory is not private")
        server.close()


def user_data(changes: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_path, store = guest_contract.standard_fixture(root)
        spec = yaml.safe_load(spec_path.read_text())
        spec.update({"lifecycle": "permanent", **changes})
        guest_contract.write_yaml(spec_path, spec)
        plan = guest_contract.build_plan(root, spec_path, store)
    text = guest_contract.template_env().get_template("user-data.j2").render(
        guest_plan=plan, guest_resolved_timezone="Europe/Rome", guest_cloud_init_user="sid",
        guest_admin_group="wheel", guest_cloud_init_ssh_public_keys=["ssh-ed25519 AAAA sid"],
        guest_vault_port=7401, guest_vault_listener=(ROOT / "roles/guest/files/hyperlab-vault-listen.py").read_text())
    require(text.startswith("#cloud-config\n"), "the user data lost its header")
    return yaml.safe_load(text)


def check_cloud_init() -> None:
    vault = user_data({"key_vault": "vault", "network_profile": "none", "qemu_guest_agent": False})
    plain = user_data({})
    client = user_data({"key_vault": "client"})
    require("write_files" not in plain and "runcmd" not in plain and "write_files" not in client,
            "a Machine that is not the vault carries the vault's files")
    files = {item["path"]: item for item in vault["write_files"]}
    listener = files["/usr/local/bin/hyperlab-vault-listen"]
    require(listener["content"] == (ROOT / "roles/guest/files/hyperlab-vault-listen.py").read_text()
            and listener["permissions"] == "0755", "the listener is not delivered verbatim")
    agent = files["/etc/systemd/system/hyperlab-vault-agent.service"]["content"]
    listen = files["/etc/systemd/system/hyperlab-vault-listen.service"]["content"]
    require("User=sid" in agent and "User=sid" in listen, "the vault units do not run as the account")
    require("-a /run/hyperlab-vault/agent.sock" in agent and LISTEN.AGENT == "/run/hyperlab-vault/agent.sock",
            "the listener and the agent disagree on the socket")
    require("ssh-keygen -q -t ed25519" in agent and "ssh-add -q" in agent, "the vault makes or loads no key")
    require('"$$HOME/.ssh/id_ed25519"' in agent and "$$(seq" in agent and "$HOME/" not in agent.replace("$$HOME/", ""),
            "a shell dollar in the agent unit is left to systemd")
    require("Environment=HYPERLAB_VAULT_PORT=7401" in listen and "RestrictAddressFamilies=AF_VSOCK AF_UNIX" in listen,
            "the listener unit lost its port or its restrictions")
    require(["systemctl", "enable", "--now", "hyperlab-vault-agent.service", "hyperlab-vault-listen.service"]
            in vault["runcmd"], "the vault units are not started")

    guest = yaml.safe_load((ROOT / "roles/guest/defaults/main.yml").read_text())
    host = yaml.safe_load((ROOT / "roles/host_vault/defaults/main.yml").read_text())
    client_defaults = yaml.safe_load((ROOT / "roles/guest_vault_client/defaults/main.yml").read_text())
    require(guest["guest_vault_port"] == host["host_vault_port"] == LISTEN.PORT,
            "the vault's port differs between the vault and the host relay")
    require(client_defaults["guest_vault_client_relay_port"] == host["host_vault_listen_port"] == AGENT.PORT,
            "the relay's port differs between the client and the host")


def check_client_default() -> None:
    defaults = yaml.safe_load((ROOT / "roles/guest_vault_client/defaults/main.yml").read_text())
    require(defaults["guest_vault_client_default_agent"] is False, "the vault replaces a Machine's agent by default")
    tasks = yaml.safe_load((ROOT / "roles/guest_vault_client/tasks/main.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    require(by_name["Make the vault the default agent for logins and the session"]["when"]
            == "guest_vault_client_default_agent | bool", "the default agent is not opt-in")
    require(json.dumps(by_name["Leave the Machine's own agent the default"]).count("hyperlab-vault") == 2,
            "turning the default off does not remove both files")


def main() -> int:
    check_listener()
    check_agent()
    check_cloud_init()
    check_client_default()
    print("Key vault guest contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

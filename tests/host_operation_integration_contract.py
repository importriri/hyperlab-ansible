#!/usr/bin/env python3
"""Typed bridge, installation, and compositor parity for managed operations.

The provisioning case runs the whole chain over a temporary checkout: the
real bridge creates a Machine through the real CLI and hands it to the real
runner, which launches its operation and runs the real provisioner on a real
PTY, with recording ansible-playbook and openssl programs. systemd is the
only thing replaced.
"""
import importlib.util
import json
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'roles/host_desktop_common/files'
SECRET = 'correct horse battery'
KEY_LINE = ('ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f'
            ' sid@nitro')
PROMPT = b'New password for the Machine account: '


class ExecObserved(Exception):
    pass


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Records argv and environment; exits 4 while `fail` names a token of its argv.
ANSIBLE = r'''
import json, os, sys
base, args = sys.argv[1], sys.argv[2:]
with open(os.path.join(base, "calls.jsonl"), "a") as stream:
    stream.write(json.dumps({"argv": args, "env": dict(os.environ),
                             "file": [p for p in args if p.startswith("@")]}) + "\n")
try:
    fail = open(os.path.join(base, "fail")).read()
except FileNotFoundError:
    fail = ""
sys.exit(4 if fail and fail in " ".join(args) else 0)
'''

OPENSSL = r'''
import json, os, subprocess, sys
base, data = sys.argv[1], sys.stdin.read()
with open(os.path.join(base, "openssl.jsonl"), "a") as stream:
    stream.write(json.dumps({"argv": sys.argv[3:], "env": dict(os.environ), "stdin": data}) + "\n")
result = subprocess.run([sys.argv[2], *sys.argv[3:]], input=data, capture_output=True, text=True)
sys.stdout.write(result.stdout)
sys.exit(result.returncode)
'''

LAUNCHER = """\
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("provisioner", {source!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.CLI, module.ANSIBLE, module.OPENSSL = {cli!r}, {ansible!r}, {openssl!r}
module.POINTER = Path({pointer!r})
sys.exit(module.entry(sys.argv[1:]))
"""


class Lab:
    """A temporary checkout, home, state and runtime, with the real CLI over them."""

    def __init__(self, base):
        self.base = base
        self.repo = base / 'repo'
        for name in ('images', 'templates'):
            shutil.copytree(ROOT / name, self.repo / name)
        for path in (self.repo / 'templates').glob('*.md'):
            path.unlink()
        (self.repo / 'vm-specs').mkdir()
        shutil.copytree(ROOT / 'playbooks', self.repo / 'playbooks',
                        ignore=lambda directory, names: [n for n in names if not n.endswith('.yml')])
        for path in (self.repo / 'playbooks').glob('*.yml'):
            # Inert: the names are the checkout's, nothing in them runs.
            path.write_text('---\n- hosts: none\n  tasks: []\n')
        self.home = base / 'home'
        (self.home / '.ssh').mkdir(parents=True)
        (self.home / '.ssh/hyperlab_ed25519.pub').write_text(KEY_LINE + '\n')
        self.state = base / 'state'
        self.runtime = base / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.pointer = base / 'pointer'
        self.pointer.write_text(str(self.repo))
        bin_dir = base / 'bin'
        bin_dir.mkdir()
        self.cli = bin_dir / 'hyperlabctl'
        self.cli.write_text(
            f'#!{sys.executable}\n'
            'import os, sys\n'
            f"os.environ.update({{'HOME': {str(self.home)!r}, 'XDG_STATE_HOME': {str(self.state)!r},"
            " 'PYTHONDONTWRITEBYTECODE': '1'})\n"
            'sys.dont_write_bytecode = True\n'
            f"sys.path.insert(0, {str(ROOT / 'tools/hyperlabctl')!r})\n"
            'from hyperlabctl.cli import main\n'
            f"sys.exit(main(['--repo', {str(self.repo)!r}, *sys.argv[1:]]))\n")
        self.cli.chmod(0o700)
        programs = {}
        for name, source, fixed in (('ansible-playbook', ANSIBLE, ''),
                                    ('openssl', OPENSSL, shutil.which('openssl') or '/usr/bin/openssl')):
            (base / f'{name}.py').write_text(source)
            path = bin_dir / name
            path.write_text(f'#!/bin/sh\nexec {sys.executable} -I {base / name}.py {base} {fixed} "$@"\n')
            path.chmod(0o700)
            programs[name] = path
        self.launcher = base / 'provisioner.py'
        self.launcher.write_text(LAUNCHER.format(
            source=str(FILES / 'privatestack-machine-provision.py'), cli=str(self.cli),
            ansible=str(programs['ansible-playbook']), openssl=str(programs['openssl']),
            pointer=str(self.pointer)))

    def log(self, name):
        path = self.base / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def snapshot(self):
        tree = {}
        for root in (self.state, self.repo / 'vm-specs'):
            for path in sorted(root.rglob('*')):
                if path.name == '.lock':
                    continue
                data = path.read_bytes() if path.is_file() and not path.is_symlink() else None
                tree[str(path)] = (path.lstat().st_mode, data)
        return tree

    def shown(self, name):
        result = subprocess.run([str(self.cli), '--json', 'machine', 'show', name],
                                text=True, capture_output=True, check=False)
        return result.returncode == 0 and json.loads(result.stdout)['id'] == name


def read_until(conn, token, deadline=20):
    seen = b''
    end = time.time() + deadline
    conn.settimeout(0.5)
    while token not in seen and time.time() < end:
        try:
            data = conn.recv(4096)
        except TimeoutError:
            continue
        if not data:
            break
        seen += data
    return seen


def provisioning_contract():
    """Bridge -> runner -> provisioner, with nothing but systemd replaced."""
    with tempfile.TemporaryDirectory() as temp, \
            patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(Path(temp) / 'runtime')}):
        lab = Lab(Path(temp))
        bridge = load('provision_bridge', FILES / 'privatestack-machine-actions.py')
        bridge.HYPERLABCTL = str(lab.cli)
        op = load('provision_runner', FILES / 'privatestack-operation.py')
        op.POINTER = lab.pointer
        op.CLI = str(lab.cli)
        units = lab.base / 'units'
        units.mkdir()
        real_call = op.call

        def call(argv, **kwargs):
            if argv[0] == '/usr/bin/systemctl':
                return SimpleNamespace(returncode=0, stdout=''.join(
                    f'{unit.name}.service loaded active running Fixture\n' for unit in units.iterdir()))
            if argv[0] == '/usr/bin/systemd-run':
                unit = next(a.split('=', 1)[1] for a in argv if a.startswith('--unit='))
                if unit.startswith('hyperlab-operation-'):
                    (units / unit).write_text('active')
                return SimpleNamespace(returncode=0)
            require(argv[0] == str(lab.cli), f'the runner started {argv[0]}')
            return real_call(argv, **kwargs)

        op.call = call
        op.unit_active = lambda unit: (units / unit).exists()
        real_popen = subprocess.Popen

        def popen(argv, *args, **kwargs):
            if argv and argv[0] == op.PROVISION:
                # What the runner launches is recorded as it asked for it,
                # in a file, since the runner may be a forked process; the
                # provisioner it gets is the real one, from the checkout.
                with (lab.base / 'launched.jsonl').open('a') as stream:
                    stream.write(json.dumps(list(argv)) + '\n')
                argv = [sys.executable, '-I', str(lab.launcher), *argv[1:]]
            return real_popen(argv, *args, **kwargs)

        launched = []

        def execv(executable, argv):
            require(executable == bridge.OPERATION and argv[:2] == [bridge.OPERATION, 'launch'],
                    f'the bridge executed {argv}')
            launched.append(op.launch(argv[2], argv[3]))
            raise ExecObserved()

        def create(*args):
            launched.clear()
            try:
                with patch.object(bridge.os, 'execv', execv):
                    bridge.create(list(args))
            except ExecObserved:
                return launched
            except bridge.Refused as exc:
                return 'refused: ' + str(exc)
            raise AssertionError('the bridge neither launched nor refused')

        with patch.object(subprocess, 'Popen', popen):
            server_case(lab, op, create)
            workstation_case(lab, op, create)


def server_case(lab, op, create):
    root = op.directory()
    result = create('server-arch', 'srv-01', 'permanent', 'dev', 'balanced')
    require(isinstance(result, list) and len(result) == 1 and result[0]['phase'] == 'dispatched'
            and result[0]['action_id'] == 'machine.provision' and result[0]['machine'] == 'srv-01',
            f'a staged creation did not dispatch exactly one provisioning operation: {result}')
    oid = result[0]['operation_id']
    records = sorted(root.glob('*.json'))
    # Refused creations dispatch nothing: a name in use, a stale spec.
    stale = lab.repo / 'vm-specs/.generated/srv-02.yml'
    stale.write_text('stale: true\n')
    for args, reason in ((('server-arch', 'srv-01', 'permanent', 'dev', 'balanced'), 'already exists'),
                         (('server-arch', 'srv-02', 'permanent', 'dev', 'balanced'), 'already exists')):
        refusal = create(*args)
        require(isinstance(refusal, str) and reason in refusal,
                f'a refused creation was not refused: {refusal}')
        require(sorted(root.glob('*.json')) == records, 'a refused creation dispatched an operation')
    stale.unlink()

    before = lab.snapshot()
    (lab.base / 'fail').write_text('vm-guest-inventory')
    require(op.run(oid) == 1, 'a failed provisioning reported success')
    (lab.base / 'fail').unlink()
    record = op.read(root, oid)
    require(record['phase'] == 'failed' and record['reason'] == 'execution-failed' and record['rc'] == 4,
            f'the failing step\'s status was not recorded: {record}')
    launched = lab.log('launched.jsonl')
    require(launched == [[op.PROVISION, 'srv-01']],
            f'the runner did not launch exactly the provisioner and the name: {launched}')
    calls = [call['argv'] for call in lab.log('calls.jsonl')]
    require([argv[0] for argv in calls] == ['playbooks/vm-create.yml', 'playbooks/vm-guest-inventory.yml'],
            f'provisioning went on after a failed step: {calls}')
    # Failed provisioning is not refused intent: the Machine stays.
    require(lab.snapshot() == before and lab.shown('srv-01')
            and (lab.repo / 'vm-specs/.generated/srv-01.yml').is_file(),
            'a failed provisioning changed or withdrew the Machine record or its spec')
    (lab.base / 'launched.jsonl').unlink()
    (lab.base / 'calls.jsonl').unlink()


def workstation_case(lab, op, create):
    """The password crosses an observer, never the shell, record or transcript;
    an observer that leaves mid-prompt does not cancel the operation."""
    root = op.directory()
    result = create('workstation-dev', 'dev-01', 'permanent', 'dev', 'balanced')
    require(isinstance(result, list) and len(result) == 1 and result[0]['phase'] == 'dispatched',
            f'a workstation creation did not dispatch one operation: {result}')
    oid = result[0]['operation_id']
    before = lab.snapshot()
    context = multiprocessing.get_context('fork')
    worker = context.Process(target=lambda: os._exit(op.run(oid)))
    worker.start()
    try:
        endpoint = op.endpoint(root, oid)
        for _ in range(200):
            if endpoint.exists():
                break
            time.sleep(0.05)
        first = socket.socket(socket.AF_UNIX)
        first.connect(str(endpoint))
        require(PROMPT in read_until(first, PROMPT), 'the password prompt did not reach an observer')
        first.close()  # the operation window is closed at the prompt
        time.sleep(0.5)
        require(worker.is_alive() and op.read(root, oid)['phase'] == 'running',
                'closing the observer cancelled the provisioning')
        second = socket.socket(socket.AF_UNIX)
        second.connect(str(endpoint))
        require(PROMPT in read_until(second, PROMPT), 'a reopened observer lost the prompt')
        second.sendall(SECRET.encode() + b'\n')
        require(b'Repeat it: ' in read_until(second, b'Repeat it: '), 'no confirmation prompt')
        second.sendall(SECRET.encode() + b'\n')
        tail = read_until(second, b'dev-01 is provisioned.', deadline=30)
        second.close()
        worker.join(30)
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join()
    record_path = root / f'{oid}.json'
    record = op.read(root, oid)
    require(worker.exitcode == 0 and record['phase'] == 'succeeded' and record['rc'] == 0,
            f'workstation provisioning did not succeed: {record} {tail[-300:]!r}')
    launched = lab.log('launched.jsonl')
    require(launched == [[op.PROVISION, 'dev-01']], f'the runner launched {launched}')
    calls = lab.log('calls.jsonl')
    require(len(calls) == 5 and [len(call['file']) for call in calls] == [0, 0, 1, 0, 0],
            f'workstation steps: {[call["argv"] for call in calls]}')
    for call in calls:
        require(SECRET not in json.dumps(call['argv']) and SECRET not in json.dumps(call['env']),
                'the password reached a playbook')
    openssl = lab.log('openssl.jsonl')
    require(len(openssl) == 1 and openssl[0]['stdin'] == SECRET + '\n'
            and SECRET not in json.dumps(openssl[0]['argv']) + json.dumps(openssl[0]['env']),
            'the password did not reach openssl on stdin alone')
    require(SECRET.encode() not in op.transcript(root, oid).read_bytes(),
            'the password is in the operation transcript')
    require(SECRET not in record_path.read_text(), 'the password is in the operation record')
    private = lab.runtime / 'hyperlab/provision'
    require(private.is_dir() and not list(private.iterdir()), 'the hash file outlived the operation')
    require(lab.snapshot() == before, 'provisioning changed the Machine record or its spec')


def main():
    path = FILES / 'privatestack-machine-actions.py'
    spec = importlib.util.spec_from_file_location('machine_bridge', path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    observed = []

    def execv(executable, argv):
        observed.append((executable, argv))
        raise ExecObserved()

    bridge.live_machine = lambda name: {'name': name, 'managed': True,
                                        'state': 'shut off', 'vfio': True}
    bridge.managed_spec = lambda name: {'path': 'vm-specs/one.yml', 'spec': {'name': name}}
    bridge.resolve = lambda *args: ['ansible-playbook', 'reviewed-command']
    bridge.cli_json = lambda *args: {'devices': [
        {'port': '1-2', 'vendor_id': '0781', 'product_id': '5581', 'authorized': 0,
         'interfaces': ['08'], 'hid': False}]}
    for args, expected in (
        (['start', 'one'], ['launch', 'vm.managed-start', 'one']),
        (['usb-allow', '1-2', 'permanent', '0781:5581'],
         ['launch', 'usb.allow', 'usb:1-2:permanent:0781:5581']),
        (['operation', 'a' * 32], ['operation', 'a' * 32]),
        (['operations'], ['operations']),
        (['operation-view', 'a' * 32], ['view', 'a' * 32]),
    ):
        with patch.object(sys, 'argv', ['bridge', *args]), patch.object(bridge.os, 'execv', execv):
            try:
                bridge.main()
            except ExecObserved:
                pass
        assert observed[-1] == (bridge.OPERATION, [bridge.OPERATION, *expected])

    source = path.read_text()
    assert 'subprocess.Popen' not in source and 'json.dumps(argv)' not in source
    assert 'os.execvp(argv[0], argv)' in source
    assert bridge.CONNECTION_VERBS == ('console', 'ssh', 'looking-glass')
    tasks = (ROOT / 'roles/host_desktop_common/tasks/main.yml').read_text()
    assert ('src: privatestack-operation.py\n'
            '    dest: /usr/local/bin/privatestack-operation\n'
            '    owner: root\n    group: root\n    mode: "0755"') in tasks
    assert '/hyperlab/operations' not in tasks
    hypr = (ROOT / 'roles/host_desktop_hyprland/templates/hyprland.lua.j2').read_text()
    rule = hypr[hypr.index('name = "hyperlab-operation"'):].split('})', 1)[0]
    for token in ('class = "^hyperlab-operation$"', 'float = true',
                  'size = { 980, 560 }', 'center = true',
                  'no_initial_focus = false', 'focus_on_activate = true'):
        assert token in rule, token
    sway = (ROOT / 'roles/host_desktop_sway/files/sway.config').read_text()
    assert 'for_window [app_id="^hyperlab-operation$"]   floating enable, resize set 980 560' in sway
    gtk = (ROOT / 'roles/host_desktop_sway/files/privatestack-hyperlab-domains.py').read_text()
    managed = gtk.split('    def _managed_action(', 1)[1].split('    def _destructive_managed', 1)[0]
    for action in ('vm.managed-start', 'vm.managed-shutdown', 'vm.managed-reboot',
                   'vm.force-stop', 'vm.power-cycle', 'vm.reset'):
        assert action in managed
    assert '["/usr/local/bin/privatestack-operation", "launch",' in managed
    qml = FILES / 'quickshell/hyperlab'
    actions = (qml / 'MachineActions.qml').read_text()
    assert 'command: [machineActions.bridge, "operations"]' in actions
    assert 'if (mode !== "operation")' in actions
    assert 'interval: 2000' in actions
    assert 'if (!operationStatus.running && !statusDeadline.running)' in actions
    assert 'statusDeadline.start();' in actions
    assert 'interval: 90000' in actions
    assert 'Machine bridge unavailable' in actions
    assert 'machineActions.busyFor(name)' in actions
    # The window is an observer: it can be reopened, and its closure is never
    # reported as the reason an operation stopped.
    assert '[machineActions.bridge, "operation-view", record.id]' in actions
    tracker = (qml / 'OperationTracker.qml').read_text()
    assert 'terminal closed' not in tracker
    pane = (qml / 'MachineContextPane.qml').read_text()
    assert 'pane.machineActions.viewOperation(pane.identifier)' in pane
    shell = (qml / 'shell.qml').read_text()
    assert '"id": record.id' in shell and 'onInventoryRefreshRequested' in shell
    for name in ('MachineActions.qml', 'OperationTracker.qml'):
        source = (qml / name).read_text()
        for forbidden in ('sudo', 'pkexec', 'virsh', 'hyprctl', 'swaymsg',
                          'systemctl', 'systemd-run', '/proc', 'ansible-playbook'):
            assert forbidden not in source, (name, forbidden)
    provisioning_contract()
    print('HyperLab operation integration contract: OK')


if __name__ == '__main__':
    main()

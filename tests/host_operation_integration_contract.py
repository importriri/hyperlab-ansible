#!/usr/bin/env python3
"""Typed bridge, installation, and compositor parity for managed operations."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'roles/host_desktop_common/files'


class ExecObserved(Exception):
    pass


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
    for args, expected in (
        (['start', 'one'], ['launch', 'vm.managed-start', 'one']),
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
    print('HyperLab operation integration contract: OK')


if __name__ == '__main__':
    main()

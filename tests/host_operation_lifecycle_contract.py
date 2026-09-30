#!/usr/bin/env python3
"""Exercise the real operation state/storage/locking with inert execution."""
import importlib.util
import multiprocessing
import os
import signal
import socket
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'roles/host_desktop_common/files/privatestack-operation.py'
sys.path.insert(0, str(ROOT / 'tools/hyperlabctl'))
from hyperlabctl.registry import resolve as registry_resolve  # noqa: E402


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def refused(fn):
    try:
        fn()
    except (ValueError, OSError, TypeError):
        return
    raise AssertionError('unsafe request accepted')


PROMPT = r'''
import sys, termios
tty = open("/dev/tty", "r+b", buffering=0)
attrs = termios.tcgetattr(tty)
attrs[3] &= ~termios.ECHO
termios.tcsetattr(tty, termios.TCSANOW, attrs)
tty.write(b"BECOME password: ")
line = b""
while not line.endswith(b"\n"):
    line += tty.read(1)
tty.write(b"\r\nauthenticated\r\n")
sys.exit(0 if line.strip() == b"fixture-secret" else 9)
'''


def read_until(conn, token, deadline=10):
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


def detach_contract(op, root, base):
    """Real PTY: an observer leaving mid-prompt does not interrupt the run."""
    # Settle earlier fixtures: their units stop, recovery marks them final.
    for unit in base.glob('hyperlab-operation-*'):
        unit.unlink()
    op.records(root)
    record = op.launch('vm.managed-reboot', 'one')
    require(record['phase'] == 'dispatched', 'fixture launch refused')
    oid = record['operation_id']
    argv = ['/usr/bin/python3', '-I', '-c', PROMPT]
    record['command_digest'] = op.digest(__import__('json').dumps(argv).encode())
    op.write(root, record)
    op.resolve = lambda action, machine, repo: (argv, record['checkout_identity'],
                                                record['spec_digest'])
    context = multiprocessing.get_context('fork')
    worker = context.Process(target=lambda: os._exit(op.run(oid)))
    worker.start()
    endpoint = op.endpoint(root, oid)
    for _ in range(100):
        if endpoint.exists():
            break
        time.sleep(0.05)
    require(stat.S_ISSOCK(endpoint.lstat().st_mode)
            and stat.S_IMODE(endpoint.lstat().st_mode) == 0o600, 'private observer endpoint')
    first = socket.socket(socket.AF_UNIX)
    first.connect(str(endpoint))
    require(b'BECOME password:' in read_until(first, b'BECOME password:'),
            'prompt not relayed to observer')
    first.close()  # the operation terminal was closed mid-authentication
    time.sleep(0.5)
    require(worker.is_alive() and op.read(root, oid)['phase'] == 'running',
            'closing the observer interrupted the operation')
    # A real observer process, attached when the operation ends, must report
    # the published result, never the running phase it raced past.
    stdin_r, stdin_w = os.pipe()
    stdout_r, stdout_w = os.pipe()
    observer = os.fork()
    if observer == 0:  # inherits the fixture's unit state
        os.dup2(stdin_r, 0)
        os.dup2(stdout_w, 1)
        os.dup2(stdout_w, 2)
        try:
            op.attach(oid)
        finally:
            os._exit(0)
    os.close(stdin_r)
    os.close(stdout_w)
    time.sleep(0.5)
    second = socket.socket(socket.AF_UNIX)
    second.connect(str(endpoint))
    require(b'BECOME password:' in read_until(second, b'BECOME password:'),
            'reattached observer lost context')
    second.sendall(b'fixture-secret\n')
    require(b'authenticated' in read_until(second, b'authenticated'), 'input not relayed')
    second.close()
    worker.join(15)
    report = b''
    while chunk := os.read(stdout_r, 65536):
        report += chunk
    os.waitpid(observer, 0)
    os.close(stdout_r)
    os.close(stdin_w)
    require(b'[HyperLab operation succeeded (exit 0)]' in report,
            'observer reported a stale phase: %r' % report[-200:])
    final = op.read(root, oid)
    require(worker.exitcode == 0 and final['phase'] == 'succeeded' and final['rc'] == 0,
            'reattached operation did not reach a real terminal state')
    require(not endpoint.exists(), 'observer endpoint leaked after completion')
    log = op.transcript(root, oid)
    require(stat.S_IMODE(log.stat().st_mode) == 0o600
            and b'fixture-secret' not in log.read_bytes(), 'transcript leaked secret or mode')
    with patch.object(op.os, 'getuid', return_value=os.getuid() + 1):
        pair = socket.socketpair(socket.AF_UNIX)
        require(not op.peer_is_owner(pair[0]), 'foreign observer accepted')
        for item in pair:
            item.close()


def main():
    spec = importlib.util.spec_from_file_location('operation', SOURCE)
    op = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(op)
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        runtime = base / 'runtime'
        runtime.mkdir(mode=0o700)
        repo = base / 'repo'
        (repo / 'vm-specs').mkdir(parents=True)
        (repo / 'playbooks').mkdir()
        for name in ('start', 'shutdown', 'reboot', 'stop', 'power-cycle', 'reset'):
            (repo / f'playbooks/vm-{name}.yml').write_text('---\n')
        for machine in ('one', 'two'):
            (repo / f'vm-specs/{machine}.yml').write_text(f'name: {machine}\n')
        pointer = base / 'pointer'
        pointer.write_text(str(repo))
        op.POINTER = pointer
        calls = []

        def fake_cli(root, *args):
            require(root == repo, 'checkout escaped')
            if args == ('compose', 'list'):
                return [{'path': f'vm-specs/{name}.yml', 'spec': {'name': name}}
                        for name in ('one', 'two')]
            require(args[:2] == ('actions', '--resolve'), 'unreviewed lookup')
            return registry_resolve(args[2], repo_root=repo, spec=args[4], domain=args[6])

        def fake_call(argv, **kwargs):
            if argv[0] == '/usr/bin/systemctl' and 'list-units' in argv:
                return SimpleNamespace(returncode=0, stdout=''.join(
                    item.name + '.service loaded active running Fixture\n'
                    for item in base.glob('hyperlab-operation-*')))
            calls.append(argv)
            require(argv[0] == '/usr/bin/systemd-run', 'unexpected process')
            unit = next(a.split('=', 1)[1] for a in argv if a.startswith('--unit='))
            (base / unit).write_text('active')
            return SimpleNamespace(returncode=0)

        original_unit_active = op.unit_active
        op.cli = fake_cli
        op.call = fake_call
        op.unit_active = lambda unit: (base / unit).exists()
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(runtime)}):
            root = op.directory()
            with patch.object(op, 'call', return_value=SimpleNamespace(
                    returncode=0, stdout='LoadState=not-found\nActiveState=inactive\n')):
                require(not original_unit_active('hyperlab-operation-' + 'a' * 32),
                        'missing unit counted active')
            with patch.object(op, 'call', return_value=SimpleNamespace(returncode=1, stdout='')):
                refused(lambda: original_unit_active('hyperlab-operation-' + 'a' * 32))
            require(stat.S_IMODE(root.stat().st_mode) == 0o700, 'directory mode')
            refused(lambda: op.launch('vm.create', 'one'))
            refused(lambda: op.launch('vm.managed-start', 'missing'))
            with patch.object(sys, 'argv', ['runner', 'launch', '--argv-json', '[]']):
                refused(op.main)

            record = op.launch('vm.managed-start', 'one')
            oid = record['operation_id']
            require(len(oid) == 32 and op.identity(oid), 'random id shape')
            path = root / (oid + '.json')
            require(stat.S_IMODE(path.stat().st_mode) == 0o600, 'record mode')
            require(record['phase'] == 'dispatched', 'dispatch phase')
            require(op.launch('vm.managed-start', 'one')['reason'] == 'operation-in-progress',
                    'duplicate not refused')
            other = op.launch('vm.managed-start', 'two')
            require(other['operation_id'] != oid, 'independent operation id')
            command = calls[0]
            require('--user' in command and '--collect' in command
                    and '/usr/bin/env' in command and '-i' in command
                    and '--unit=hyperlab-operation-' + oid in command,
                    'operation not in independent user unit')
            require(command[-3:] == [op.SELF, 'run', oid], 'terminal command changed')
            # The operation unit owns execution; no terminal lives in it.
            require('/usr/bin/foot' not in command, 'terminal owns the operation unit')
            view = calls[1]
            require(view[0] == '/usr/bin/systemd-run' and '/usr/bin/foot' in view
                    and view[-3:] == [op.SELF, 'attach', oid], 'observer view missing')
            view_unit = next(a.split('=', 1)[1] for a in view if a.startswith('--unit='))
            require(not view_unit.startswith('hyperlab-operation-')
                    and 'hyperlab-operation' not in view_unit
                    and oid in view_unit, 'view unit collides with operation inventory')
            require('one' not in record['unit'], 'machine leaked into unit name')

            saved = path.read_bytes()
            path.unlink()
            refused(lambda: op.records(root))
            refused(lambda: op.launch('vm.managed-start', 'one'))
            path.write_bytes(saved)
            path.chmod(0o600)

            # Atomic replacement preserves the old record if publication fails.
            before = path.read_bytes()
            with patch.object(op.os, 'replace', side_effect=OSError('fixture')):
                refused(lambda: op.transition(root, record, 'running', 'authentication-or-execution'))
            require(path.read_bytes() == before and not list(root.glob('.record-*')),
                    'failed publication damaged old record or leaked temporary file')
            path.chmod(0o644)
            refused(lambda: op.read(root, oid))
            path.chmod(0o600)
            with patch.object(op.os, 'getuid', return_value=os.getuid() + 1):
                refused(lambda: op.read(root, oid))
            path.unlink()
            path.symlink_to(root / (other['operation_id'] + '.json'))
            refused(lambda: op.read(root, oid))
            path.unlink()
            op.write(root, record)
            path.write_text('{}')
            refused(lambda: op.read(root, oid))
            op.write(root, record)

            executed = []
            class Child:
                def __init__(self, argv, **kwargs):
                    executed.append(argv)
                    require(argv == ['/usr/bin/ansible-playbook', 'playbooks/vm-start.yml',
                                     '-K', '-e', 'guest_spec=vm-specs/one.yml'],
                            'runner did not execute complete reviewed registry command')
                    require(op.read(root, oid)['phase'] == 'running', 'running not durable')
                def wait(self, **kwargs):
                    return 0
                def poll(self):
                    return 0

            with patch.object(op.subprocess, 'Popen', Child):
                require(op.run(oid) == 0, 'success run failed')
            require(op.read(root, oid)['phase'] == 'succeeded', 'success not recorded')
            with patch.object(op.subprocess, 'Popen', side_effect=AssertionError('replayed')):
                require(op.run(oid) == 1, 'replayed terminal record')
            require(op.read(root, oid)['phase'] == 'succeeded', 'replay overwrote result')

            for rc in (7,):
                record = op.launch('vm.managed-start', 'one')
                oid = record['operation_id']
                with patch.object(Child, 'wait', return_value=rc), patch.object(op.subprocess, 'Popen', Child):
                    op.run(oid)
                require(op.read(root, oid)['rc'] == rc
                        and op.read(root, oid)['phase'] == 'failed', 'failure rc lost')

            # Stopping the unit interrupts; a hangup never does.
            for sig, expected in ((signal.SIGTERM, 'interrupted'), (signal.SIGHUP, 'succeeded')):
                record = op.launch('vm.managed-start', 'one')
                oid = record['operation_id']
                def interrupt(*args, signal_number=sig, **kwargs):
                    os.kill(os.getpid(), signal_number)
                    return 0
                with patch.object(Child, 'wait', interrupt), patch.object(op.subprocess, 'Popen', Child):
                    op.run(oid)
                require(op.read(root, oid)['phase'] == expected,
                        'signal %s recorded as %s' % (sig, op.read(root, oid)['phase']))

            (base / other['unit']).unlink()
            require(op.recover(root, op.read(root, other['operation_id']))['phase'] == 'interrupted',
                    'inactive unit was not interrupted')

            # flock shared by independent UI callers: exactly one winner.
            context = multiprocessing.get_context('fork')
            queue = context.Queue()
            def contender():
                queue.put(op.launch('vm.managed-start', 'one')['phase'])
            workers = [context.Process(target=contender) for _ in range(6)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
                require(worker.exitcode == 0, 'concurrent launch hung')
            results = [queue.get(timeout=2) for _ in workers]
            require(results.count('dispatched') == 1 and results.count('refused') == 5,
                    'duplicate concurrent winners')

            # Re-resolution refuses changed context before any command starts.
            tampered = op.launch('vm.managed-start', 'two')
            tampered['command_digest'] = '0' * 64
            op.write(root, tampered)
            with patch.object(op.subprocess, 'Popen', side_effect=AssertionError('tampered execution')):
                op.run(tampered['operation_id'])
            require(op.read(root, tampered['operation_id'])['phase'] == 'failed',
                    'context drift did not leave a durable failure')
            for action in op.ACTIONS:
                argv, _, _ = op.resolve(action, 'two', repo)
                require(argv[0] == '/usr/bin/ansible-playbook' and '-K' in argv,
                        'lifecycle action lost reviewed binary/authentication')

            # A view that cannot open never fails or cancels the operation.
            viewless = op.launch('vm.managed-start', 'two')
            (base / viewless['unit']).unlink()
            op.write(root, op.transition(root, op.read(root, viewless['operation_id']),
                                         'interrupted', 'unit-inactive'))
            op.call = lambda argv, **kwargs: (SimpleNamespace(returncode=1)
                if argv[0] == '/usr/bin/systemd-run' and '/usr/bin/foot' in argv
                else fake_call(argv, **kwargs))
            result = op.launch('vm.managed-start', 'two')
            require(result['phase'] == 'dispatched', 'view failure changed operation state')
            (base / result['unit']).unlink()
            op.write(root, op.transition(root, op.read(root, result['operation_id']),
                                         'interrupted', 'unit-inactive'))

            # Early systemd-run failure still leaves a final record.
            op.call = lambda argv, **kwargs: (SimpleNamespace(returncode=1)
                if argv[0] == '/usr/bin/systemd-run' else fake_call(argv, **kwargs))
            result = op.launch('vm.managed-start', 'two')
            require(result['phase'] == 'failed' and result['reason'] == 'execution-launch-failed',
                    'early launch failure not durable')
            op.call = fake_call

            detach_contract(op, root, base)
            # No automatic backend lock cleanup is part of this helper.
            source = SOURCE.read_text()
            require('shell=True' not in source and 'eval(' not in source
                    and 'rmtree' not in source and 'rmdir' not in source
                    and '--argv-json' not in source, 'generic execution or lock removal')
    print('HyperLab operation lifecycle contract: OK')


if __name__ == '__main__':
    main()

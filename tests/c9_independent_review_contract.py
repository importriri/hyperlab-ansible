#!/usr/bin/env python3
"""Independent behavioural regressions: no libvirt, systemd or guest mutation."""
import importlib.util
import multiprocessing
import os
from pathlib import Path
import signal
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/hyperlabctl'))
sys.path.insert(0, str(ROOT / 'tools/hyperlabctl/tests'))
import world  # noqa: E402
from hyperlabctl import document  # noqa: E402


class LifecycleReview(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'review_operation', ROOT / 'roles/host_desktop_common/files/privatestack-operation.py')
        self.op = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.op)
        temporary = tempfile.TemporaryDirectory(prefix='hyperlab-independent-review-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.units = set()
        self.timeout_after_accept = False
        for target, value in (
            ('directory', lambda: self.root),
            ('environment', lambda: {'PATH': '/usr/bin'}),
            ('checkout', lambda: self.root),
            ('resolve', lambda *args: (['/usr/bin/ansible-playbook', '-K'], 'fixture', 'a' * 64)),
            ('unit_active', lambda unit: unit in self.units),
            ('call', self.call),
        ):
            patcher = patch.object(self.op, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, argv, **kwargs):
        if 'list-units' in argv:
            return SimpleNamespace(returncode=0, stdout=''.join(
                unit + '.service loaded active running fixture\n' for unit in self.units))
        self.assertEqual(argv[0], '/usr/bin/systemd-run')
        unit = next(arg.split('=', 1)[1] for arg in argv if arg.startswith('--unit='))
        self.units.add(unit)
        if self.timeout_after_accept:
            raise subprocess.TimeoutExpired(argv, 20)
        return SimpleNamespace(returncode=0, stdout='')

    def test_terminal_hangup_does_not_terminate_execution(self):
        record = self.op.launch('vm.managed-shutdown', 'fixture')
        real_popen = subprocess.Popen
        children = []
        timers = []

        def inert_child(*args, **kwargs):
            child = real_popen([sys.executable, '-c', 'import time; time.sleep(0.3)'])
            children.append(child)
            timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGHUP))
            timers.append(timer)
            timer.start()
            return child

        try:
            with patch.object(self.op.subprocess, 'Popen', inert_child):
                self.op.run(record['operation_id'])
        finally:
            for timer in timers:
                timer.cancel()
                timer.join()
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait()
        final = self.op.read(self.root, record['operation_id'])
        self.assertEqual(final['phase'], 'succeeded',
                         'observer terminal SIGHUP terminated independent work')
        self.assertEqual(children[0].returncode, 0)

    def test_stalled_observer_cannot_block_worker_completion(self):
        context = multiprocessing.get_context('fork')
        ready = context.Event()
        begin = context.Event()
        oid = 'b' * 32

        def worker():
            listener, _ = self.op.serve(self.root, oid)
            read_fd, write_fd = os.pipe()
            ready.set()
            begin.wait(2)
            started = time.monotonic()
            child = SimpleNamespace(poll=lambda: 0 if time.monotonic() - started > 0.2 else None)

            def produce():
                try:
                    for _ in range(128):
                        os.write(write_fd, b'x' * 32768)
                finally:
                    os.close(write_fd)

            threading.Thread(target=produce, daemon=True).start()
            with open(self.root / (oid + '.log'), 'wb') as log:
                self.op.relay(child, read_fd, listener, log, self.root / (oid + '.log'))
            listener.close()
            os.close(read_fd)

        process = context.Process(target=worker)
        process.start()
        observer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.assertTrue(ready.wait(2))
            observer.connect(str(self.op.endpoint(self.root, oid)))
            begin.set()
            process.join(2)
            self.assertFalse(process.is_alive(), 'non-reading observer blocked the worker relay')
            self.assertEqual(process.exitcode, 0)
        finally:
            observer.close()
            if process.is_alive():
                process.terminate()
            process.join(2)

    def test_timeout_after_unit_acceptance_is_not_a_terminal_failure(self):
        self.timeout_after_accept = True
        record = self.op.launch('vm.managed-shutdown', 'fixture')
        self.assertIn(record['unit'], self.units)
        self.assertNotIn(record['phase'], self.op.FINAL,
                         'unknown dispatch outcome was recorded as an immutable failure')
        self.timeout_after_accept = False
        duplicate = self.op.launch('vm.managed-shutdown', 'fixture')
        self.assertEqual(duplicate['phase'], 'refused')


class VerificationReview(unittest.TestCase):
    def test_shell_discovery_ignores_generated_binary_files(self):
        line = next(line for line in (ROOT / 'verify.sh').read_text().splitlines()
                    if line.startswith('scripts='))
        command = shlex.split(line.split('$(', 1)[1].split(' 2>', 1)[0])
        with tempfile.TemporaryDirectory(prefix='hyperlab-discovery-review-') as temporary:
            root = Path(temporary)
            (root / 'real.sh').write_text('#!/bin/sh\nexit 0\n')
            (root / 'cached.pyc').write_bytes(b'\x00bytecode\n#!/bin/sh\n')
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), ['./real.sh'])


class TrustReview(unittest.TestCase):
    def test_unreadable_gpu_mapped_domain_has_no_network_identity(self):
        name = 'win11clean-valley'
        ctx = world.build(domains=[{'name': name, 'state': 'running',
                                   'memory_mb': 1024, 'vfio': True}], trust=None)
        ctx.runner.register(['/usr/bin/virsh', '-c', 'qemu:///system', '-q',
                             'dumpxml', name], (1, ''))
        row = next(row for row in document.build(ctx)['domains'] if row['name'] == name)
        self.assertIsNone(row['managed'])
        self.assertIsNone(row['trust_profile'],
                          'unreadable domain was treated as a known unmanaged GPU guest')


if __name__ == '__main__':
    unittest.main()

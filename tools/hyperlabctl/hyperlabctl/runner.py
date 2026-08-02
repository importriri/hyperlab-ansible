"""The only place in the package that starts a process.

Everything else asks the runner. That is what makes every provider testable
offline: the tests swap in RecordedRunner and replay captured output, with no
mocking library and no network.
"""

import os
import shlex
import subprocess


_DEFAULT_TIMEOUT = object()


class Result:
    __slots__ = ("argv", "rc", "stdout", "stderr")

    def __init__(self, argv, rc, stdout="", stderr=""):
        self.argv = list(argv)
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self):
        return self.rc == 0

    def lines(self):
        return [line.strip() for line in self.stdout.splitlines() if line.strip()]

    def __repr__(self):
        return "Result(%s, rc=%d)" % (shlex.join(self.argv), self.rc)


class Runner:
    """Real subprocess execution with stable C-locale output."""

    def __init__(self, timeout=15, environ=None):
        self.timeout = timeout
        self.calls = []
        self.environ = dict(os.environ if environ is None else environ)
        self.environ["LC_ALL"] = "C"
        self.environ["LANG"] = "C"

    def run(self, argv, timeout=_DEFAULT_TIMEOUT):
        argv = [str(part) for part in argv]
        self.calls.append(tuple(argv))
        effective_timeout = self.timeout if timeout is _DEFAULT_TIMEOUT else timeout
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
                env=self.environ,
            )
        except FileNotFoundError:
            return Result(argv, 127, "", "%s: not found" % argv[0])
        except subprocess.TimeoutExpired:
            return Result(argv, 124, "", "%s: timed out" % argv[0])
        return Result(argv, proc.returncode, proc.stdout, proc.stderr)


class RecordedRunner(Runner):
    """Replays a table of captured command output.

    An unregistered command returns rc=127 rather than raising: a provider must
    survive a binary that is not installed, and the tests must see that path.
    """

    def __init__(self, table=None):
        super().__init__()
        self.table = {}
        self.timeouts = []
        for argv, value in (table or {}).items():
            self.register(argv, value)

    def register(self, argv, value):
        key = tuple(argv) if isinstance(argv, (list, tuple)) else tuple(shlex.split(argv))
        if isinstance(value, Result):
            self.table[key] = value
        elif isinstance(value, tuple):
            self.table[key] = Result(key, value[0], value[1])
        else:
            self.table[key] = Result(key, 0, value)
        return self

    def run(self, argv, timeout=_DEFAULT_TIMEOUT):
        argv = [str(part) for part in argv]
        key = tuple(argv)
        self.calls.append(key)
        self.timeouts.append(timeout)
        if key not in self.table:
            return Result(argv, 127, "", "%s: not registered" % argv[0])
        recorded = self.table[key]
        return Result(argv, recorded.rc, recorded.stdout, recorded.stderr)

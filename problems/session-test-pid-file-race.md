# The session reload tests took a vanished pid file for a new manager

Author: [importriri](https://github.com/importriri).

Status: corrected in the test; covered by a deterministic case in
`tests/hyperlab_session.bats`.

## Symptom

`tests/hyperlab_session.bats` failed now and then, on commits that did not
touch the session launcher, in either reload test:

```text
not ok 33 a reload replaces the resident manager before warming the new source
#   `[[ $(<"${HYPERLAB_TEST_PID_FILE}") == "${current}" ]]' failed
# .../manager.pid: No such file or directory
not ok 36 concurrent reload helpers perform one serialized replacement
#   `current=$(<"${HYPERLAB_TEST_PID_FILE}")' failed
```

Idle, the two tests passed 15 times out of 15. With 16 to 24 busy loops on
the eight CPUs they failed once in 15 runs and once in 30.

## Diagnosis

A failing run with the test's state dumped showed one start in the starts
file, the old manager's, and no pid file: the launcher had quit the old
manager and not yet started the new one, yet `wait_for_pid_change` had
already returned success.

The helper checked the pid file with `-r` and then read it. The fake
manager removes its pid file when it exits, so under load the file could
go between the two steps. The read failed, gave an empty string, and an
empty string is not the old pid, so the helper reported a new manager that
did not exist. The next read of the pid file then failed. An empty read
while the new manager truncates the file before writing it had the same
effect.

The launcher was not at fault: it still waited for the old manager to exit
before starting the new one.

## Fix

`read_manager_pid` reads the file once and treats a failed or empty read as
no pid; `wait_for_pid_change` waits for a pid that is present and different.

The concurrent test also asserted that each losing helper had exited with
`! kill -0`, which Bash's `errexit` ignores, so that line could never fail;
it now checks the status of `run kill -0`.

## Regression proof

The new case "a missing, unreadable or empty pid file is not a new manager"
gives the helper a missing pid file, a pid file that passes `-r` but cannot
be read (a directory), an empty one and a real different pid. The old
helper fails it; the corrected one passes. With 24 busy loops the two
reload tests then passed 30 runs out of 30.

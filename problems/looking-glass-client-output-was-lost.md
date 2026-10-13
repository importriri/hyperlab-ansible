# The Looking Glass client's output was lost

Seen on Nitro, 2026-10-12, after group 16 (`16-looking-glass-sender-171244`):
the restarted sender never had a client, and nothing on the host could say
why the client did not reconnect.

## What happened

`hyperlabctl open looking-glass` ends by exec'ing
`/usr/local/bin/looking-glass-client`, which keeps the caller's output.
From the HyperLab shell the caller is the Machine actions bridge, run by a
Quickshell `Process`: stdout went to a line parser that reads only the
bridge's own `accepted` and `refused` lines, and stderr to a collector that
kept it in memory and used it only as the failure text when the client
ended badly (`MachineActions.qml`, the connection runner). A client that
ran and did not reconnect left no line anywhere. When it is started from a
terminal its output scrolls away with that terminal.

The client logs what a reconnection needs: "Waiting for the host to
restart", "The host application seems to not be running", every
`lgmpClientSessionInit` and `lgmpClientSubscribe` failure and the host's
version (`client/src/main.c`).

## Fix

Just before the exec, `open looking-glass` sends its own output, and so the
client's, to `$XDG_STATE_HOME/hyperlab/looking-glass-client-<Machine>.log`
(`~/.local/state/hyperlab/` when `XDG_STATE_HOME` is not an absolute path):

- mode 0600, in a directory created 0700; a file left with a looser mode is
  set back to 0600;
- replaced at each start, with a first line naming the Machine and the
  time;
- opened without following a symlink and without waiting on a FIFO, and
  used only when it is this user's regular file; a Machine name that could
  leave the directory or hide the file is refused (HyperLab's names,
  `^[a-z0-9][a-z0-9-]{1,30}$`, all pass);
- the caller is told the path on its own stderr first, so a client that
  fails at once still points the pane at its log.

The provenance registration and the exec are unchanged; the client keeps
the process.

## What the file can contain

Read in the pinned client's source (`client/src`, `PureSpice`): the
client's and the host's versions, renderer and font, the configuration
file's path, the SPICE socket's path, the guest's name, CPU model and OS,
frame formats, LGMP and SPICE errors, and `strerror` texts. The clipboard
code logs only failures, never data; no keystroke or key code is logged.
No secret reaches it: HyperLab passes no SPICE password and no key, and
`hyperlabctl` writes nothing to it before the exec but the first line.

## Regression proof

`tests/looking_glass_client_log_contract.py` runs the real redirect in a
child process that then execs a stand-in client writing to both streams:
the caller gets only the path line; the file holds the first line and both
streams, mode 0600, in a 0700 directory; a second start replaces it and
restores 0600; a relative `XDG_STATE_HOME` falls back to `~/.local/state`;
a symlink in its place is not followed, a FIFO is refused without waiting,
and names such as `../escape` are refused. It also requires the redirect
inside the Looking Glass branch, after the provenance registration and
before the exec. Against the previous code: `open looking-glass does not
send the client's output to its log`, and the redirect does not exist.

Reviewed and left as they are (2026-10-12): a hard link left at the log's
path to another of the same user's files is truncated (only that user can
plant it; `st_nlink` is not checked); an existing state directory keeps its
mode, only a new one is made 0700; a failed `mkdir`, `write` or `ftruncate`
ends `open looking-glass` with a traceback instead of a message, and no
window opens (fail-closed).

## Still open

Why the client did not reconnect to the restarted sender on 2026-10-12
at 17:12 is not known: that run had no client log. In the next run
(`16-looking-glass-sender-224919`) the log shows the client reconnecting
when the sender restarted: "Waiting for the host to restart..." at
00:05:01.629, the SPICE display meanwhile, and the stream's first format
line at 00:05:01.766.

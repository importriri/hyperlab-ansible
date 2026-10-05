#!/usr/bin/env python3
"""The Linux sender keeps receiving frames, and recovers when it does not.

problems/looking-glass-sender-streaming-without-frames.md: the pinned
sender's PipeWire process callback returned on a buffer with an empty
chunk without queueing it back, so every empty buffer was lost to the
stream. With the pool gone the producer could send nothing more, the
stream stayed "streaming", and a capture timeout is not logged: the
client froze on its last frame and the sender said nothing.

The reviewed runtime patch carries the whole callback in one hunk, so this
contract rebuilds it before and after the patch and runs each against a
fake stream with a pool of four buffers and one empty frame in ten:

  1. before the patch the producer runs out of buffers (the reproduction);
  2. after it every frame is produced and every usable one delivered;
  3. the watchdog warns once after 10 s without a usable frame and asks
     for a capture restart after 30 s, and a frame resets it;
  4. the capture timeout path uses the watchdog and restarts the capture.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "roles/guest_looking_glass_linux/files/pipewire-thread-loop-runtime.patch"
CALLBACK = "static void streamProcessCallback(void * opaque)"

HARNESS = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
struct spa_chunk { uint32_t size; };
struct spa_data { void *data; struct spa_chunk *chunk; };
struct spa_buffer { struct spa_data datas[1]; };
struct pw_buffer { struct spa_buffer *buffer; };
struct pw_stream { int unused; };
struct pw_thread_loop { int unused; };
#define DEBUG_WARN(...) (fprintf(stderr, __VA_ARGS__), fputc('\n', stderr))
static uint64_t clock_us;
static uint64_t microtime(void) { return ++clock_us; }

#define POOL 4
enum { FREE, READY, HELD };
static struct spa_chunk chunks[POOL];
static struct spa_buffer sbufs[POOL];
static struct pw_buffer pbufs[POOL];
static int owner[POOL];
static unsigned delivered;

static struct pw_buffer *pw_stream_dequeue_buffer(struct pw_stream *s)
{
  (void)s;
  for (int i = 0; i < POOL; ++i)
    if (owner[i] == READY) { owner[i] = HELD; return &pbufs[i]; }
  return NULL;
}
static void pw_stream_queue_buffer(struct pw_stream *s, struct pw_buffer *b)
{
  (void)s;
  owner[b - pbufs] = FREE;
}
static void pw_thread_loop_signal(struct pw_thread_loop *l, bool wait)
{
  (void)l; (void)wait;
  ++delivered;
}

struct pipewire {
  bool stop, hasFormat;
  struct pw_stream *stream;
  struct pw_thread_loop *threadLoop;
  uint8_t *frameData;
  uint64_t lastFrameUs;
  unsigned int callbacks, emptyBuffers;
  bool stallWarned;
};
static struct pw_stream stream;
static struct pw_thread_loop loop;
static struct pipewire state = { .hasFormat = true, .stream = &stream, .threadLoop = &loop };
static struct pipewire *this = &state;

#include "callback.c"

int main(void)
{
  static uint8_t pixels[16];
  (void)microtime;
  for (int i = 0; i < POOL; ++i) {
    sbufs[i].datas[0].data = pixels;
    sbufs[i].datas[0].chunk = &chunks[i];
    pbufs[i].buffer = &sbufs[i];
  }
  for (int frame = 0; frame < 1000; ++frame) {
    int slot = -1;
    for (int i = 0; i < POOL; ++i)
      if (owner[i] == FREE) { slot = i; break; }
    if (slot < 0) {
      printf("stalled %d %u\n", frame, delivered);
      return 1;
    }
    chunks[slot].size = (frame % 10 == 9) ? 0 : 16;
    owner[slot] = READY;
    streamProcessCallback(NULL);
  }
  printf("flowing 1000 %u\n", delivered);
  return 0;
}
"""

WATCHDOG_TEST = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "watchdog.c"
#define S 1000000ULL
int main(void)
{
  int failed = 0;
#define EXPECT(now, last, warned, want) \
  if (hlStallAction(now, last, warned) != want) { \
    printf("hlStallAction(%llu, %llu, %d) != %s\n", (unsigned long long)(now), \
        (unsigned long long)(last), warned, #want); failed = 1; }
  EXPECT(5 * S, 0, false, HL_STALL_NONE);
  EXPECT(10 * S, 0, false, HL_STALL_WARN);
  EXPECT(12 * S, 0, true, HL_STALL_NONE);
  EXPECT(30 * S, 0, true, HL_STALL_RESTART);
  EXPECT(30 * S, 0, false, HL_STALL_RESTART);
  EXPECT(31 * S, 29 * S, false, HL_STALL_NONE);
  EXPECT(1 * S, 2 * S, false, HL_STALL_NONE);
  return failed;
}
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def hunk_images(patch: str, needle: str) -> tuple[list[str], list[str]]:
    """The pre- and post-image lines of the one hunk that contains needle."""
    hunks = re.split(r"(?m)^@@[^\n]*@@[^\n]*\n", patch)[1:]
    matches = [h for h in hunks if needle in h]
    require(len(matches) == 1, f"{needle!r} is not in exactly one hunk of the runtime patch")
    before, after = [], []
    for line in matches[0].splitlines():
        if line.startswith("\\"):
            continue
        tag, text = (line[:1], line[1:]) if line else (" ", "")
        if tag in (" ", "-"):
            before.append(text)
        if tag in (" ", "+"):
            after.append(text)
    return before, after


def function(lines: list[str], signature: str) -> str:
    require(signature in lines, f"the hunk does not hold the whole of {signature}")
    start = lines.index(signature)
    end = lines.index("}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


def compile_and_run(directory: Path, name: str, main: str, include: str, source: str) -> subprocess.CompletedProcess:
    (directory / include).write_text(source)
    (directory / f"{name}.c").write_text(main)
    binary = directory / name
    built = subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Werror", "-Wno-unused-function",
                            "-o", str(binary), str(directory / f"{name}.c")],
                           capture_output=True, text=True, cwd=directory, check=False)
    require(built.returncode == 0, f"{name} did not compile:\n{built.stderr}")
    return subprocess.run([str(binary)], capture_output=True, text=True, check=False)


def main() -> int:
    require(shutil.which("gcc") is not None, "gcc is needed to run the sender's callback")
    patch = PATCH.read_text()
    before, after = hunk_images(patch, CALLBACK)
    watchdog = re.search(r"(?ms)^\+// HyperLab frame watchdog \(begin\)\n(.*?)^\+// HyperLab frame watchdog \(end\)",
                         patch)
    require(watchdog is not None, "the runtime patch has no frame watchdog")
    watchdog_source = "\n".join(line[1:] for line in watchdog.group(1).splitlines()) + "\n"

    with tempfile.TemporaryDirectory(prefix="hyperlab-lg-stall-") as temporary:
        directory = Path(temporary)
        old = compile_and_run(directory, "old", HARNESS, "callback.c", function(before, CALLBACK))
        require(old.returncode == 1 and old.stdout.startswith("stalled "),
                f"the unpatched callback did not reproduce the stall: {old.stdout!r}")
        new = compile_and_run(directory, "new", HARNESS, "callback.c", function(after, CALLBACK))
        require(new.returncode == 0 and new.stdout.strip() == "flowing 1000 900",
                f"the patched callback still loses buffers: {new.stdout!r} {new.stderr!r}")
        policy = compile_and_run(directory, "policy", WATCHDOG_TEST, "watchdog.c", watchdog_source)
        require(policy.returncode == 0, f"the watchdog policy is wrong:\n{policy.stdout}")

    capture = patch[patch.index("pipewire_capture("):]
    timeout = capture[capture.index("if (result == ETIMEDOUT)"):]
    timeout = timeout[:timeout.index("return CAPTURE_RESULT_TIMEOUT;")]
    require("hlStallAction(" in timeout and "return CAPTURE_RESULT_REINIT;" in timeout,
            "a capture timeout does not consult the watchdog or restart the capture")
    require("No usable frame for" in timeout, "a stall is not logged")
    print("Looking Glass sender frame stall contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

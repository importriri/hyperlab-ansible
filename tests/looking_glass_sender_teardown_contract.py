#!/usr/bin/env python3
"""The Linux sender's capture restart cannot hang after "Capture Stop".

problems/looking-glass-sender-hung-after-capture-stop.md: on dev-01 the
sender logged "Capture Stop" and then nothing for 28 hours, alive and
sleeping. A PipeWire callback that delivers a frame or a format waits in
pw_thread_loop_signal(..., true) until the capture accepts it. When the
capture restarts instead, nothing accepted it, and deinit joined the
PipeWire thread that was still waiting: a deadlock.

The runtime patch carries the whole of pipewire.c in one hunk, so this
contract rebuilds the patched file and compiles it against the real
PipeWire thread loop (libpipewire), with the Looking Glass framework,
the portal and the stream's buffers replaced by small fakes:

  1. teardown: a usable frame arrives while the capture restarts; the
     sender's own order (stop, "Capture Stop", deinit) must finish;
  2. late format: a format that arrives after the stop, while deinit is
     about to join the PipeWire thread, must not wait for an accept;
  3. flow: frames still reach the capture one after another, and every
     buffer goes back to the stream;
  4. missed wake-up: a frame handed over while the capture is not waiting
     (problems/looking-glass-sender-frame-handed-over-to-nobody.md) is still
     taken by the next capture, instead of every capture timing out.
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
TARGET = "host/platform/Linux/capture/pipewire/src/pipewire.c"

# Just enough of the Looking Glass host framework for pipewire.c to build.
STUBS = {
    "portal.h": r"""
#pragma once
#include <stdbool.h>
#include <stdint.h>
struct Portal;
struct Portal * portal_create(void);
void portal_free(struct Portal * portal);
bool portal_createScreenCastSession(struct Portal * portal, char ** handle);
void portal_destroySession(struct Portal * portal, char ** sessionHandle);
bool portal_selectSource(struct Portal * portal, const char * sessionHandle);
uint32_t portal_getPipewireNode(struct Portal * portal, const char * sessionHandle);
int portal_openPipewireRemote(struct Portal * portal, const char * sessionHandle);
""",
    "interface/capture.h": r"""
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct stFrameBuffer FrameBuffer;
bool framebuffer_write(FrameBuffer * frame, const void * src, size_t size);
typedef enum CaptureResult {
  CAPTURE_RESULT_OK, CAPTURE_RESULT_REINIT, CAPTURE_RESULT_TIMEOUT, CAPTURE_RESULT_ERROR
} CaptureResult;
typedef enum CaptureFormat {
  CAPTURE_FMT_BGRA, CAPTURE_FMT_RGBA, CAPTURE_FMT_RGBA10, CAPTURE_FMT_RGBA16F
} CaptureFormat;
typedef enum CaptureRotation { CAPTURE_ROT_0 } CaptureRotation;
typedef struct CaptureFrame {
  unsigned formatVer, screenWidth, screenHeight, dataWidth, dataHeight;
  unsigned frameWidth, frameHeight, pitch, stride;
  CaptureFormat format;
  bool truncated, hdr, hdrPQ;
  CaptureRotation rotation;
  uint32_t damageRectsCount;
} CaptureFrame;
typedef struct CapturePointer CapturePointer;
typedef bool (*CaptureGetPointerBuffer )(void ** data, uint32_t * size);
typedef void (*CapturePostPointerBuffer)(const CapturePointer * pointer);
typedef struct CaptureInterface {
  const char * shortName;
  const bool   asyncCapture;
  const char * (*getName)(void);
  bool (*create)(CaptureGetPointerBuffer, CapturePostPointerBuffer, unsigned);
  bool (*init)(void * ivshmemBase, unsigned * alignSize);
  void (*stop)(void);
  bool (*deinit)(void);
  void (*free)(void);
  CaptureResult (*capture)(unsigned, FrameBuffer *);
  CaptureResult (*waitFrame)(unsigned, CaptureFrame *, const size_t);
  CaptureResult (*getFrame)(unsigned, FrameBuffer *, const size_t);
} CaptureInterface;
""",
    "interface/platform.h": "#pragma once\n",
    "common/stringutils.h": "#pragma once\n",
    "common/util.h": r"""
#pragma once
#define min(a,b) ({ __typeof__ (a) _a = (a); __typeof__ (b) _b = (b); _a < _b ? _a : _b; })
""",
    "common/debug.h": r"""
#pragma once
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#define HL_LOG(level, ...) (fprintf(stderr, level " " __VA_ARGS__), fputc('\n', stderr))
#define DEBUG_INFO(...)  HL_LOG("[I]", __VA_ARGS__)
#define DEBUG_WARN(...)  HL_LOG("[W]", __VA_ARGS__)
#define DEBUG_ERROR(...) HL_LOG("[E]", __VA_ARGS__)
#define DEBUG_ASSERT(x)  do { if (!(x)) { HL_LOG("[A]", "%s", #x); abort(); } } while (0)
""",
    "common/time.h": r"""
#pragma once
#include <stdint.h>
#include <time.h>
// The test moves the sender's clock forward instead of waiting.
extern uint64_t hlTestClockOffsetUs;
static inline uint64_t microtime(void)
{
  struct timespec time;
  clock_gettime(CLOCK_MONOTONIC, &time);
  return (uint64_t)time.tv_sec * 1000000ULL + time.tv_nsec / 1000 + hlTestClockOffsetUs;
}
""",
}

HARNESS = r"""
#include "pipewire.c"
#include <pthread.h>
#include <stdatomic.h>

uint64_t hlTestClockOffsetUs = 3600ULL * 1000000ULL;

// The stream is a fake that holds one ready buffer at a time.
static char fakeStream;
#define FAKE_STREAM ((struct pw_stream *)&fakeStream)
static uint8_t pixels[64];
static struct spa_chunk chunk = { .size = sizeof(pixels) };
static struct spa_data data = { .data = pixels, .chunk = &chunk };
static struct spa_buffer spaBuffer = { .n_datas = 1, .datas = &data };
static struct pw_buffer pwBuffer = { .buffer = &spaBuffer };
static atomic_int ready, queuedBack;

struct pw_buffer * pw_stream_dequeue_buffer(struct pw_stream * stream)
{
  return stream == FAKE_STREAM && atomic_exchange(&ready, 0) ? &pwBuffer : NULL;
}
int pw_stream_queue_buffer(struct pw_stream * stream, struct pw_buffer * buffer)
{
  atomic_fetch_add(&queuedBack, 1);
  return 0;
}
void pw_stream_destroy(struct pw_stream * stream) {}
int pw_stream_update_params(struct pw_stream * stream, const struct spa_pod ** params, uint32_t n_params)
{
  return 0;
}

bool framebuffer_write(FrameBuffer * frame, const void * src, size_t size) { return true; }
struct Portal * portal_create(void) { return NULL; }
void portal_free(struct Portal * portal) {}
bool portal_createScreenCastSession(struct Portal * portal, char ** handle) { return false; }
void portal_destroySession(struct Portal * portal, char ** sessionHandle) {}
bool portal_selectSource(struct Portal * portal, const char * sessionHandle) { return false; }
uint32_t portal_getPipewireNode(struct Portal * portal, const char * sessionHandle) { return 0; }
int portal_openPipewireRemote(struct Portal * portal, const char * sessionHandle) { return -1; }

static atomic_int inLoopThread;
static int markLoopThread(struct spa_loop * loop, bool async, uint32_t seq,
    const void * data, size_t size, void * user)
{
  atomic_store(&inLoopThread, pw_thread_loop_in_thread(this->threadLoop));
  return 0;
}

// A streaming capture on the real PipeWire thread loop.
static void streaming(void)
{
  pw_init(NULL, NULL);
  pipewire_create(NULL, NULL, 0);
  this->threadLoop = pw_thread_loop_new("hl-test", NULL);
  if (!this->threadLoop || pw_thread_loop_start(this->threadLoop) < 0)
  {
    printf("no PipeWire thread loop\n");
    exit(2);
  }
  // Until the PipeWire thread has entered its loop, pw_loop_invoke runs the
  // function on the caller, without the loop lock. Wait for it, so every
  // callback below runs on the PipeWire thread with the lock held, as in
  // the sender.
  atomic_store(&inLoopThread, 0);
  for (int i = 0; i < 500 && !atomic_load(&inLoopThread); ++i)
  {
    pw_loop_invoke(pw_thread_loop_get_loop(this->threadLoop), markLoopThread, 0, NULL, 0, true, NULL);
    if (!atomic_load(&inLoopThread))
      usleep(10 * 1000);
  }
  if (!atomic_load(&inLoopThread))
  {
    printf("the PipeWire thread never entered its loop\n");
    exit(2);
  }
  pw_thread_loop_lock(this->threadLoop);
  this->hasFormat   = true;
  this->stream      = FAKE_STREAM;
  this->width       = 4;
  this->height      = 4;
  this->pitch       = 16;
  this->lastFrameUs = microtime();
  pw_thread_loop_unlock(this->threadLoop);
}

static int runProcess(struct spa_loop * loop, bool async, uint32_t seq,
    const void * data, size_t size, void * user)
{
  streamProcessCallback(NULL);
  return 0;
}

// The producer delivers one usable frame from the PipeWire thread.
static void deliverFrame(void)
{
  atomic_store(&ready, 1);
  pw_loop_invoke(pw_thread_loop_get_loop(this->threadLoop), runProcess, 0, NULL, 0, false, NULL);
}

static void * deliverLater(void * opaque)
{
  usleep(200 * 1000);
  deliverFrame();
  return NULL;
}

static atomic_int deinitDone;
static void * runDeinit(void * opaque)
{
  pipewire_deinit();
  atomic_store(&deinitDone, 1);
  return NULL;
}

// A frame arrives while the capture restarts (the watchdog or a stream error
// asked for it): the frame callback now waits for an accept that never comes.
static int teardown(void)
{
  streaming();
  deliverFrame();
  bool waiting = false;
  for (int i = 0; i < 500 && !waiting; ++i)
  {
    pw_thread_loop_lock(this->threadLoop);
    waiting = this->frameData != NULL;
    pw_thread_loop_unlock(this->threadLoop);
    if (!waiting)
      usleep(10 * 1000);
  }
  if (!waiting)
  {
    printf("the frame never reached the callback\n");
    return 2;
  }

  // host/src/app.c: stopThreads() calls iface->stop(), then captureStop()
  // logs "Capture Stop" and calls iface->deinit().
  pipewire_stop();
  printf("Capture Stop\n");
  pthread_t thread;
  pthread_create(&thread, NULL, runDeinit, NULL);
  for (int i = 0; i < 500 && !atomic_load(&deinitDone); ++i)
    usleep(10 * 1000);
  if (!atomic_load(&deinitDone))
  {
    printf("deinit blocked after Capture Stop\n");
    fflush(stdout);
    _exit(1);
  }
  pthread_join(thread, NULL);
  printf("teardown finished\n");
  return 0;
}

static int runFormat(struct spa_loop * loop, bool async, uint32_t seq,
    const void * data, size_t size, void * user)
{
  uint8_t buffer[1024];
  struct spa_pod_builder builder = SPA_POD_BUILDER_INIT(buffer, sizeof(buffer));
  struct spa_video_info_raw info = { .format = SPA_VIDEO_FORMAT_BGRx, .size = SPA_RECTANGLE(4, 4) };
  const struct spa_pod * param = spa_format_video_raw_build(&builder, SPA_PARAM_Format, &info);
  streamParamChangedCallback(NULL, SPA_PARAM_Format, param);
  return 0;
}

static atomic_int formatDone;
static void * deliverFormat(void * opaque)
{
  pw_loop_invoke(pw_thread_loop_get_loop(this->threadLoop), runFormat, 0, NULL, 0, true, NULL);
  atomic_store(&formatDone, 1);
  return NULL;
}

// A format arrives after the stop, before deinit stops the PipeWire thread.
// The stop cleared hasFormat, so the callback hands the format over again;
// nothing accepts it any more, and the thread deinit joins would wait.
static int lateFormat(void)
{
  streaming();
  pipewire_stop();
  pthread_t thread;
  pthread_create(&thread, NULL, deliverFormat, NULL);
  for (int i = 0; i < 500 && !atomic_load(&formatDone); ++i)
    usleep(10 * 1000);
  if (!atomic_load(&formatDone))
  {
    printf("a format after the stop waited for an accept\n");
    fflush(stdout);
    _exit(1);
  }
  pthread_join(thread, NULL);
  pipewire_deinit();
  printf("a late format does not wait\n");
  return 0;
}

// A frame handed over while the capture is not waiting, between two
// captures: its signal reaches nobody and its callback waits for an accept.
// The next capture must take it, and the one after it must see the next.
static int missedWakeup(void)
{
  streaming();
  for (int frame = 1; frame <= 2; ++frame)
  {
    deliverFrame();
    bool waiting = false;
    for (int i = 0; i < 500 && !waiting; ++i)
    {
      pw_thread_loop_lock(this->threadLoop);
      waiting = this->frameData != NULL && atomic_load(&ready) == 0;
      pw_thread_loop_unlock(this->threadLoop);
      if (!waiting)
        usleep(10 * 1000);
    }
    const CaptureResult captured = pipewire_capture(0, NULL);
    if (captured != CAPTURE_RESULT_OK)
    {
      printf("frame %d, handed over between captures: the capture returned %s\n", frame,
          captured == CAPTURE_RESULT_TIMEOUT ? "a timeout" : "something else");
      fflush(stdout);
      _exit(1);
    }
    pipewire_getFrame(0, NULL, 1 << 20);
    for (int i = 0; i < 500 && atomic_load(&queuedBack) < frame; ++i)
      usleep(10 * 1000);
    if (atomic_load(&queuedBack) != frame)
    {
      printf("frame %d: %d buffers went back to the stream\n", frame, atomic_load(&queuedBack));
      return 1;
    }
    pw_thread_loop_lock(this->threadLoop);
    this->frameData = NULL;
    pw_thread_loop_unlock(this->threadLoop);
  }
  pipewire_stop();
  pipewire_deinit();
  printf("a frame handed over between captures is taken\n");
  return 0;
}

// Frames keep flowing: each one reaches the capture, is read, and its
// buffer goes back to the stream.
static int flow(void)
{
  streaming();
  for (int frame = 1; frame <= 3; ++frame)
  {
    pthread_t thread;
    pthread_create(&thread, NULL, deliverLater, NULL);
    const CaptureResult captured = pipewire_capture(0, NULL);
    pthread_join(thread, NULL);
    if (captured != CAPTURE_RESULT_OK)
    {
      printf("frame %d: capture returned %d\n", frame, captured);
      return 1;
    }
    if (pipewire_getFrame(0, NULL, 1 << 20) != CAPTURE_RESULT_OK)
    {
      printf("frame %d: getFrame failed\n", frame);
      return 1;
    }
    for (int i = 0; i < 500 && atomic_load(&queuedBack) < frame; ++i)
      usleep(10 * 1000);
    if (atomic_load(&queuedBack) != frame)
    {
      printf("frame %d: %d buffers went back to the stream\n", frame, atomic_load(&queuedBack));
      return 1;
    }
  }
  pipewire_stop();
  pipewire_deinit();
  printf("flowing 3\n");
  return 0;
}

int main(int argc, char ** argv)
{
  if (argc == 2 && !strcmp(argv[1], "teardown"))
    return teardown();
  if (argc == 2 && !strcmp(argv[1], "late-format"))
    return lateFormat();
  if (argc == 2 && !strcmp(argv[1], "flow"))
    return flow();
  if (argc == 2 && !strcmp(argv[1], "missed-wakeup"))
    return missedWakeup();
  return 2;
}
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def patched_source(patch: str) -> str:
    """pipewire.c after the patch, from the patch's one whole-file hunk."""
    files = re.split(r"(?m)^diff --git ", patch)[1:]
    require(len(files) == 1 and files[0].startswith(f"a/{TARGET} b/{TARGET}\n"),
            f"the runtime patch must change {TARGET} only")
    hunk = re.search(r"(?m)^@@ -1,\d+ \+1,(\d+) @@[^\n]*\n", files[0])
    require(hunk is not None and files[0].count("\n@@ ") == 1,
            "the runtime patch must carry the whole of pipewire.c in one hunk")
    body = files[0][hunk.end():]
    after = [line[1:] for line in body.splitlines() if line[:1] in (" ", "+")]
    require(len(after) == int(hunk.group(1)), "the runtime patch hunk is truncated")
    return "\n".join(after) + "\n"


def pkg_config(*args: str) -> list[str]:
    result = subprocess.run(["pkg-config", *args, "libpipewire-0.3"],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, f"libpipewire-0.3 development files are needed: {result.stderr}")
    return result.stdout.split()


def main() -> int:
    require(shutil.which("gcc") is not None, "gcc is needed to build the sender's capture")
    require(shutil.which("pkg-config") is not None, "pkg-config is needed to find libpipewire")
    source = patched_source(PATCH.read_text())
    with tempfile.TemporaryDirectory(prefix="hyperlab-lg-teardown-") as temporary:
        directory = Path(temporary)
        for name, text in STUBS.items():
            (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / name).write_text(text)
        (directory / "pipewire.c").write_text(source)
        (directory / "harness.c").write_text(HARNESS)
        binary = directory / "harness"
        built = subprocess.run(
            ["gcc", "-std=gnu11", "-Wall", "-Werror", "-Wno-unused-function",
             "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-I", str(directory),
             *pkg_config("--cflags"), "-o", str(binary), str(directory / "harness.c"),
             *pkg_config("--libs"), "-lpthread"],
            capture_output=True, text=True, check=False)
        require(built.returncode == 0, f"the patched pipewire.c did not build:\n{built.stderr}")
        for scenario, expected in (("teardown", "teardown finished"),
                                   ("late-format", "a late format does not wait"),
                                   ("flow", "flowing 3"),
                                   ("missed-wakeup", "a frame handed over between captures is taken")):
            try:
                run = subprocess.run([str(binary), scenario], capture_output=True, text=True,
                                     timeout=60, check=False)
            except subprocess.TimeoutExpired:
                raise AssertionError(f"{scenario}: the harness itself hung") from None
            lines = run.stdout.strip().splitlines()
            require(run.returncode == 0 and lines and lines[-1] == expected,
                    f"{scenario}: {run.stdout.strip()!r} (exit {run.returncode})\n{run.stderr[-2000:]}")
    print("Looking Glass sender teardown contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

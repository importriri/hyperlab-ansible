#!/usr/bin/env python3
"""The Linux sender's portal requests end, answered or not.

problems/looking-glass-sender-hung-after-capture-stop.md: after each
screen-cast portal request the pinned sender waited for the portal's
Response signal with no deadline, so a portal that never answers holds the
sender for good, alive and silent.

The portal patch carries the whole of portal.c in one hunk, so this
contract rebuilds the patched file and compiles it against the real GLib
main loop. Only the D-Bus calls are fakes (no bus is started): the
portal accepts every request and then either never answers, or answers
after 50 ms. With the deadline set to 0.3 s for the test:

  1. silent: CreateSession, SelectSources and Start each fail by
     themselves, near the deadline, and say so;
  2. answered: a Response that comes in time still completes CreateSession;
  3. destroy: closing a session clears the caller's handle. The pinned
     sender cleared only its own copy, so after every capture restart
     pipewire.c kept a freed handle; a re-init that failed before a new
     session (the portal could not be reached) then used it again.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "roles/guest_looking_glass_linux/files/portal-compat-runtime.patch"
TARGET = "host/platform/Linux/capture/pipewire/src/portal.c"
DEADLINE_US = 300000

STUBS = {
    "portal.h": r"""
#pragma once
#include <stdbool.h>
#include <stdint.h>
enum PipewireCaptureType { PIPEWIRE_CAPTURE_DESKTOP = 1, PIPEWIRE_CAPTURE_WINDOW = 2 };
struct Portal;
struct Portal * portal_create(void);
void portal_free(struct Portal * portal);
bool portal_createScreenCastSession(struct Portal * portal, char ** handle);
void portal_destroySession(struct Portal * portal, char ** sessionHandle);
bool portal_selectSource(struct Portal * portal, const char * sessionHandle);
uint32_t portal_getPipewireNode(struct Portal * portal, const char * sessionHandle);
int portal_openPipewireRemote(struct Portal * portal, const char * sessionHandle);
""",
    "common/debug.h": r"""
#pragma once
#include <inttypes.h>
#include <stdio.h>
#define HL_LOG(level, ...) (fprintf(stderr, level " " __VA_ARGS__), fputc('\n', stderr))
#define DEBUG_INFO(...)  HL_LOG("[I]", __VA_ARGS__)
#define DEBUG_WARN(...)  HL_LOG("[W]", __VA_ARGS__)
#define DEBUG_ERROR(...) HL_LOG("[E]", __VA_ARGS__)
""",
    "common/stringutils.h": r"""
#pragma once
#include <stdarg.h>
#include <stdio.h>
static inline int alloc_sprintf(char ** str, const char * format, ...)
{
  va_list ap;
  va_start(ap, format);
  const int length = vasprintf(str, format, ap);
  va_end(ap);
  if (length < 0)
    *str = NULL;
  return length;
}
""",
}

HARNESS = r"""
#include "portal.c"
#include <signal.h>
#include <unistd.h>

// The fake portal accepts every request; it answers only when asked to.
static bool answers;
static GDBusSignalCallback subscribed;
static gpointer subscribedData;
static const char * waiting = "nothing";

guint g_dbus_connection_signal_subscribe(GDBusConnection * connection,
    const gchar * sender, const gchar * interface_name, const gchar * member,
    const gchar * object_path, const gchar * arg0, GDBusSignalFlags flags,
    GDBusSignalCallback callback, gpointer user_data, GDestroyNotify user_data_free_func)
{
  subscribed = callback;
  subscribedData = user_data;
  return 1;
}

void g_dbus_connection_signal_unsubscribe(GDBusConnection * connection, guint subscription_id)
{
  subscribed = NULL;
  subscribedData = NULL;
}

static gboolean respond(gpointer opaque)
{
  if (!subscribed)
    return G_SOURCE_REMOVE;
  GVariantBuilder results;
  g_variant_builder_init(&results, G_VARIANT_TYPE_VARDICT);
  g_variant_builder_add(&results, "{sv}", "session_handle",
      g_variant_new_string("/org/freedesktop/portal/desktop/session/1_1/lg0"));
  GVariant * params = g_variant_ref_sink(g_variant_new("(ua{sv})", 0, &results));
  subscribed(NULL, ":1.1", "/request", "org.freedesktop.portal.Request", "Response",
      params, subscribedData);
  g_variant_unref(params);
  return G_SOURCE_REMOVE;
}

GVariant * g_dbus_proxy_call_sync(GDBusProxy * proxy, const gchar * method_name,
    GVariant * parameters, GDBusCallFlags flags, gint timeout_msec,
    GCancellable * cancellable, GError ** error)
{
  waiting = method_name;
  if (parameters)
    g_variant_unref(g_variant_ref_sink(parameters));
  if (answers)
    g_timeout_add(50, respond, NULL);
  return g_variant_ref_sink(g_variant_new("(o)", "/request"));
}

static int closed;
GVariant * g_dbus_connection_call_sync(GDBusConnection * connection, const gchar * bus_name,
    const gchar * object_path, const gchar * interface_name, const gchar * method_name,
    GVariant * parameters, const GVariantType * reply_type, GDBusCallFlags flags,
    gint timeout_msec, GCancellable * cancellable, GError ** error)
{
  ++closed;
  return NULL;
}

GVariant * g_dbus_proxy_get_cached_property(GDBusProxy * proxy, const gchar * property_name)
{
  return g_variant_ref_sink(g_variant_new_uint32(2));
}

static void hung(int signal)
{
  printf("%s waited without a deadline\n", waiting);
  fflush(stdout);
  _exit(1);
}

static double seconds(gint64 since)
{
  return (double)(g_get_monotonic_time() - since) / G_USEC_PER_SEC;
}

int main(int argc, char ** argv)
{
  struct Portal portal = { .senderName = "1_1" };
  signal(SIGALRM, hung);
  alarm(10);

  if (argc == 2 && !strcmp(argv[1], "silent"))
  {
    char * handle = NULL;
    gint64 start = g_get_monotonic_time();
    const bool created = portal_createScreenCastSession(&portal, &handle);
    const double createSeconds = seconds(start);
    start = g_get_monotonic_time();
    const bool selected = portal_selectSource(&portal, "/session");
    const double selectSeconds = seconds(start);
    start = g_get_monotonic_time();
    const uint32_t node = portal_getPipewireNode(&portal, "/session");
    const double startSeconds = seconds(start);
    if (created || handle || selected || node)
    {
      printf("a request without an answer succeeded\n");
      return 1;
    }
    if (createSeconds < 0.25 || createSeconds > 2 || selectSeconds < 0.25 || selectSeconds > 2 ||
        startSeconds < 0.25 || startSeconds > 2)
    {
      printf("the requests failed after %.2f, %.2f and %.2f s, not at the deadline\n",
          createSeconds, selectSeconds, startSeconds);
      return 1;
    }
    printf("every unanswered request failed at its deadline\n");
    return 0;
  }

  if (argc == 2 && !strcmp(argv[1], "destroy"))
  {
    // pipewire_deinit closes this->sessionHandle on every capture restart,
    // and again when a re-init fails before it creates a new session.
    char * handle = g_strdup("/org/freedesktop/portal/desktop/session/1_1/lg0");
    portal_destroySession(&portal, &handle);
    if (handle != NULL)
    {
      printf("closing the session left the freed handle in place\n");
      return 1;
    }
    portal_destroySession(&portal, &handle);
    if (closed != 1)
    {
      printf("a closed session was closed %d times\n", closed);
      return 1;
    }
    printf("a closed session's handle is cleared\n");
    return 0;
  }

  if (argc == 2 && !strcmp(argv[1], "answered"))
  {
    answers = true;
    char * handle = NULL;
    if (!portal_createScreenCastSession(&portal, &handle) || !handle ||
        strcmp(handle, "/org/freedesktop/portal/desktop/session/1_1/lg0"))
    {
      printf("an answered CreateSession did not complete\n");
      return 1;
    }
    printf("an answered request completes\n");
    return 0;
  }
  return 2;
}
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def patched_source(patch: str) -> str:
    """portal.c after the patch, from the patch's one whole-file hunk."""
    files = re.split(r"(?m)^diff --git ", patch)[1:]
    require(len(files) == 1 and files[0].startswith(f"a/{TARGET} b/{TARGET}\n"),
            f"the portal patch must change {TARGET} only")
    hunk = re.search(r"(?m)^@@ -1,\d+ \+1,(\d+) @@[^\n]*\n", files[0])
    require(hunk is not None and files[0].count("\n@@ ") == 1,
            "the portal patch must carry the whole of portal.c in one hunk")
    after = [line[1:] for line in files[0][hunk.end():].splitlines() if line[:1] in (" ", "+")]
    require(len(after) == int(hunk.group(1)), "the portal patch hunk is truncated")
    return "\n".join(after) + "\n"


def pkg_config(*args: str) -> list[str]:
    result = subprocess.run(["pkg-config", *args, "gio-2.0", "gio-unix-2.0"],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, f"GLib's GIO development files are needed: {result.stderr}")
    return result.stdout.split()


def main() -> int:
    require(shutil.which("gcc") is not None, "gcc is needed to build the sender's portal code")
    require(shutil.which("pkg-config") is not None, "pkg-config is needed to find GIO")
    source = patched_source(PATCH.read_text())
    with tempfile.TemporaryDirectory(prefix="hyperlab-lg-portal-") as temporary:
        directory = Path(temporary)
        for name, text in STUBS.items():
            (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / name).write_text(text)
        (directory / "portal.c").write_text(source)
        (directory / "harness.c").write_text(HARNESS)
        binary = directory / "harness"
        built = subprocess.run(
            ["gcc", "-std=gnu11", "-Wall", "-Werror", "-Wno-unused-function",
             f"-DHL_PORTAL_TIMEOUT_US={DEADLINE_US}", "-I", str(directory),
             *pkg_config("--cflags"), "-o", str(binary), str(directory / "harness.c"),
             *pkg_config("--libs")],
            capture_output=True, text=True, check=False)
        require(built.returncode == 0, f"the patched portal.c did not build:\n{built.stderr}")
        for scenario, expected in (("silent", "every unanswered request failed at its deadline"),
                                   ("answered", "an answered request completes"),
                                   ("destroy", "a closed session's handle is cleared")):
            try:
                run = subprocess.run([str(binary), scenario], capture_output=True, text=True,
                                     timeout=60, check=False)
            except subprocess.TimeoutExpired:
                raise AssertionError(f"{scenario}: the harness itself hung") from None
            lines = run.stdout.strip().splitlines()
            require(run.returncode == 0 and lines and lines[-1] == expected,
                    f"{scenario}: {run.stdout.strip()!r} (exit {run.returncode})\n{run.stderr[-2000:]}")
            if scenario == "silent":
                for request in ("CreateSession", "SelectSources", "Start"):
                    require(f"did not answer {request} within" in run.stderr,
                            f"an unanswered {request} is not logged:\n{run.stderr[-2000:]}")
    print("Looking Glass sender portal contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Nitro fans returned to automatic because the requested policy was 0,0

Author: [importriri](https://github.com/importriri).

## Symptom

The Nitro fan interface read `0,0` even though the intended host behavior was
maximum CPU and GPU fan duty after boot.

The settings service was enabled and successful, so the first suspicion was a
service ordering or persistence failure.

## What was wrong

The service had applied exactly what the role requested.

The rendered helper contained:

```text
fan_value="0,0"
```

and the role defaults also requested zero for both fan percentages. On this
interface `0,0` means firmware automatic control. The runtime state was
therefore internally consistent but inconsistent with the hardware policy
chosen for this lab.

## Fix

Make the intended Nitro policy explicit in role defaults:

```text
CPU fan: 100
GPU fan: 100
```

Do not change the native-first decision to pretend that this request can be
satisfied by an in-tree platform-profile path. A non-zero manual fan policy is
one of the reasons the native path is insufficient and the out-of-tree opt-in
remains required.

The helper continues to write and read back the requested value instead of
assuming that a successful systemd unit means the setting reached hardware.

## Regression proof

The installed helper rendered `fan_value="100,100"` and the live Nitro fan
interface read `100,100`. `nitro-sense-apply.service` remained successful and
the battery limiter simultaneously read the requested value `1`.

The distinction between service health and policy correctness is now preserved:
a green oneshot service is not evidence that the requested value itself was the
right one.

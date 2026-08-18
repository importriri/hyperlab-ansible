# Nitro suspend evidence was captured before the machine resumed

Author: [importriri](https://github.com/importriri).

## Symptom

The first AN515-55 suspend gate reported a successful post-resume runtime
comparison, but its network snapshot showed `wlan0` down.

That result looked like a resume regression even though the later physical
checks passed and Wi-Fi was usable.

## What was wrong

The evidence wrapper treated the return of `systemctl suspend` as proof that a
complete suspend/resume cycle had finished. On this host the command returned
after the request was accepted, before the machine had actually entered and
left deep sleep.

The timestamps made the race visible. The supposed post-resume snapshot was
captured at `15:20:25`; the kernel recorded `PM: suspend entry (deep)` at that
time and did not record `PM: suspend exit` until `15:29:36`.

The down wireless interface belonged to the transition into sleep. It was not a
snapshot of the recovered system. The role and driver had not failed; the test
harness had observed the wrong lifecycle boundary.

## Fix

The gate now records a pre-request journal marker and waits for a newer kernel
`PM: suspend exit` event before it captures post-resume state. The wait is
bounded, and absence of the marker fails the gate instead of manufacturing a
post-resume result.

Runtime services, fan and battery values, broker state, network link and route
are collected only after that kernel boundary is present.

## Regression evidence

The repaired proof found the real suspend entry at `15:20:25` and exit at
`15:29:36`. Its later runtime snapshot showed both Nitro services active and
enabled, fan policy `100,100`, battery limiter `1`, unchanged four-zone state,
`wlan0` `UP,LOWER_UP` and a route through `wlan0`.

Brightness, audio, wireless, Nitro-key and fan behavior also passed physical
checks after resume.

A suspend command returning is not accepted as resume evidence. Future gates
must anchor the post-state to a kernel resume event and then prove the recovered
runtime independently.

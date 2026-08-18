# Linuwu-Sense logged an unclassified WMI function-four event

Author: [importriri](https://github.com/importriri).

## Symptom

The AN515-55 suspend campaign recorded 48 messages in this form while physical
function-key checks were being exercised:

```text
linuwu_sense: Unknown function number - 4 - 0
```

The message appeared before and after suspend. It did not appear during the
later controlled rollback/reinstall transition.

## What is known

The pinned driver emits this message from the default branch of its WMI event
switch when an event function is not one of the cases it handles explicitly.
The reviewed source is
[`linuwu_sense.c`](https://github.com/0x7375646F/Linuwu-Sense/blob/73a25ec243a44ba2b1703e8d0a76fa2735062506/src/linuwu_sense.c).

The evidence identifies function `4` and device `0`. It does not establish what
firmware action that pair represents, so the repository does not assign it a
name or add a guessed handler.

## Classification

This remains an open observation rather than a failed acceptance gate for the
tested candidate.

Brightness, volume and mute, Wi-Fi, the Nitro key, suspend/resume, fan control,
battery control and four-zone static lighting all passed their physical checks.
The genuine post-resume state matched the pre-suspend state, and the driver
journal contained no matching error, failure, timeout, oops or kernel bug.

That evidence does not prove function `4` harmless on every Acer model. It only
shows that the observed messages did not coincide with a tested AN515-55
regression.

## Regression boundary

Hardware gates keep the message visible and count exact occurrences. A new
function/device pair, a material increase without operator input, or any loss of
the tested platform functions reopens this investigation.

The warning must not be suppressed merely to make the journal quiet. It is more
useful as a tracked unknown until its firmware meaning is established.

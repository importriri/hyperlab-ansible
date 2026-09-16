# Nitro settings were not reapplied after a managed driver reload

## Symptom

During the Linux 7.2 DKMS transition the managed Linuwu-Sense module built
and loaded successfully, but the role later rejected the configured fan
value and entered its full acer_wmi rollback path.

The persistent settings unit was already active from the current boot.

## Failure boundary

`nitro-sense-apply.service` is a oneshot service with `RemainAfterExit=yes`.
An active oneshot is not executed again merely because Ansible requests
`state: started`.

The role can replace or reload the platform module before including its
settings configuration. A freshly loaded module begins with its own runtime
state, so the previously completed oneshot no longer proves that the current
module instance has received HyperLab's persistent policy.

This is an orchestration failure, not a Linux 7.2 compile failure and not a
firmware refusal of the reviewed fan range.

## Repair

The settings-service task now records whether `state: started` actually
changed the service.

When the role performed a platform-driver transition and the settings
service was already active, the role explicitly restarts the settings
oneshot before validating the hardware state.

A newly installed or newly started service is not restarted a second time.
Normal idempotent runs do not restart it.

Template changes still use the existing handler path.

## Runtime proof

The regression test is physical, not only static:

1. reconcile the managed replacement and persistent settings;
2. verify an idempotent second apply;
3. stop the runtime broker and deliberately unload only `linuwu_sense`;
4. run the canonical role again;
5. require the role to reload the driver and reapply the configured fan and
   battery settings;
6. require one final idempotent run.

The existing rescue path remains responsible for restoring `acer_wmi` if
the managed transaction fails.

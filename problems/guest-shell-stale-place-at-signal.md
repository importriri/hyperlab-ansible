# The Desk OSD announced the project of the Desk being left

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest workspace shell runtime
contract. Physical acceptance on a guest is pending.

## Symptom

Switching from Programming (project HyperLab) to Desk 2 showed an OSD reading
`Programming` over `DESK 2 · HYPERLAB`: the right Desk number, with the name
and project of the Desk just left. The context island, read a moment later,
was correct.

## Root cause

`DeskState` publishes the current place as a binding:

```qml
readonly property var place: Desks.place(state.model, state.activeWorkspace)
```

and emits `deskEntered(desk)` from `onActiveWorkspaceChanged`. The OSD read
`deskState.place` inside that signal handler. A change handler can run before
QML has re-evaluated the other bindings that depend on the same property, so
the handler saw the `place` computed for the previous workspace. The Desk
number was right only because it travelled in the signal argument.

## Fix

`DeskState.placeNow()` computes the place from the model and the active
workspace at the moment it is called, and every signal-time reader uses it.
Bindings keep using `place`, where Qt orders the evaluation itself.

## Regression proof

`tests/guest_workspace_shell_runtime_contract.py` (desktop scenario) moves the
compositor from workspace 11 to 21 and requires the OSD to read
`DESK 2 · BLENDER RENDERS` and the context island to name Blender renders.
Reading `deskState.place` in the OSD again fails the scenario.

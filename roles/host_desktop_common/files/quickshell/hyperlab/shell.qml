//@ pragma ShellId hyperlab

// HyperLab Platform shell entry point (V447-C9.3).
//
// One long-running shell process owns every HyperLab surface. One state
// layer, one action layer, one machine-operation layer, one theme, one token
// set and one surface coordinator are created for the session and injected
// into every surface, so runtime data is read once regardless of how many
// outputs the host drives and every surface speaks the same visual language.
//
//   HyperLab Shell
//   ├── HyperLabBar        top rail, per screen
//   ├── HyperLabDesktop    quiet idle desktop, per screen
//   ├── WorkspaceSurface   the product workspace, one ordinary window
//   ├── SystemPanel        quick settings, on the summoning output
//   ├── OsdSurface         on-screen display, on the summoning output
//   ├── LauncherSurface    command palette, on the summoning output
//   └── ShellIpc           fixed IPC receivers
//
// Operation results are observed here, once, and published into the state
// layer. Nothing downstream infers a result from a process ending.

import Quickshell
import QtQuick

ShellRoot {
    id: shell

    Tokens {
        id: sharedTokens

        // Reduced motion is a host setting, not a build-time constant.
        reducedMotion: sharedState.reducedMotion
    }

    Icons {
        id: sharedIcons
    }

    Theme {
        id: sharedTheme
    }

    ShellState {
        id: sharedState
    }

    ShellSurfaces {
        id: sharedSurfaces

        // Where a keyboard or IPC request lands: the compositor's focused
        // output when it names a live screen, otherwise the first live
        // screen. Never "every output" and never an empty owner.
        activeOutput: {
            const screens = Quickshell.screens;
            const focused = sharedState.focusedOutput;

            for (let index = 0; index < screens.length; index++) {
                if (String(screens[index].name) === focused)
                    return focused;
            }

            return screens.length > 0 ? String(screens[0].name) : "";
        }

        liveOutputs: Quickshell.screens.map(screen => String(screen.name))
    }

    ShellActions {
        id: sharedActions

        onActionFinished: action => {
            sharedState.settleAction(action);
        }

        // Locking from inside the shell withdraws armed state at once; the
        // lock helper also notifies the shell for every other lock path.
        onActionStarted: action => {
            if (action === "session-lock")
                sharedSurfaces.sessionLocking();
        }

        // A host action reports its own outcome. A failure is recorded as a
        // failure; nothing here turns an exit code into apparent success,
        // and only the OSD reporting this very action is settled by it.
        onActionResult: (action, ok, detail) => {
            sharedSurfaces.settleActionOsd(action, ok, detail);

            sharedState.recordOperation({
                "id": "host:" + action,
                "kind": "session",
                "label": sharedActions.labelFor(action),
                "target": "host",
                "phase": ok ? "completed" : "failed",
                "detail": detail
            });
        }
    }

    MachineActions {
        id: sharedMachineActions

        // Transport in, observation out: the state layer decides whether a
        // reply answers the question currently being asked.
        onCapabilityRequested: (serial, machine, generation) => {
            sharedState.beginCapabilityRequest(serial, machine, generation);
        }

        onCapabilityAnswered: (serial, machine, raw, exitCode, detail) => {
            sharedState.applyCapabilityAnswer(
                serial,
                machine,
                raw,
                exitCode,
                detail
            );
        }

        onCapabilitiesCleared: sharedState.clearCapabilities()

        onAccepted: (verb, machine) => {
            sharedState.recordOperation({
                "id": "machine:" + machine + ":" + verb,
                "kind": "machine",
                "label": sharedMachineActions.labelFor(verb),
                "target": machine,
                "phase": "accepted",
                "detail": ""
            });
        }

        onSettled: (verb, machine, phase, detail) => {
            sharedState.recordOperation({
                "id": "machine:" + machine + ":" + verb,
                "kind": "machine",
                "label": sharedMachineActions.labelFor(verb),
                "target": machine,
                "phase": phase,
                "detail": detail
            });

            // Read the host back rather than assuming the machine moved.
            sharedState.refreshInventory();
        }
    }

    ShellIpc {
        shellState: sharedState
        shellSurfaces: sharedSurfaces
        theme: sharedTheme
    }

    Variants {
        model: Quickshell.screens

        HyperLabBar {
            tokens: sharedTokens
            theme: sharedTheme
            icons: sharedIcons
            shellState: sharedState
            shellActions: sharedActions
            shellSurfaces: sharedSurfaces
        }
    }

    Variants {
        model: Quickshell.screens

        HyperLabDesktop {
            tokens: sharedTokens
            theme: sharedTheme
            icons: sharedIcons
            shellState: sharedState
            shellSurfaces: sharedSurfaces
        }
    }

    // The product workspace is one ordinary compositor-managed window, not a
    // surface mirrored onto every output.
    WorkspaceSurface {
        tokens: sharedTokens
        theme: sharedTheme
        icons: sharedIcons
        shellState: sharedState
        shellActions: sharedActions
        machineActions: sharedMachineActions
        shellSurfaces: sharedSurfaces
    }

    Variants {
        model: Quickshell.screens

        SystemPanel {
            tokens: sharedTokens
            theme: sharedTheme
            icons: sharedIcons
            shellState: sharedState
            shellActions: sharedActions
            shellSurfaces: sharedSurfaces
        }
    }

    Variants {
        model: Quickshell.screens

        OsdSurface {
            tokens: sharedTokens
            theme: sharedTheme
            icons: sharedIcons
            shellState: sharedState
            shellSurfaces: sharedSurfaces
        }
    }

    Variants {
        model: Quickshell.screens

        LauncherSurface {
            tokens: sharedTokens
            theme: sharedTheme
            icons: sharedIcons
            shellState: sharedState
            shellActions: sharedActions
            shellSurfaces: sharedSurfaces
        }
    }
}

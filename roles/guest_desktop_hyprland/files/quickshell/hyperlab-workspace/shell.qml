//@ pragma ShellId hyperlab-workspace

// HyperLab Workspace Shell: the desktop of a HyperLab guest workstation.
//
// One process owns every surface. One theme, one Desk state, one set of
// system readouts and one surface controller are created once and handed to
// every surface:
//
//   Workspace Shell
//   ├── DesktopLayer   clock and greeting under the windows
//   ├── TopLayer       context island (Desk / Project) and status island
//   ├── DockLayer      Desks, workspaces of the current Desk, launcher
//   ├── DeskOverview   ALT+D, every Desk and its projects
//   ├── Launcher       ALT+Space, applications, projects and actions
//   ├── Cheatsheet     ALT+H, every guest key from keys.json
//   ├── Osd            Desk changes, volume, helper outcomes
//   └── Ipc            fixed receivers for the key bindings
//
// The guest shell shows no trust. What this machine is, and what it may
// reach, is said only by the host frame around it.

import Quickshell
import Quickshell.Hyprland
import QtQuick

ShellRoot {
    id: shell

    Theme {
        id: sharedTheme
    }

    DeskState {
        id: sharedDesks
    }

    SystemStats {
        id: sharedStats
    }

    Surfaces {
        id: sharedSurfaces
    }

    Ipc {
        surfaces: sharedSurfaces
        deskState: sharedDesks
    }

    // Transient surfaces appear on the output that has focus.
    function isPrimary(screen) {
        const screens = Quickshell.screens;
        if (screens.length <= 1)
            return true;
        const focused = Hyprland.focusedMonitor ? String(Hyprland.focusedMonitor.name) : "";
        return screen !== null && screen !== undefined && String(screen.name) === focused;
    }

    Variants {
        model: Quickshell.screens

        DesktopLayer {
            theme: sharedTheme
            deskState: sharedDesks
        }
    }

    Variants {
        model: Quickshell.screens

        TopLayer {
            theme: sharedTheme
            deskState: sharedDesks
            stats: sharedStats
            surfaces: sharedSurfaces
        }
    }

    Variants {
        model: Quickshell.screens

        DockLayer {
            theme: sharedTheme
            deskState: sharedDesks
            surfaces: sharedSurfaces
        }
    }

    Variants {
        model: Quickshell.screens

        DeskOverview {
            theme: sharedTheme
            deskState: sharedDesks
            surfaces: sharedSurfaces
            primary: shell.isPrimary(screen)
        }
    }

    Variants {
        model: Quickshell.screens

        Launcher {
            theme: sharedTheme
            deskState: sharedDesks
            surfaces: sharedSurfaces
            primary: shell.isPrimary(screen)
        }
    }

    Variants {
        model: Quickshell.screens

        Cheatsheet {
            theme: sharedTheme
            surfaces: sharedSurfaces
            primary: shell.isPrimary(screen)
        }
    }

    Variants {
        model: Quickshell.screens

        Osd {
            theme: sharedTheme
            deskState: sharedDesks
            stats: sharedStats
            primary: shell.isPrimary(screen)
        }
    }
}

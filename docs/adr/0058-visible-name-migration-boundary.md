# ADR 0058 - Record the remaining visible name migration

Status: Proposed.

## Context

The native shell and CLI presentation read the shared product identity, but
Ly session entries and the retained GTK, Waybar, native Sway bar and rofi
surfaces still display the previous name. They are visible product surfaces,
not internal identifiers. Renaming their static entries safely requires their
deployment and runtime readers to consume the shared identity as well.

The product documentation contract forbade every old product word except the
history sentence. That also rejected an accurate description of the session
labels actually installed in Ly. Replacing those labels with generic prose
hid an unfinished migration and made the README less useful at login.

## Decision

Proposed: retain these existing recovery/session surfaces for now and list
each one in an open release-roadmap item. Keep the physical presentation
gate open. The software checkbox covers only the named native-shell, CLI
banner and notification surfaces, not completion of the visible migration.

Correct the documentation check with one exact README sentence naming the
installed Ly sessions. Parse the desktop entries to pin those names, and
parse the Waybar brand/tooltip to keep the deferred inventory explicit.
All other old product prose remains rejected except the history sentence.
This exception documents existing behavior; it does not permit additional
old-name strings or change command names, paths or session identifiers.

## Evidence and consequences

The product contract requires the exact session-label sentence and the open
inventory. Removing either fails. New help literals naming the old product
also fail through an AST check; the two existing literals rewritten by the
CLI formatter are enumerated explicitly. Native presentation continues to
reject old names in evaluated text and accessibility attributes.

A later visible migration must update deployment, runtime consumers, the
inventory and these narrow checks together. No Nitro or Predator visual
acceptance follows from these software results.

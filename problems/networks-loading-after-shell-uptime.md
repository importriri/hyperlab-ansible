# An on-demand network read must not inherit shell startup age

The Networks page starts its inventory read only when opened. The shared
source-health helper treats a source still loading 90 seconds after shell
startup as unavailable. Networks used that helper for its initial loading
state, so opening or reopening the page after that uptime showed "Networks
unavailable" before any reply or failure. A slow read kept the false failure
label until its own 15-second deadline.

## Fix

Networks presents its initial loading state directly and lets its existing
completion deadline report an unanswered read as unavailable. Other sources
keep the shared startup rule. A published Networks observation still uses
the shared 90-second freshness boundary; failure and timeout still withhold
rows, and a fresh valid answer recovers.

Cancellation signals the bridge process only. It does not terminate CLI
descendants as a group, so a child read can outlive the bridge. The shell
documentation describes this limit without claiming descendant cleanup.

## Regression proof

The offscreen QML scenario advances observation time past shell startup by
91 seconds, opens Networks and checks both loading status and the visible
"Reading declared networks" label before any reply. A valid answer becomes
ready. Reopening after longer uptime stays loading until its own deadline;
a timeout becomes unavailable and refuses a late answer, then a new valid
answer recovers. Removing the Networks-specific loading rule fails with
"Networks first read after shell uptime became unavailable"; restoring it
passes. The late-answer scenario also requires signal 9 immediately after
hiding and a new signal on disabling. Removing cancellation on hide fails
with "Networks hide did not stop its bridge process".

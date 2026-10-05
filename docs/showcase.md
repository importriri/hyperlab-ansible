# Showcase: from Golden Image to running Machine

A short public demonstration of HyperLab, recorded on the host. It shows
what the platform does, in the order an operator meets it, and claims
nothing the film does not show. HyperLab is not described as providing the
security properties of Qubes OS.

## Storyboard (about 80 seconds)

| Shot | Seconds | On screen | What it shows |
|---|---|---|---|
| 1 | 5 | the quiet desktop: wallpaper and the rail | the host is a calm control plane |
| 2 | 20 | Machines → New Machine → Development Workstation, name, dev network, Balanced, Create; the operation window | a Machine is a Template's offer, chosen within its limits; privilege is asked in one place |
| 3 | 15 | the new card turns Running; its Template, image digest and network | the Machine comes from a sealed Golden Image pinned by digest |
| 4 | 10 | the GPU badge; later the per-run lease | the GPU is owned by one running Machine, under the trust ladder |
| 5 | 20 | Looking Glass: the guest's Workspace Shell, two Desks, the overview, the launcher | the workstation inside the Machine |
| 6 | 10 | the host frame colour and Diagnostics | the host, never the guest, says which network a surface belongs to |

Shot 4 waits for the GPU lease ([ADR 0019](adr/0019-gpu-lease.md)); until
it exists the shot shows the badge only, or is cut.

## Running the take

```sh
tools/showcase/demo.sh demo-01
```

The script never changes the host. It checks that the shell answers and
that the Machine does not exist yet, prints what must not appear in the
published film, then walks the shots: it opens each shell surface through
its reviewed IPC target, says what to do, and waits until the inventory
shows the Machine running before the shots that need it. The Machine is
created by hand in the shell, as the film shows; the password is typed in
the operation window, off camera. Afterwards the demo Machine is destroyed
like any other.

## Review before publishing

Watch the whole take, then every frame where text is on screen, and refuse
it if any of these appears:

- the host name, the user name or a home path (the script prints the ones
  of this host before the take);
- an IP address, a MAC address, an SSH key fingerprint or a host key;
- a path under `/run/user`, a token, or any file the operator keeps private;
- a window that is not part of the storyboard, or a notification.

Captions say only what the shot shows. Editing never joins two takes in a
way that hides a step the platform did not do.

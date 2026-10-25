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
it exists the shot shows the badge only, or is cut, and the demo script
says so at that shot.

## Running the take

```sh
tools/showcase/demo.sh demo-01
```

The script never changes the host. Before the first shot it checks that
`hyperlabctl`, Quickshell, Python and `sleep` are installed, that the shell
answers, and that the Machine inventory is readable and does not hold the
name yet.
The name is refused, before anything runs, unless it is 2 to 31 lowercase
letters, digits and dashes starting with a letter. The script then prints a
generic list of what must not appear in the published film, and walks the
shots: it opens each shell surface through its reviewed IPC target, says
what to do, and waits until the inventory shows the Machine running before
the shots that need it, at most 15 minutes. The Machine is created by hand
in the shell, as the film shows; the password is typed in the operation
window, off camera. Afterwards the demo Machine is destroyed like any other.

Its terminal may be on camera, so the script never reads the host name,
the user name, the home path or an address, and never shows the output of
the tools it calls: a failure prints one fixed reason, such as `demo: the
HyperLab shell does not answer; start the session first`, and stops the take
with a nonzero status. The Looking Glass client opened for shot 5 keeps
running after the take, so the script does not wait for it: if it has
already ended with an error when shot 5 is done, or before the take is
called complete, the take stops with `demo: Looking Glass failed for NAME`.
A client that fails after that is not seen by the script.

`tests/showcase_contract.py` runs the whole take and each failure from a
checkout inside a made-up home, with stub tools that answer with made-up
host values, and fails if one of them reaches either output stream.

## Review before publishing

A clean script transcript proves nothing about the other windows, the
notifications or the recorded frames. Watch the whole take, then every frame
where text is on screen, and refuse it if any of these appears:

- the host name, the user name or a home path;
- an IP address, a MAC address, an SSH key fingerprint or a host key;
- a path under `/run/user`, a token, or any file the operator keeps private;
- a window that is not part of the storyboard, or a notification.

Captions say only what the shot shows. Editing never joins two takes in a
way that hides a step the platform did not do.

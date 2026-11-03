# The capability contract needed an undeclared CI runtime

## Finding

The capability transport contract requires real Quickshell processes to
check failed starts, stream completion and cancellation. Local and nested
desktop environments provided `qs`, but the hosted Ubuntu 26.04 toolchain
did not. Its discovered contract loop would therefore fail before testing
the transport. The contributor prerequisites also omitted Quickshell.

## Fix and evidence

Ubuntu's [package index](https://packages.ubuntu.com/quickshell) lists
Quickshell only for a newer suite. The fixed toolchain builds upstream
v0.3.2 from a SHA-256 checked archive against its own Qt private headers,
installs into a private prefix and requires `qs --version` before running
contracts. Unused compositor and desktop services are disabled; the real
process transport remains enabled. The build follows upstream's
[build instructions](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/BUILD.md).
The contributor table and Arch command now include `quickshell`.

With the system `qs` hidden from PATH, the transport contract refuses its
missing runtime. The same workflow build supplies the executable for that
isolated PATH; removing installation must bring back the missing-runtime
failure. This local build does not prove Ubuntu package installation or a
hosted workflow run; those remain CI acceptance.

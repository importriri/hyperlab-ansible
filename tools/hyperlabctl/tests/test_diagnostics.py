"""Collect one Machine's diagnostics, redacted and private."""

import json
import stat
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

from harness import check, equals
from hyperlabctl.commands import diagnostics as diag
from hyperlabctl.errors import ContractError

SECRETS = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----",
    "password=hunter2",
    'passphrase: "correct horse"',
    "Authorization: Bearer abc.def.ghi",
    "$6$saltsalt$Qx0Zy1hashhashhashhash",
    "ghp_" + "a" * 36,
    "glpat-" + "b" * 20,
    "AKIA" + "C" * 16,
    "xoxb-1234567890-abcdef",
    "sid@example.org",
)


def test_the_redactor_removes_every_kind_of_secret():
    text = "\n".join("line %d %s end" % (i, secret) for i, secret in enumerate(SECRETS))
    clean, count = diag.redact(text)
    for secret in SECRETS:
        core = secret.split("=")[-1].split(": ")[-1].strip('"')
        check("redacted_%s" % secret[:12], core not in clean, clean)
    equals("redaction_count", count, len(SECRETS))
    plain, none = diag.redact("dev-01 started on 10.10.3.105 at 12:00, sender streaming\n")
    equals("plain_text_untouched", (plain, none),
           ("dev-01 started on 10.10.3.105 at 12:00, sender streaming\n", 0))


def _fake_run(calls):
    def run(argv, **kwargs):
        calls.append(argv)
        text = "%s output with password=hunter2 and sid@example.org\n" % " ".join(argv)[:40]
        if argv[:2] == ["hyperlabctl", "--json"]:
            text = json.dumps({"machines": [{"name": "dev-01", "token": "x"}, {"name": "srv-01"}]})
        if "dominfo" in argv:
            return SimpleNamespace(returncode=1, stdout="", stderr="error: failed to get domain")
        return SimpleNamespace(returncode=0, stdout=text, stderr="")
    return run


def test_collect_writes_a_private_redacted_archive():
    calls = []
    saved = (diag._ssh_argv, diag._wait_for_ssh_ready)
    diag._ssh_argv = lambda ctx, name: ["ssh", "-o", "BatchMode=yes", "sid@" + name]
    diag._wait_for_ssh_ready = lambda argv, name: None
    try:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "diagnostics"
            path, manifest = diag.collect(None, "dev-01", run=_fake_run(calls), output=out, now=0)
            check("archive_private", stat.S_IMODE(path.stat().st_mode) == 0o600)
            check("directory_private", stat.S_IMODE(out.stat().st_mode) == 0o700)
            with tarfile.open(path) as archive:
                members = {m.name.split("/", 1)[1]: m for m in archive.getmembers()}
                contents = {name: archive.extractfile(m).read().decode() for name, m in members.items()}
            check("members_private", all(m.mode == 0o600 for m in members.values()))
            for name, text in contents.items():
                check("no_password_in_%s" % name, "hunter2" not in text)
                check("no_email_in_%s" % name, "sid@example.org" not in text)
            inventory = json.loads(contents["host/machine-inventory.json"])
            equals("only_this_machine", [row["name"] for row in inventory], ["dev-01"])
            check("dominfo_missing", "host/domain-info.txt" in manifest["missing"])
            check("guest_logs_collected", "guest/looking-glass-host.log" in manifest["files"])
            check("manifest_in_archive", json.loads(contents["manifest.json"])["machine"] == "dev-01")
            check("redactions_counted", manifest["files"]["guest/journal-user.txt"]["redactions"] >= 2)
    finally:
        diag._ssh_argv, diag._wait_for_ssh_ready = saved
    flat = " ".join(" ".join(argv) for argv in calls)
    for forbidden in (".ssh/", "-access.yml", "cloud-init", "user-data", "seed.iso", "/run/user"):
        check("never_reads_%s" % forbidden, forbidden not in flat, flat)
    check("virsh_read_only", all("-r" in argv for argv in calls if argv[:1] == ["virsh"]))


def test_collect_refuses_a_bad_name_and_works_without_the_guest():
    for name in ("../x", "Dev-01", "", "a" * 40):
        try:
            diag.collect(None, name, run=_fake_run([]), output="/nonexistent")
            check("refused_%r" % name, False)
        except ContractError:
            check("refused_%r" % name, True)
    calls = []
    with tempfile.TemporaryDirectory() as td:
        _, manifest = diag.collect(None, "srv-01", run=_fake_run(calls), output=Path(td), now=0, with_guest=False)
    check("host_only_has_no_guest", not any(path.startswith("guest/") for path in manifest["files"]))
    check("host_only_never_ssh", not any(argv[:1] == ["ssh"] for argv in calls))

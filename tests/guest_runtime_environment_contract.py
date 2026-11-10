#!/usr/bin/env python3
"""The guest fixtures can launch a user-installed Ansible with a private HOME."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("ANSIBLE_INVENTORY", "ANSIBLE_CALLBACK_PLUGINS", "SSH_AUTH_SOCK", "PYTHONPATH")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="guest-runtime-environment-") as temporary:
        root = Path(temporary)
        userbase = root / "userbase"
        packages = Path(sysconfig.get_path("purelib", scheme="posix_user",
                                          vars={"userbase": str(userbase)}))
        packages.mkdir(parents=True)
        (packages / "guest_fixture_dependency.py").write_text("TOKEN = 'user-site-only'\n", encoding="utf-8")
        bindir = userbase / "bin"
        bindir.mkdir()
        launcher = bindir / "ansible-playbook"
        launcher.write_text(f'''#!{sys.executable}
import json
import os
import sys
from guest_fixture_dependency import TOKEN

print(json.dumps({{
    "argv": sys.argv[1:], "token": TOKEN,
    "home": os.environ["HOME"], "path": os.environ["PATH"],
    "configuration": os.environ["ANSIBLE_CONFIG"],
    "temporary": [os.environ[key] for key in
                  ("ANSIBLE_HOME", "ANSIBLE_LOCAL_TEMP", "ANSIBLE_REMOTE_TEMP")],
    "inherited": [key for key in {FORBIDDEN!r} if key in os.environ],
}}))
''', encoding="utf-8")
        launcher.chmod(0o700)
        driver = root / "driver.py"
        # Keep the driver's own installed dependencies available even though
        # this fresh interpreter starts with a different Python user base.
        # The launcher gets only the environment the real helper constructs.
        driver.write_text(f'''
import json
import subprocess
import sys
from pathlib import Path
sys.path[:0] = {[str(ROOT / "tests"), *sys.path]!r}
import guest_contract

workspace = Path(sys.argv[1])
argv, environment = guest_contract.playbook_invocation(workspace, [{{
    "hosts": "localhost", "gather_facts": False,
    "tasks": [{{"ansible.builtin.assert": {{"that": [True]}}}}],
}}], {{}}, "--check")
result = subprocess.run(argv, cwd=workspace, env=environment, text=True,
                        capture_output=True, timeout=30, check=False)
print(json.dumps({{"argv": argv, "returncode": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}}))
''', encoding="utf-8")
        environment = {"PATH": str(bindir), "HOME": str(root / "caller-home"),
                       "PYTHONUSERBASE": str(userbase), "LC_ALL": "C.UTF-8",
                       **dict.fromkeys(FORBIDDEN, "/unusable-caller-setting")}
        workspace = root / "workspace"
        workspace.mkdir()
        result = subprocess.run([sys.executable, str(driver), str(workspace)], env=environment,
                                text=True, capture_output=True, timeout=45, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        observed = json.loads(result.stdout)
        assert observed["argv"][0] == str(launcher), "guest fixture did not execute the caller's Ansible launcher"
        assert observed["returncode"] == 0, observed["stderr"]
        record = json.loads(observed["stdout"])
        assert record["token"] == "user-site-only", record
        assert record["argv"] == observed["argv"][1:], record
        assert record["argv"] == ["-i", "localhost,", "-e", f"@{workspace / 'playbook-0-vars.json'}",
                                  "--check", str(workspace / "playbook-0.yml")], record
        assert record["home"] == str(workspace), "guest fixture lost its private HOME"
        assert record["path"] == "/usr/local/bin:/usr/bin:/bin", "guest fixture inherited the caller's PATH"
        assert record["configuration"] == str(ROOT / "ansible.cfg"), "guest fixture lost its repository Ansible configuration"
        assert record["temporary"] == [str(workspace / name) for name in
                                        ("ansible-home", "ansible-local", "ansible-remote")], "guest fixture lost its private Ansible directories"
        assert record["inherited"] == [], "guest fixture inherited caller configuration"

        # Neither the helper nor its child may fall back to a system Ansible
        # when the caller cannot resolve the required executable.
        launcher.unlink()
        refused = subprocess.run([sys.executable, str(driver), str(workspace)], env=environment,
                                 text=True, capture_output=True, timeout=45, check=False)
        assert refused.returncode != 0, "guest fixture accepted a missing Ansible launcher"
        assert "ansible-playbook is required for guest runtime fixtures" in refused.stderr, (
            f"missing launcher did not produce a deliberate refusal: {refused.stderr}")
        # Check that this case really hid every launcher from the caller.
        assert shutil.which("ansible-playbook", path=environment["PATH"]) is None
    print("guest runtime environment contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

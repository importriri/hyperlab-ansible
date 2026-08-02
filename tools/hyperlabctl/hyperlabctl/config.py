"""Where the CLI reads the contract from.

Nothing here decides policy. Every number and every path is already declared
somewhere in the repository or written by a brick; this module only locates it.
"""

import os
import socket
from pathlib import Path

from .errors import ContractError, HyperlabError, Unavailable

DEFAULTS = {
    "hardware_profile_report": "/etc/privatestack/hardware-profile.yml",
    "gpu_handoff_state": "/run/gpu-handoff/trust",
    "brick_stamp_dir": "/etc/privatestack/bricks",
    "sysfs_pci": "/sys/bus/pci/devices",
    "proc_meminfo": "/proc/meminfo",
    "virsh_bin": "/usr/bin/virsh",
    "libvirt_uri": "qemu:///system",
    "journalctl_bin": "/usr/bin/journalctl",
    "pkill_bin": "/usr/bin/pkill",
    "journal_units": ["virtqemud", "libvirtd", "virtnetworkd"],
    "provider_paths": [],
}


def _find_repo_root(start):
    current = Path(start).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "group_vars" / "all").is_dir() and (candidate / "roles").is_dir():
            return candidate
    return None


CONFIG_FILES = ("/etc/hyperlabctl/config.yml",
                "~/.config/hyperlabctl/config.yml")

PROVIDER_DIRS = ("~/.config/hyperlabctl/providers",)


def _file_settings():
    """Least surprising precedence: package defaults, then system, then user.

    A host that needs a different journal unit or a store on another disk says
    so in one file instead of carrying a patched copy of the CLI.
    """
    merged = {}
    for candidate in CONFIG_FILES:
        path = Path(candidate).expanduser()
        if not path.exists():
            continue
        try:
            loaded = load_yaml(path)
        except HyperlabError:
            continue
        if isinstance(loaded, dict):
            merged.update({key: value for key, value in loaded.items() if key in DEFAULTS})
    return merged


class Config:
    """Resolved locations plus lazily loaded group_vars."""

    def __init__(self, repo_root=None, overrides=None, read_files=True):
        self.repo_root = Path(repo_root) if repo_root else _find_repo_root(__file__)
        settings = dict(DEFAULTS)
        if read_files:
            settings.update(_file_settings())
        settings.update(overrides or {})
        for key, value in settings.items():
            setattr(self, key, value)
        self._group_vars = None

    def path(self, name):
        return Path(getattr(self, name))

    @property
    def group_vars(self):
        if self._group_vars is None:
            self._group_vars = self._load_group_vars()
        return self._group_vars

    def _load_group_vars(self):
        if self.repo_root is None:
            raise Unavailable("no repository checkout found: run from the repo or pass --repo")
        directory = self.repo_root / "group_vars" / "all"
        if not directory.is_dir():
            raise Unavailable("group_vars/all is missing under %s" % self.repo_root)
        merged = {}
        for item in sorted(directory.glob("*.yml")):
            loaded = load_yaml(item)
            if isinstance(loaded, dict):
                merged.update(loaded)
        if not merged:
            raise ContractError("group_vars/all parsed to nothing")
        return merged

    def var(self, name, default=Unavailable):
        try:
            variables = self.group_vars
        except Unavailable:
            if default is Unavailable:
                raise
            return default
        if name not in variables:
            if default is Unavailable:
                raise ContractError("group_vars does not declare %s" % name)
            return default
        return variables[name]

    def hostname(self):
        return self.var("host_hostname", None) or socket.gethostname()


def load_yaml(path):
    """PyYAML is the one dependency ADR 0004 allows. Its absence degrades."""
    path = Path(path)
    if not path.exists():
        raise Unavailable("%s does not exist" % path)
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - hosts without PyYAML
        raise Unavailable("PyYAML is not importable; install python-yaml") from exc
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except OSError as exc:
        raise Unavailable("%s is unreadable: %s" % (path, exc)) from exc
    except Exception as exc:
        raise ContractError("%s is not valid YAML: %s" % (path, exc)) from exc


class Context:
    """Everything a provider is given. Providers never reach past this."""

    def __init__(self, config, runner, environ=None):
        self.config = config
        self.runner = runner
        self.environ = environ if environ is not None else os.environ
        self.cache = {}

    def virsh_uncached(self, *args, timeout=None):
        """For blocking calls: never answer from cache; caller owns the timeout."""
        argv = [self.config.virsh_bin, "-c", self.config.libvirt_uri, "-q", *args]
        return self.runner.run(argv, timeout=timeout)

    def virsh(self, *args):
        argv = [self.config.virsh_bin, "-c", self.config.libvirt_uri, "-q", *args]
        key = tuple(argv)
        if key not in self.cache:
            self.cache[key] = self.runner.run(argv)
        return self.cache[key]

    def read_text(self, path):
        try:
            return Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise Unavailable("%s does not exist" % path) from None
        except OSError as exc:
            raise Unavailable("%s is unreadable: %s" % (path, exc)) from exc

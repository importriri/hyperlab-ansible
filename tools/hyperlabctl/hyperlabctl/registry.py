"""The action registry: one table, three consumers.

The rofi palette, the sway keybinds and the panel all read this. Nothing else
may hold a second list of what the CLI can do, or the palette starts offering
commands that no longer exist.

``privileged`` and ``destructive`` are data. Targets are resolved centrally to
an argv list; shell surfaces receive only ``shlex.join`` output from that argv,
never a string assembled from a libvirt name.
"""

from pathlib import Path
from string import Formatter

from .errors import ContractError, Unavailable


ACTIONS = [
    {
        "id": "status.show",
        "label": "Show lab status",
        "command": ["hyperlabctl", "status"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "vm.list",
        "label": "List domains",
        "command": ["hyperlabctl", "vm", "list"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "vm.start",
        "label": "Start an unmanaged domain",
        "command": ["hyperlabctl", "vm", "start", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "vm.stop",
        "label": "Shut down an unmanaged domain",
        "command": ["hyperlabctl", "vm", "stop", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "vm.inspect",
        "label": "Inspect a domain",
        "command": ["hyperlabctl", "vm", "inspect", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "domain.manager",
        "label": "Open the domain manager",
        "command": ["hyperlabctl", "open", "manager"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "vm.console",
        "label": "Open the graphical console",
        "command": ["hyperlabctl", "open", "console", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "vm.ssh",
        "label": "Open an SSH terminal for a running managed guest",
        "command": ["hyperlabctl", "open", "ssh", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "vm.looking-glass",
        "label": "Open Looking Glass for one running VFIO guest",
        "command": ["hyperlabctl", "open", "looking-glass", "{domain}"],
        "privileged": False,
        "destructive": False,
        "target": "domain",
        "requires": None,
    },
    {
        "id": "panel.open",
        "label": "Open the cockpit panel",
        "command": ["hyperlabctl", "panel"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "doctor.run",
        "label": "Explain every problem",
        "command": ["hyperlabctl", "doctor"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "logs.show",
        "label": "Show the libvirt journal",
        "command": ["hyperlabctl", "logs"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "net.list",
        "label": "List the security domains",
        "command": ["hyperlabctl", "net", "list"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "image.list",
        "label": "List the image manifests",
        "command": ["hyperlabctl", "image", "list"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "trust.show",
        "label": "Explain the trust ladder",
        "command": ["hyperlabctl", "trust"],
        "privileged": False,
        "destructive": False,
        "target": None,
        "requires": None,
    },
    {
        "id": "vm.create",
        "label": "Create a domain from its spec",
        "command": ["ansible-playbook", "playbooks/vm-create.yml", "-K",
                    "-e", "guest_spec={spec}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-create.yml",
    },
    {
        "id": "vm.destroy",
        "label": "Destroy a domain",
        "command": ["ansible-playbook", "playbooks/vm-destroy.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_destroy={domain}"],
        "privileged": True,
        "destructive": True,
        "target": "spec",
        "requires": "playbooks/vm-destroy.yml",
    },
    {
        "id": "vm.validate",
        "label": "Validate a managed domain",
        "command": ["ansible-playbook", "playbooks/vm-validate.yml", "-K",
                    "-e", "guest_spec={spec}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-validate.yml",
    },
    {
        "id": "vm.managed-start",
        "label": "Start a managed domain",
        "command": ["ansible-playbook", "playbooks/vm-start.yml", "-K",
                    "-e", "guest_spec={spec}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-start.yml",
    },
    {
        "id": "vm.managed-shutdown",
        "label": "Shut down a managed domain",
        "command": ["ansible-playbook", "playbooks/vm-shutdown.yml", "-K",
                    "-e", "guest_spec={spec}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-shutdown.yml",
    },
    {
        "id": "vm.managed-reboot",
        "label": "Reboot a managed domain without replacing QEMU",
        "command": ["ansible-playbook", "playbooks/vm-reboot.yml", "-K",
                    "-e", "guest_spec={spec}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-reboot.yml",
    },
    {
        "id": "vm.resize",
        "label": "Expand a managed domain disk",
        "command": ["ansible-playbook", "playbooks/vm-resize-disk.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_resize={domain}"],
        "privileged": True,
        "destructive": True,
        "target": "spec",
        "requires": "playbooks/vm-resize-disk.yml",
    },
    {
        "id": "vm.reconfigure",
        "label": "Reconfigure a managed domain offline",
        "command": ["ansible-playbook", "playbooks/vm-reconfigure.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_reconfigure={domain}"],
        "privileged": True,
        "destructive": False,
        "target": "spec",
        "requires": "playbooks/vm-reconfigure.yml",
    },
    {
        "id": "vm.inventory",
        "label": "Publish managed guest inventory",
        "command": ["hyperlabctl", "vm", "inventory", "{spec}"],
        "privileged": False,
        "destructive": False,
        "target": "spec",
        "requires": None,
    },
    {
        "id": "vm.force-stop",
        "label": "Force-stop a managed domain",
        "command": ["ansible-playbook", "playbooks/vm-stop.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_stop={domain}"],
        "privileged": True,
        "destructive": True,
        "target": "spec",
        "requires": "playbooks/vm-stop.yml",
    },
    {
        "id": "vm.power-cycle",
        "label": "Power-cycle a managed domain through a full QEMU stop",
        "command": ["ansible-playbook", "playbooks/vm-power-cycle.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_power_cycle={domain}"],
        "privileged": True,
        "destructive": True,
        "target": "spec",
        "requires": "playbooks/vm-power-cycle.yml",
    },
    {
        "id": "vm.reset",
        "label": "Reset a disposable domain",
        "command": ["ansible-playbook", "playbooks/vm-reset.yml", "-K",
                    "-e", "guest_spec={spec}",
                    "-e", "guest_confirm_reset={domain}"],
        "privileged": True,
        "destructive": True,
        "target": "spec",
        "requires": "playbooks/vm-reset.yml",
    },
    {
        "id": "image.import",
        "label": "Prepare or validate an image from its manifest",
        "command": ["ansible-playbook", "playbooks/image-prepare.yml", "-K",
                    "-e", "image_factory_manifest={manifest}"],
        "privileged": True,
        "destructive": False,
        "target": "manifest",
        "requires": "playbooks/image-prepare.yml",
    },
    {
        "id": "image.validate",
        "label": "Validate a sealed image",
        "command": ["ansible-playbook", "playbooks/image-validate.yml", "-K",
                    "-e", "image_factory_manifest={manifest}"],
        "privileged": True,
        "destructive": False,
        "target": "manifest",
        "requires": "playbooks/image-validate.yml",
    },
    {
        "id": "store.layout",
        "label": "Lay out and verify the image store",
        "command": ["ansible-playbook", "playbooks/image-store.yml", "-K"],
        "privileged": True,
        "destructive": False,
        "target": None,
        "requires": "playbooks/image-store.yml",
    },
]

_IDS = [action["id"] for action in ACTIONS]
if len(_IDS) != len(set(_IDS)):
    raise RuntimeError("duplicate action id in the registry")


def available(action, repo_root):
    """An action with no prerequisite is always available."""
    if not action.get("requires"):
        return True
    if repo_root is None:
        return False
    return (Path(repo_root) / action["requires"]).is_file()


def actions(include_privileged=True, repo_root=None, include_unavailable=False):
    listed = []
    for action in ACTIONS:
        if not include_privileged and action["privileged"]:
            continue
        entry = dict(action)
        entry["available"] = available(action, repo_root)
        if entry["available"] or include_unavailable:
            listed.append(entry)
    return listed


def by_id(action_id):
    for action in ACTIONS:
        if action["id"] == action_id:
            return dict(action)
    return None


def target_choices(kind, repo_root):
    """Return checked-in targets plus host-local generated VM specs."""
    layout = {"spec": ("vm-specs", "*.yml"), "manifest": ("images", "*.yml")}
    if kind not in layout:
        raise ContractError("unsupported action target %r" % kind)
    if repo_root is None:
        raise Unavailable("no repository checkout found")
    root = Path(repo_root).resolve()
    subdir, pattern = layout[kind]
    declared = root / subdir
    if declared.is_symlink():
        raise ContractError("%s must not be a symlink" % declared)
    directory = declared.resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise ContractError("%s escaped the repository" % declared) from exc
    if not directory.is_dir():
        raise Unavailable("%s is missing under %s" % (subdir, root))
    candidates = list(directory.glob(pattern))
    if kind == "spec":
        generated = directory / ".generated"
        if generated.exists():
            if generated.is_symlink() or not generated.is_dir():
                raise ContractError("vm-specs/.generated must be a real directory")
            candidates.extend(generated.glob(pattern))

    choices = []
    for item in sorted(candidates):
        if item.is_symlink() or not item.is_file():
            continue
        resolved = item.resolve()
        try:
            resolved.relative_to(directory)
        except ValueError:
            continue
        choices.append(resolved.relative_to(root).as_posix())
    return choices


def _safe_scalar(value, label):
    if not isinstance(value, str) or not value:
        raise ContractError("%s is required" % label)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ContractError("%s contains control characters" % label)
    return value


def _repo_target(value, kind, repo_root):
    value = _safe_scalar(value, kind)
    choices = target_choices(kind, repo_root)
    if value not in choices:
        raise ContractError("%s is not a checked-in or generated %s target" % (value, kind))
    return value


def resolve(action_id, repo_root=None, domain=None, spec=None, manifest=None):
    """Resolve one action to an argv list, rejecting missing or unsafe targets."""
    action = by_id(action_id)
    if action is None:
        raise ContractError("unknown action %s" % action_id)
    if not available(action, repo_root):
        raise Unavailable("%s requires %s" % (action_id, action["requires"]))

    values = {}
    fields = {field for token in action["command"]
              for _, field, _, _ in Formatter().parse(token) if field}
    if "spec" in fields:
        values["spec"] = _repo_target(spec, "spec", repo_root)
    if "manifest" in fields:
        values["manifest"] = _repo_target(manifest, "manifest", repo_root)
    if "domain" in fields:
        if domain is None and spec is not None:
            domain = Path(values["spec"]).stem
        values["domain"] = _safe_scalar(domain, "domain")

    try:
        return [token.format_map(values) for token in action["command"]]
    except KeyError as exc:
        raise ContractError("action %s has an unresolved target %s" % (action_id, exc)) from exc

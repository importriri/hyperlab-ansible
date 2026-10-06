"""The palette may only ever offer what the CLI declares."""

import world
from harness import check, equals
from hyperlabctl import registry
from hyperlabctl.commands import REGISTRY as COMMANDS


ALL = {"include_unavailable": True}


def test_action_ids_are_unique():
    ids = [action["id"] for action in registry.actions(**ALL)]
    equals("unique_action_ids", len(ids), len(set(ids)))


def test_every_action_declares_the_privilege_fields():
    for action in registry.actions(**ALL):
        for field in ("id", "label", "command", "privileged", "destructive",
                      "target", "requires"):
            check("action_%s_has_%s" % (action["id"], field), field in action)
        check("action_%s_privileged_is_bool" % action["id"],
              isinstance(action["privileged"], bool))


def test_unprivileged_filter_removes_every_privileged_action():
    listed = registry.actions(include_privileged=False, **ALL)
    check("no_privileged_leaks", all(not action["privileged"] for action in listed))
    check("filter_actually_removed_some", len(listed) < len(registry.actions(**ALL)))


def test_every_destructive_action_is_also_privileged():
    for action in registry.actions(**ALL):
        if action["destructive"]:
            check("destructive_%s_is_privileged" % action["id"], action["privileged"])


def test_unprivileged_actions_only_invoke_the_cli_itself():
    for action in registry.actions(include_privileged=False, **ALL):
        equals("unprivileged_%s_entrypoint" % action["id"], action["command"][0], "hyperlabctl")


def test_every_unprivileged_action_names_a_real_subcommand():
    for action in registry.actions(include_privileged=False, **ALL):
        check("action_%s_subcommand_exists" % action["id"], action["command"][1] in COMMANDS)


def test_lookup_by_id_returns_a_copy():
    first = registry.by_id("vm.start")
    first["label"] = "mutated"
    equals("registry_not_mutated", registry.by_id("vm.start")["label"], "Start an unmanaged domain")


def test_an_action_with_no_prerequisite_is_always_available():
    for action in registry.actions(include_privileged=False, **ALL):
        equals("unprivileged_%s_available" % action["id"], action["available"], True)


def test_an_action_whose_playbook_is_absent_is_not_offered():
    ctx = world.build(trust=None)
    offered = {action["id"] for action in registry.actions(repo_root=ctx.config.repo_root)}
    check("vm_create_hidden_until_m3", "vm.create" not in offered)
    check("vm_destroy_hidden_until_m3", "vm.destroy" not in offered)


def test_an_action_whose_playbook_exists_is_offered():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks" / "vm-create.yml").write_text("---\n")
    offered = {action["id"] for action in registry.actions(repo_root=ctx.config.repo_root)}
    check("vm_create_appears_when_the_playbook_lands", "vm.create" in offered)


def test_show_all_still_reveals_the_unavailable_ones():
    ctx = world.build(trust=None)
    listed = registry.actions(repo_root=ctx.config.repo_root, include_unavailable=True)
    unavailable = [action for action in listed if not action["available"]]
    check("unavailable_are_visible_on_request", len(unavailable) > 0)
    for action in unavailable:
        check("unavailable_%s_says_why" % action["id"], bool(action["requires"]))


def test_no_available_action_may_reference_a_missing_playbook():
    """The invariant that matters: whatever the palette offers must be runnable."""
    ctx = world.build(trust=None)
    for action in registry.actions(repo_root=ctx.config.repo_root):
        for part in action["command"]:
            if part.startswith("playbooks/"):
                check("available_%s_playbook_exists" % action["id"],
                      (ctx.config.repo_root / part).exists(),
                      "%s references %s" % (action["id"], part))


def test_resolved_domain_command_round_trips_without_shell_injection():
    import shlex
    name = "demo; printf injected"
    command = shlex.join(registry.resolve("vm.start", domain=name))
    equals("resolved_domain_round_trip", shlex.split(command),
           ["hyperlabctl", "vm", "start", name])


def test_managed_destroy_uses_its_real_playbook_and_derives_confirmation():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks/vm-destroy.yml").write_text("---\n")
    (ctx.config.repo_root / "vm-specs").mkdir()
    (ctx.config.repo_root / "vm-specs/demo.yml").write_text("---\n")
    argv = registry.resolve("vm.destroy", repo_root=ctx.config.repo_root,
                            spec="vm-specs/demo.yml")
    equals("destroy_playbook", argv[1], "playbooks/vm-destroy.yml")
    check("destroy_confirmation_derived", "guest_confirm_destroy=demo" in argv)


def test_managed_resize_and_reconfigure_derive_exact_confirmations():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks/vm-resize-disk.yml").write_text("---\n")
    (ctx.config.repo_root / "playbooks/vm-reconfigure.yml").write_text("---\n")
    (ctx.config.repo_root / "vm-specs").mkdir()
    (ctx.config.repo_root / "vm-specs/demo.yml").write_text("---\n")

    resized = registry.resolve(
        "vm.resize", repo_root=ctx.config.repo_root, spec="vm-specs/demo.yml"
    )
    equals("resize_playbook", resized[1], "playbooks/vm-resize-disk.yml")
    check("resize_confirmation_derived", "guest_confirm_resize=demo" in resized)

    reconfigured = registry.resolve(
        "vm.reconfigure", repo_root=ctx.config.repo_root, spec="vm-specs/demo.yml"
    )
    equals("reconfigure_playbook", reconfigured[1], "playbooks/vm-reconfigure.yml")
    check(
        "reconfigure_confirmation_derived",
        "guest_confirm_reconfigure=demo" in reconfigured,
    )


def test_managed_inventory_routes_through_the_unprivileged_cli():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "vm-specs").mkdir()
    (ctx.config.repo_root / "vm-specs/demo.yml").write_text("---\n")

    inventory = registry.resolve(
        "vm.inventory",
        repo_root=ctx.config.repo_root,
        spec="vm-specs/demo.yml",
    )
    equals(
        "inventory_cli_route",
        inventory,
        [
            "hyperlabctl",
            "vm",
            "inventory",
            "vm-specs/demo.yml",
        ],
    )


def test_image_import_resolves_to_the_supported_prepare_transaction():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks/image-prepare.yml").write_text("---\n")
    (ctx.config.repo_root / "images").mkdir(exist_ok=True)
    (ctx.config.repo_root / "images/arch.yml").write_text("---\n")
    argv = registry.resolve("image.import", repo_root=ctx.config.repo_root,
                            manifest="images/arch.yml")
    equals("image_import_playbook", argv[1], "playbooks/image-prepare.yml")
    check("image_import_uses_prepare_contract", "image_factory_operation=import" not in argv)
    check("image_import_selects_manifest", "image_factory_manifest=images/arch.yml" in argv)


def test_target_choices_refuse_a_redirected_spec_directory():
    import tempfile
    from pathlib import Path
    from hyperlabctl.errors import ContractError
    ctx = world.build(trust=None)
    outside = Path(tempfile.mkdtemp(prefix="hyperlab-spec-outside-"))
    (ctx.config.repo_root / "vm-specs").symlink_to(outside, target_is_directory=True)
    try:
        registry.target_choices("spec", ctx.config.repo_root)
    except ContractError:
        check("redirected_spec_dir_refused", True)
    else:
        check("redirected_spec_dir_refused", False)


def test_managed_reboot_and_power_cycle_use_reviewed_playbooks():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks/vm-reboot.yml").write_text("---\n")
    (ctx.config.repo_root / "playbooks/vm-power-cycle.yml").write_text("---\n")
    (ctx.config.repo_root / "vm-specs").mkdir()
    (ctx.config.repo_root / "vm-specs/demo.yml").write_text("---\n")

    rebooted = registry.resolve(
        "vm.managed-reboot",
        repo_root=ctx.config.repo_root,
        spec="vm-specs/demo.yml",
    )
    equals("reboot_playbook", rebooted[1], "playbooks/vm-reboot.yml")
    check(
        "reboot_has_no_force_confirmation",
        not any("guest_confirm_" in part for part in rebooted),
    )

    cycled = registry.resolve(
        "vm.power-cycle",
        repo_root=ctx.config.repo_root,
        spec="vm-specs/demo.yml",
    )
    equals("power_cycle_playbook", cycled[1], "playbooks/vm-power-cycle.yml")
    check(
        "power_cycle_confirmation_derived",
        "guest_confirm_power_cycle=demo" in cycled,
    )


def test_guest_fullscreen_is_a_typed_unprivileged_vm_action():
    action = registry.by_id("vm.guest-fullscreen")
    equals(
        "guest_fullscreen_command",
        action["command"],
        ["hyperlabctl", "vm", "guest-fullscreen", "{domain}"],
    )
    equals("guest_fullscreen_privileged", action["privileged"], False)
    equals("guest_fullscreen_destructive", action["destructive"], False)
    equals("guest_fullscreen_target", action["target"], "domain")
    equals(
        "guest_fullscreen_resolve",
        registry.resolve("vm.guest-fullscreen", domain="demo"),
        ["hyperlabctl", "vm", "guest-fullscreen", "demo"],
    )


def _usb_repo():
    ctx = world.build(trust=None)
    (ctx.config.repo_root / "playbooks").mkdir(exist_ok=True)
    (ctx.config.repo_root / "playbooks/host-usb-allow.yml").write_text("---\n")
    return ctx


def test_usb_allow_is_a_privileged_reviewed_playbook():
    action = registry.by_id("usb.allow")
    equals("usb_allow_privileged", action["privileged"], True)
    equals("usb_allow_destructive", action["destructive"], False)
    equals("usb_allow_target", action["target"], "usb")
    equals("usb_allow_requires", action["requires"], "playbooks/host-usb-allow.yml")


def test_usb_allow_resolves_port_scope_and_device():
    repo = _usb_repo().config.repo_root
    for scope in ("once", "permanent"):
        equals("usb_allow_resolves_%s" % scope,
               registry.resolve("usb.allow", repo_root=repo, usb_port="1-3.4", usb_scope=scope,
                                usb_device="0781:5581"),
               ["ansible-playbook", "playbooks/host-usb-allow.yml", "-K",
                "-e", "host_usb_allow_port=1-3.4", "-e", "host_usb_allow_scope=%s" % scope,
                "-e", "host_usb_allow_device=0781:5581"])


def _refused(name, **target):
    from hyperlabctl.errors import ContractError
    repo = _usb_repo().config.repo_root
    try:
        registry.resolve("usb.allow", repo_root=repo, **target)
    except ContractError:
        check(name, True)
    else:
        check(name, False)


def test_usb_allow_refuses_a_malformed_port_or_scope():
    cases = [("usb1", "once"), ("1-2 x", "once"), ("1-2\n", "once"), ("-1-2", "once"),
             ("1-2.", "once"), ("1", "once"), ("1-\u0662", "once"), ("1-2", "always"),
             ("1-2", ""), (None, "once"), ("1-2", None),
             ("1-2 host_usb_allow_scope=permanent", "once")]
    for port, scope in cases:
        _refused("usb_allow_refuses_%r_%r" % (port, scope),
                 usb_port=port, usb_scope=scope, usb_device="0781:5581")


def test_usb_allow_refuses_a_missing_or_malformed_device():
    # Without the device the allow is bound to a port only: whatever is
    # plugged in there by the time the playbook runs would be allowed.
    for device in (None, "", "0781", "0781:558", "0781:55811", "0781-5581", "0781:5581 ",
                   "0781:558G", "0781:5581\n", "0781:5581:1", "07815581",
                   "0781:5581 host_usb_allow_scope=permanent"):
        _refused("usb_allow_refuses_device_%r" % device,
                 usb_port="1-2", usb_scope="once", usb_device=device)
    # Uppercase is refused, not folded: sysfs and USBGuard print lowercase,
    # and the id must match what they print exactly.
    _refused("usb_allow_refuses_uppercase_device", usb_port="1-2", usb_scope="once",
             usb_device="0781:558A")


def test_usb_allow_is_unavailable_without_its_playbook():
    from hyperlabctl.errors import Unavailable
    ctx = world.build(trust=None)
    try:
        registry.resolve("usb.allow", repo_root=ctx.config.repo_root,
                         usb_port="1-2", usb_scope="once", usb_device="0781:5581")
    except Unavailable:
        check("usb_allow_needs_playbook", True)
    else:
        check("usb_allow_needs_playbook", False)


def test_actions_resolve_accepts_usb_flags():
    import io
    import json
    from contextlib import redirect_stdout
    from hyperlabctl.cli import main
    ctx = _usb_repo()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["--json", "actions", "--resolve", "usb.allow", "--usb-port", "1-2",
                     "--usb-scope", "permanent", "--usb-device", "0781:5581"], ctx=ctx)
    equals("usb_cli_exit", code, 0)
    equals("usb_cli_argv", json.loads(buffer.getvalue())[-6:],
           ["-e", "host_usb_allow_port=1-2", "-e", "host_usb_allow_scope=permanent",
            "-e", "host_usb_allow_device=0781:5581"])

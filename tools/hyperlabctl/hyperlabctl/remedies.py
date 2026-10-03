"""Every problem the providers can raise, and the command that clears it.

A panel that reports a problem without saying what fixes it makes the reader do
the lookup. This is the lookup.
"""

REMEDIES = {
    "host.profile_unknown": "ansible-playbook playbooks/preflight.yml -K",
    "trust.level_unmapped": "check gpu_trust_levels in group_vars/all/networks.yml "
                            "against /run/gpu-handoff/trust",
    "memory.overcommitted": "shut a domain down, or lower its allocation in its vm-spec",
    "gpu.id_absent": "ansible-playbook playbooks/preflight.yml -K "
                     "(the profile does not match this machine)",
    "gpu.not_bound": "reboot into the Vfio boot entry",
    "networks.missing": "ansible-playbook playbooks/network-domains.yml -K",
    "networks.inactive": "virsh -c qemu:///system net-start <name>",
    "domains.unguarded_vfio": "add the fixture domain to gpu_domain_profiles in "
                              "group_vars/all/networks.yml, then re-run foundation.yml",
    "domains.gpu_policy_unverified": "re-apply the managed Machine through the reviewed "
                                     "guest lifecycle so its root-owned GPU handoff "
                                     "policy matches gpu_handoff_profile",
    "domains.gpu_policy_unexpected": "remove the stale managed GPU handoff policy through "
                                     "the reviewed Machine lifecycle before treating this "
                                     "standard Machine as reconciled",
    "domains.network_identity_mismatch": "re-apply the guest from its vm-spec so its "
                                         "interfaces match its network_profile",
    "store.low_space": "prune {root}/cache and {root}/exports, or grow the volume",
    "images.sealed_without_checksum": "re-run playbooks/image-prepare.yml with "
                                      "image_factory_operation=seal",
    "images.no_source": "record source_url and source_sha256 in the manifest",
    "hyperlab.unavailable": "the source this section reads is absent on this host",
    "hyperlab.contract": "the repository declares something this host cannot honour",
    "provider.crashed": "a provider raised: this is a bug in hyperlabctl, not in the host",
}


def remedy(problem, document=None):
    text = REMEDIES.get(problem.get("id"))
    if text is None:
        return None
    root = ((document or {}).get("store") or {}).get("root", "<store>")
    return text.replace("{root}", root)

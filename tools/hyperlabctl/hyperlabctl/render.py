"""Renderers. Each one reads the document and writes nothing back."""

import json

COLORS = {"ok": "\033[32m", "warn": "\033[33m", "error": "\033[31m",
          "dim": "\033[90m", "off": "\033[0m"}


def paint(text, tone, enabled):
    if not enabled or tone not in COLORS:
        return text
    return "%s%s%s" % (COLORS[tone], text, COLORS["off"])


def as_json(document, pretty=True):
    return json.dumps(document, indent=2 if pretty else None, sort_keys=False)


def _line(label, value, tone, color):
    return "  %-22s %s" % (label, paint(str(value), tone, color))


def as_text(document, color=True):
    out = []
    host = document.get("host") or {}
    out.append("hyperlab  %s  %s" % (host.get("hostname") or "?",
                                     host.get("profile") or "profile unknown"))

    trust = document.get("trust")
    if trust:
        if trust["claimed"]:
            value = "%s (%s), reboot to rise" % (trust["name"] or "?", trust["level"])
            tone = "warn"
        else:
            value = "unclaimed, any level available"
            tone = "ok"
        out.append(_line("trust", value, tone, color))

    memory = document.get("memory")
    if memory:
        out.append(_line("assignable ram",
                         "%d MB of %d" % (memory["assignable_mb"], memory["total_mb"]),
                         "error" if memory["negative"] else "ok", color))

    gpu = document.get("gpu")
    if gpu:
        owner = gpu["held_by"] or ("free" if gpu["bound"] else "not bound")
        out.append(_line("gpu", "%s  %s" % (", ".join(gpu["ids"]), owner),
                         "ok" if gpu["bound"] else "warn", color))

    networks = document.get("networks")
    if networks:
        out.append(_line("networks", "%d/%d active" % (networks["active"], networks["expected"]),
                         "ok" if networks["active"] == networks["expected"] else "warn", color))

    store = document.get("store")
    if store:
        out.append(_line("store", "%s GiB free" % store["free_gib"], "ok", color))

    domains = document.get("domains")
    if domains:
        out.append("")
        out.append("  %-26s %-10s %8s  %-10s %s" % ("domain", "state", "ram", "network", "note"))
        for domain in domains:
            note = ""
            if domain["blocked"]:
                note = "short %d MB" % domain["blocked"]["short_mb"]
            elif domain["vfio"]:
                note = "vfio"
            tone = "ok" if domain["state"] == "running" else "dim"
            out.append("  %-26s %-10s %8s  %-10s %s" % (
                domain["name"],
                paint(domain["state"], tone, color),
                "%s MB" % domain["memory_mb"] if domain["memory_mb"] else "-",
                domain["network"] or "-",
                paint(note, "warn", color) if note else "",
            ))

    problems = document.get("problems") or []
    if problems:
        out.append("")
        for problem in problems:
            out.append("  %s %s" % (paint(problem["severity"].upper(), problem["severity"], color),
                                    problem["message"]))
    return "\n".join(out)


def as_waybar(document):
    """The shape waybar's custom module expects: text, alt, tooltip, class."""
    trust = document.get("trust") or {}
    memory = document.get("memory") or {}
    gpu = document.get("gpu") or {}
    networks = document.get("networks") or {}
    domains = document.get("domains") or []
    problems = document.get("problems") or []

    severity = "ok"
    for problem in problems:
        if problem["severity"] == "error":
            severity = "error"
            break
        severity = "warn"

    # An unreadable trust section is unknown, never "unclaimed".
    trust_known = trust_claim(document)["known"]
    if not trust_known:
        text = "?"
        trust_line = "unknown (trust state could not be read)"
    elif trust.get("claimed"):
        text = "%s %s" % (trust.get("name") or "?", trust.get("level"))
        trust_line = "%s (%s), reboot to rise" % (trust.get("name"), trust.get("level"))
    else:
        text = "unclaimed"
        trust_line = "unclaimed"

    running = [domain for domain in domains if domain["state"] == "running"]
    tooltip = [
        "trust: %s" % trust_line,
        "assignable: %s MB" % memory.get("assignable_mb", "?"),
        "gpu: %s" % (gpu.get("held_by") or ("free" if gpu.get("bound") else "not bound")),
        "networks: %s/%s" % (networks.get("active", "?"), networks.get("expected", "?")),
        "running: %s" % (", ".join(domain["name"] for domain in running) or "none"),
    ]
    for problem in problems:
        tooltip.append("%s %s" % (problem["severity"], problem["message"]))

    return {
        "text": text,
        "alt": severity,
        "tooltip": "\n".join(tooltip),
        "class": severity,
    }


def waybar_field(document, field):
    """One pill of the drawer. Same four keys, so the CSS rules are shared."""
    trust = document.get("trust") or {}
    memory = document.get("memory") or {}
    gpu = document.get("gpu") or {}
    domains = document.get("domains") or []
    running = [domain for domain in domains if domain["state"] == "running"]

    if field == "trust":
        claimed = trust.get("claimed")
        text = "%s %s" % (trust.get("name") or "?", trust.get("level")) if claimed else "unclaimed"
        state = "warn" if claimed else "ok"
        tooltip = ("GPU held at trust %s; only a reboot raises it"
                   % trust.get("level")) if claimed else "GPU unclaimed this boot"
        if not trust_claim(document)["known"]:
            # An unreadable or inconsistent claim is never shown as "unclaimed".
            text, state = "?", "error"
            tooltip = "GPU trust claim could not be read; run hyperlabctl doctor"
    elif field == "ram":
        assignable = memory.get("assignable_mb")
        text = "%s MB" % assignable if assignable is not None else "?"
        state = "error" if memory.get("negative") else "ok"
        tooltip = ("%s MB total, %s reserved, %s committed, %s overhead"
                   % (memory.get("total_mb"), memory.get("host_reserved_mb"),
                      memory.get("committed_mb"), memory.get("overhead_mb")))
    elif field == "gpu":
        if gpu.get("held_by"):
            text, state = gpu["held_by"], "warn"
        elif gpu.get("bound"):
            text, state = "free", "ok"
        else:
            text, state = "not bound", "warn"
        tooltip = "\n".join("%s  %s" % (address, info["driver"] or "no driver")
                             for address, info in sorted((gpu.get("devices") or {}).items())) \
            or "no PCI device matched the profile"
    elif field == "vms":
        text = "%d/%d" % (len(running), len(domains))
        blocked = [domain for domain in domains if domain.get("blocked")]
        state = "warn" if blocked else "ok"
        tooltip = "\n".join("%s  %s" % (domain["name"], domain["state"])
                            for domain in domains) or "no domains defined"
        if blocked:
            tooltip += "\nblocked: " + ", ".join(domain["name"] for domain in blocked)
    else:
        raise ValueError("unknown waybar field %r" % field)

    if document.get(field if field != "ram" else "memory") is None and field != "vms":
        state = "error"
        tooltip = "this section could not be read; run hyperlabctl doctor"

    payload = {"text": text, "alt": state, "tooltip": tooltip, "class": state}
    if field == "trust":
        # Additive read-only projection for the shell: the explicit host claim
        # as structured fields, so the shell never parses the display text.
        payload.update(trust_claim(document))
    if field == "gpu":
        # Additive read-only projection: the current owner is the running
        # domain that holds the device, never inferred from availability text.
        payload.update(gpu_ownership(document))
    if field == "vms":
        # Additive read-only projection for the desktop. Never infer trust from
        # a VM name, network attachment, running state or appearance.
        available = isinstance(document.get("domains"), list)
        payload["machines_available"] = available
        payload["machines"] = machine_cards(document) if available else []
        if not available:
            payload.update(text="?", alt="error", **{
                "class": "error", "tooltip": "Machine inventory unavailable",
            })
    return payload


# The reviewed GPU handoff ladder. SERVICES sits outside the GPU handoff and can
# never hold a boot claim; HOST is the control plane, never a rung.
GPU_LADDER = {"clean": 3, "dev": 2, "dirty": 1, "lab": 0}


def trust_claim(document):
    """The host's explicit GPU trust claim for this boot; nothing inferred.

    `known` is true only for an affirmative, internally consistent reading:
    the trust section was read, and it either reports no claim, or a claim by
    a ladder identity at that identity's canonical rung. An unreadable
    section, an unmapped level or an off-ladder identity is `known: false`,
    so a consumer can never present "could not read the restriction" as
    "there is no restriction".
    """
    trust = document.get("trust")
    if not isinstance(trust, dict) or not isinstance(trust.get("claimed"), bool):
        return {"known": False, "claimed": False, "identity": None, "level": None}
    if not trust["claimed"]:
        return {"known": True, "claimed": False, "identity": None, "level": None}
    name = trust.get("name")
    level = trust.get("level")
    rung = GPU_LADDER.get(name) if isinstance(name, str) else None
    if rung is None or isinstance(level, bool) or level != rung:
        return {"known": False, "claimed": False, "identity": None, "level": None}
    return {"known": True, "claimed": True, "identity": name, "level": rung}


def gpu_ownership(document):
    """Structured GPU facts: owner, VFIO binding, and whether either is known."""
    gpu = document.get("gpu")
    if not isinstance(gpu, dict):
        return {"owner": None, "bound": None, "known": False}
    owner = gpu.get("held_by")
    return {
        "owner": owner if isinstance(owner, str) and owner else None,
        "bound": bool(gpu.get("bound")),
        "known": True,
    }


def _known_bool(value):
    return value if isinstance(value, bool) else None


def machine_cards(document):
    """The authoritative presentation facts for one machine.

    Everything here is read from a provider, never inferred from a name, a
    network attachment or an appearance. Two distinctions matter and are
    preserved deliberately:

      * `networks` is null when the domain could not be read and [] when the
        domain really declares no interface, so the shell never reports
        "None" for something it does not know;
      * `gpu_relation` is structured, so presentation can change the words
        without changing behaviour.

    Operation availability is deliberately NOT published here. It depends on
    the live spec registry and the runtime SSH inventory, which this document
    does not read, so the shell asks the reviewed machine bridge for it.
    """
    identities = {"clean", "dev", "services", "dirty", "lab"}
    gpu = document.get("gpu") or {}
    result = []
    for domain in document.get("domains") or []:
        profile = domain.get("trust_profile")
        identity = profile if profile in identities else "unclassified"
        if gpu.get("held_by") == domain["name"]:
            relation = "held"
            assignment = "GPU held"
        elif domain.get("state") == "unknown":
            relation = "unknown"
            assignment = "GPU assignment unknown"
        elif domain.get("vfio"):
            relation = "configured"
            assignment = "Passthrough configured"
        else:
            relation = "none"
            assignment = "No passthrough configured"
        networks = domain.get("networks")
        result.append({
            "name": domain["name"],
            "state": domain["state"],
            "provenance": identity,
            "gpu": assignment,
            "gpu_relation": relation,
            "memory_mb": domain.get("memory_mb"),
            "vcpus": domain.get("vcpus"),
            "network": domain.get("network"),
            "networks": list(networks) if isinstance(networks, list) else None,
            # Tri-state: None when the domain could not be read.
            "managed": _known_bool(domain.get("managed")),
            "vfio": _known_bool(domain.get("vfio")),
            "lifecycle": domain.get("lifecycle"),
            "device_profile": domain.get("device_profile"),
            "blocked": domain.get("blocked"),
        })
    order = ("clean", "dev", "services", "dirty", "lab", "unclassified")
    return sorted(result, key=lambda row: (order.index(row["provenance"]), row["name"]))

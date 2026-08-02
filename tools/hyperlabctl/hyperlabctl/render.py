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

    if trust.get("claimed"):
        text = "%s %s" % (trust.get("name") or "?", trust.get("level"))
    else:
        text = "unclaimed"

    running = [domain for domain in domains if domain["state"] == "running"]
    tooltip = [
        "trust: %s" % ("%s (%s), reboot to rise" % (trust.get("name"), trust.get("level"))
                       if trust.get("claimed") else "unclaimed"),
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


FIELD_ICONS = {"trust": "\uf023", "ram": "\uf1c0", "gpu": "\uf2db", "vms": "\uf233"}


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

    return {"text": text, "alt": state, "tooltip": tooltip, "class": state}

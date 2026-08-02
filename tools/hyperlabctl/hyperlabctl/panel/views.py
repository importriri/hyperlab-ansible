"""One view of the document per class. Adding a tab means adding a class.

Same discovery rule as providers and commands: subclasses register themselves,
and the panel builds its tab bar from whatever is registered. A view declares
its columns and turns the document into rows; it never touches curses.
"""

REGISTRY = {}


class View:
    key = None
    title = None
    order = 100
    columns = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "key", None) is None:
            return
        if cls.key in REGISTRY and REGISTRY[cls.key] is not cls:
            raise RuntimeError("two views claim the key %r" % cls.key)
        REGISTRY[cls.key] = cls

    def rows(self, document, logs):
        raise NotImplementedError

    def actions(self, row):
        """Which of start/stop this row can take. Views without any say no."""
        return {"start": False, "stop": False}


def views():
    return [REGISTRY[key]() for key in sorted(REGISTRY, key=lambda k: (REGISTRY[k].order, k))]


class DomainView(View):
    key = "domains"
    title = "domains"
    order = 10
    columns = (("domain", 26, "name"), ("state", 10, "state"),
               ("ram", 9, "ram"), ("network", 11, "network"), ("note", 0, "note"))

    def rows(self, document, logs):
        listed = []
        for domain in document.get("domains") or []:
            running = domain["state"] == "running"
            if domain["blocked"]:
                note, colour = "short %d MB" % domain["blocked"]["short_mb"], "warn"
            elif domain["vfio"]:
                note = "vfio %s" % (domain["trust_profile"] or "UNGUARDED")
                colour = "error" if domain["trust_profile"] is None else "mauve"
            elif domain.get("managed"):
                note = "managed %s" % (domain.get("lifecycle") or "guest")
                colour = "blue"
            else:
                note, colour = "", "dim"
            listed.append({
                "key": domain["name"], "name": domain["name"], "state": domain["state"],
                "ram": "%s MB" % domain["memory_mb"] if domain["memory_mb"] else "-",
                "network": domain["network"] or "-", "note": note, "tone": colour,
                "running": running, "blocked": domain["blocked"],
                "managed": domain.get("managed", False),
                "detail": [
                    ("state", domain["state"]),
                    ("memory", "%s MB" % domain["memory_mb"]),
                    ("networks", ", ".join(domain["networks"]) or "-"),
                    ("vfio", "yes" if domain["vfio"] else "no"),
                    ("managed", "yes" if domain.get("managed") else "no"),
                    ("device profile", domain.get("device_profile") or "-"),
                    ("lifecycle", domain.get("lifecycle") or "-"),
                    ("trust profile", domain["trust_profile"] or "-"),
                    ("blocked", "short %d MB of %d assignable"
                     % (domain["blocked"]["short_mb"], domain["blocked"]["available_mb"])
                     if domain["blocked"] else "no"),
                ],
            })
        return listed

    def actions(self, row):
        direct = not row.get("managed", False)
        return {"start": direct and not row["running"] and row["blocked"] is None,
                "stop": direct and row["running"]}


class NetworkView(View):
    key = "networks"
    title = "networks"
    order = 20
    columns = (("network", 16, "name"), ("state", 12, "state"),
               ("trust", 8, "trust"), ("note", 0, "note"))

    def rows(self, document, logs):
        section = document.get("networks") or {}
        listed = []
        for name in section.get("declared") or []:
            if name in section.get("missing", []):
                state, colour = "missing", "error"
            elif name in section.get("inactive", []):
                state, colour = "inactive", "warn"
            else:
                state, colour = "active", "dim"
            listed.append({"key": name, "name": name, "state": state, "trust": "-",
                           "note": "", "tone": colour, "running": state == "active",
                           "blocked": None,
                           "detail": [("state", state)]})
        for name in section.get("undeclared") or []:
            listed.append({"key": name, "name": name, "state": "undeclared", "trust": "-",
                           "note": "not in the contract", "tone": "warn",
                           "running": True, "blocked": None,
                           "detail": [("state", "undeclared")]})
        return listed


class ImageView(View):
    key = "images"
    title = "images"
    order = 30
    columns = (("image", 24, "name"), ("status", 12, "state"),
               ("size", 8, "ram"), ("note", 0, "note"))

    def rows(self, document, logs):
        listed = []
        for image in document.get("images") or []:
            sealed = image["status"] == "sealed"
            note = "sha256" if image["sha256"] else "no checksum"
            if image["private"]:
                note += "  private"
            listed.append({
                "key": image["name"], "name": image["name"], "state": image["status"],
                "ram": "%s G" % image["virtual_size_gib"] if image["virtual_size_gib"] else "-",
                "network": "-", "note": note, "tone": "dim" if sealed else "warn",
                "running": sealed, "blocked": None,
                "detail": [("status", image["status"]),
                           ("checksum", "yes" if image["sha256"] else "no"),
                           ("source recorded", "yes" if image["source"] else "no")],
            })
        return listed


class ProblemView(View):
    key = "problems"
    title = "problems"
    order = 40
    columns = (("severity", 10, "state"), ("section", 12, "name"), ("what", 0, "note"))

    def rows(self, document, logs):
        from ..remedies import remedy
        listed = []
        for problem in document.get("problems") or []:
            listed.append({
                "key": problem["id"], "name": problem.get("provider", "-"),
                "state": problem["severity"], "ram": "-", "network": "-",
                "note": problem["message"], "tone": problem["severity"],
                "running": False, "blocked": None,
                "detail": [("id", problem["id"]),
                           ("severity", problem["severity"]),
                           ("fix", remedy(problem, document) or "-")],
            })
        return listed


class JournalView(View):
    key = "journal"
    title = "journal"
    order = 50
    columns = (("time", 10, "name"), ("level", 8, "state"), ("message", 0, "note"))

    def rows(self, document, logs):
        listed = []
        for entry in reversed(logs or []):
            listed.append({
                "key": "%s-%s" % (entry["time"], entry["message"][:20]),
                "name": entry["time"], "state": entry["level"], "ram": "-",
                "network": "-", "note": entry["message"],
                "tone": {"error": "error", "warn": "warn"}.get(entry["level"], "dim"),
                "running": False, "blocked": None,
                "detail": [("unit", entry.get("unit") or "-"),
                           ("level", entry["level"])],
            })
        return listed

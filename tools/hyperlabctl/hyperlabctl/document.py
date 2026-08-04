"""Assembles the one document that every renderer reads.

A provider that fails does not take the document down: its section becomes null
and the reason lands in `problems`. A cockpit that blanks out because one read
failed is worse than no cockpit.
"""

import datetime

from . import SCHEMA_VERSION
from .errors import HyperlabError
from .providers import providers


def build(ctx, only=None):
    document = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    problems = []
    for provider in providers():
        if only and provider.key not in only:
            continue
        try:
            section = provider.collect(ctx)
        except HyperlabError as exc:
            document[provider.key] = None
            problems.append({
                "id": exc.problem_id,
                "severity": exc.severity,
                "provider": provider.key,
                "message": str(exc),
            })
            continue
        except Exception as exc:  # noqa: BLE001 - a provider bug must not blank the panel
            document[provider.key] = None
            problems.append({
                "id": "provider.crashed",
                "severity": "error",
                "provider": provider.key,
                "message": "%s: %s" % (type(exc).__name__, exc),
            })
            continue
        document[provider.key] = section
        for problem in provider.problems(ctx, section):
            problem.setdefault("provider", provider.key)
            problems.append(problem)
    document["problems"] = problems
    return document


def worst_severity(document):
    severities = {problem["severity"] for problem in document.get("problems", [])}
    if "error" in severities:
        return "error"
    if "warn" in severities:
        return "warn"
    return "ok"

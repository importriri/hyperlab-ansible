"""The document holds together when a provider does not."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.providers.base import Provider


def test_document_lists_every_registered_section():
    ctx = world.build(trust=None)
    built = document.build(ctx)
    for section in ("host", "trust", "memory", "gpu", "networks", "domains", "store"):
        check("document_has_%s" % section, section in built)


def test_document_survives_a_crashing_provider():
    class ExplodingProvider(Provider):
        key = "exploding"
        order = 999

        def collect(self, ctx):
            raise ZeroDivisionError("boom")

    try:
        built = document.build(world.build(trust=None))
        equals("crashed_section_is_null", built["exploding"], None)
        crashed = [p for p in built["problems"] if p["provider"] == "exploding"]
        equals("crash_recorded_once", len(crashed), 1)
        equals("crash_is_an_error", crashed[0]["severity"], "error")
        check("other_sections_survived", built["networks"] is not None)
    finally:
        from hyperlabctl.providers.base import REGISTRY
        REGISTRY.pop("exploding", None)


def test_document_without_profile_report_degrades_two_sections():
    built = document.build(world.build(trust=None, profile_report=False))
    equals("memory_is_null", built["memory"], None)
    equals("gpu_is_null", built["gpu"], None)
    check("problem_names_preflight",
          any("preflight" in p["message"] for p in built["problems"]))


def test_schema_version_is_stated():
    equals("schema_version", document.build(world.build(trust=None))["schema_version"], 1)

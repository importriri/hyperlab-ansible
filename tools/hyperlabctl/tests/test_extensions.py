"""The extension points: a provider file dropped outside the package."""

import tempfile
from pathlib import Path

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.providers import FAILED_EXTERNAL, load_external
from hyperlabctl.providers.base import REGISTRY

GOOD = '''
from hyperlabctl.providers.base import Provider


class ContribProvider(Provider):
    key = "contrib_ok"
    order = 500
    summary = "a section added from outside the package"

    def collect(self, ctx):
        return {"hello": "world"}
'''

BROKEN = "raise RuntimeError('this extension is broken')\n"


def _directory(files):
    base = Path(tempfile.mkdtemp(prefix="hyperlab-contrib-"))
    for name, text in files.items():
        (base / name).write_text(text)
    return base


def test_an_external_provider_becomes_a_section_of_the_document():
    base = _directory({"contrib_ok.py": GOOD})
    try:
        load_external([base])
        check("registered", "contrib_ok" in REGISTRY)
        built = document.build(world.build(trust=None))
        equals("section_present", built["contrib_ok"], {"hello": "world"})
    finally:
        REGISTRY.pop("contrib_ok", None)


def test_a_broken_external_provider_is_recorded_and_skipped():
    before = len(FAILED_EXTERNAL)
    base = _directory({"contrib_bad.py": BROKEN})
    load_external([base])
    equals("failure_recorded", len(FAILED_EXTERNAL), before + 1)
    check("failure_names_the_file", "contrib_bad.py" in FAILED_EXTERNAL[-1]["path"])


def test_a_broken_extension_does_not_stop_a_good_one():
    base = _directory({"contrib_bad2.py": BROKEN, "contrib_ok2.py":
                       GOOD.replace("contrib_ok", "contrib_ok2")})
    try:
        load_external([base])
        check("good_one_still_loaded", "contrib_ok2" in REGISTRY)
    finally:
        REGISTRY.pop("contrib_ok2", None)


def test_a_missing_directory_is_not_an_error():
    equals("missing_dir_is_quiet", load_external(["/nonexistent/hyperlab"]) is not None, True)


def test_files_starting_with_underscore_are_skipped():
    base = _directory({"_private.py": BROKEN})
    before = len(FAILED_EXTERNAL)
    load_external([base])
    equals("underscore_skipped", len(FAILED_EXTERNAL), before)

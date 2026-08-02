"""Process execution must be locale-stable and preserve explicit timeouts."""

from harness import equals
from hyperlabctl.runner import Runner


def test_runner_forces_machine_parseable_locale():
    runner = Runner(environ={"LANG": "it_IT.UTF-8"})
    equals("runner_lc_all", runner.environ["LC_ALL"], "C")
    equals("runner_lang", runner.environ["LANG"], "C")


def test_runner_preserves_an_explicit_no_timeout():
    import hyperlabctl.runner as runner_module

    seen = {}
    original = runner_module.subprocess.run

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return Completed()

    runner_module.subprocess.run = fake_run
    try:
        Runner().run(["true"], timeout=None)
    finally:
        runner_module.subprocess.run = original
    equals("runner_explicit_no_timeout", seen["timeout"], None)

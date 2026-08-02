"""Package defaults, then the system file, then the user file, then flags."""

from harness import check, equals
from hyperlabctl.config import DEFAULTS, Config


def test_defaults_are_used_when_no_file_and_no_override():
    config = Config(repo_root=".", read_files=False)
    equals("default_virsh", config.virsh_bin, DEFAULTS["virsh_bin"])
    equals("default_uri", config.libvirt_uri, DEFAULTS["libvirt_uri"])


def test_an_override_beats_the_default():
    config = Config(repo_root=".", overrides={"virsh_bin": "/opt/virsh"}, read_files=False)
    equals("override_wins", config.virsh_bin, "/opt/virsh")


def test_every_documented_key_exists_on_the_object():
    config = Config(repo_root=".", read_files=False)
    for key in DEFAULTS:
        check("config_has_%s" % key, hasattr(config, key))


def test_the_journal_units_are_configurable_rather_than_hardcoded():
    config = Config(repo_root=".", overrides={"journal_units": ["virtqemud"]},
                    read_files=False)
    equals("units_overridden", config.journal_units, ["virtqemud"])


def test_reading_files_is_optional_so_tests_are_not_host_dependent():
    check("read_files_flag_exists", Config(repo_root=".", read_files=False) is not None)

"""hyperlabctl - the thin control surface for the Hyperlab.

Contract (ADR 0004): standard library plus PyYAML, nothing else in the core
path. virsh is the libvirt interface, not libvirt-python. --json and --no-color
are core, not extras.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = 1

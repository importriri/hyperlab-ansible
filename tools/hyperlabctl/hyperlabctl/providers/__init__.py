"""Import every provider module so its subclass registers itself.

Two sources. The modules shipped in this package, and any directory the config
names in `provider_paths` (plus ~/.config/hyperlabctl/providers). The second is
the extension point: a file dropped there becomes a section of the status
document, and the panel, the bar and the palette pick it up without a line of
code changing anywhere else.
"""

import importlib
import importlib.util
import pkgutil
from pathlib import Path

from .base import Provider, REGISTRY, providers  # noqa: F401

for _module in pkgutil.iter_modules(__path__):
    if _module.name != "base":
        importlib.import_module("%s.%s" % (__name__, _module.name))

LOADED_EXTERNAL = []
FAILED_EXTERNAL = []


def load_external(directories):
    """Load provider modules from directories outside the package.

    A file that raises on import is recorded and skipped, never fatal: a broken
    extension must not take the cockpit down with it.
    """
    for directory in directories:
        base = Path(directory).expanduser()
        if not base.is_dir():
            continue
        for source in sorted(base.glob("*.py")):
            if source.name.startswith("_"):
                continue
            name = "hyperlabctl_contrib_%s" % source.stem
            try:
                spec = importlib.util.spec_from_file_location(name, source)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as exc:  # noqa: BLE001 - third-party contrib code fails any way it likes
                FAILED_EXTERNAL.append({"path": str(source), "error": "%s: %s"
                                        % (type(exc).__name__, exc)})
                continue
            LOADED_EXTERNAL.append(str(source))
    return LOADED_EXTERNAL

"""Import every command module so its subclass registers itself."""

import importlib
import pkgutil

from .base import Command, REGISTRY, commands  # noqa: F401

for _module in pkgutil.iter_modules(__path__):
    if _module.name != "base":
        importlib.import_module("%s.%s" % (__name__, _module.name))

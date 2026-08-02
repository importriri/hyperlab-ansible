"""A command owns one subcommand. Adding one means adding a file here.

Same discovery rule as providers: the package imports every module and every
Command subclass registers itself. Nothing central lists the subcommands.
"""

REGISTRY = {}


class Command:
    name = None
    help = ""
    order = 100

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "name", None) is None:
            return
        if cls.name in REGISTRY and REGISTRY[cls.name] is not cls:
            raise RuntimeError("two commands claim the name %r" % cls.name)
        REGISTRY[cls.name] = cls

    def configure(self, parser):
        """Add this command's arguments. Optional."""

    def run(self, args, ctx):
        raise NotImplementedError


def commands():
    return [REGISTRY[name]() for name in sorted(REGISTRY, key=lambda n: (REGISTRY[n].order, n))]

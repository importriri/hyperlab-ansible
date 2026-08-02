"""A provider owns exactly one section of the status document.

Adding a section means adding a file in this package. Nothing central lists
them: the package imports every module it contains and every Provider subclass
registers itself. Removing a file removes the section, and the schema test
notices.
"""

REGISTRY = {}


class Provider:
    key = None
    order = 100
    summary = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "key", None) is None:
            return
        if cls.key in REGISTRY and REGISTRY[cls.key] is not cls:
            raise RuntimeError("two providers claim the section %r" % cls.key)
        REGISTRY[cls.key] = cls

    def collect(self, ctx):
        raise NotImplementedError

    def problems(self, ctx, section):
        """Optional. Returns dicts with id, severity and message."""
        return []


def providers():
    return [REGISTRY[key]() for key in sorted(REGISTRY, key=lambda k: (REGISTRY[k].order, k))]

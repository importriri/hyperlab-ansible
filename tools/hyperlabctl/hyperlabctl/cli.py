"""Argument parsing. The subcommand list is discovered, never typed here."""

import argparse
from pathlib import Path
import re
import stat
import sys

from . import __version__
from .commands import commands
from .config import Config, Context
from .errors import HyperlabError
from .runner import Runner


def _product_info(path: Path) -> tuple[str, str]:
    """Read the bounded name and byline; refuse ambiguous or redirected input."""
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("redirected input")
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or not mode & 0o444:
            raise ValueError("unreadable input")
        with path.open(encoding="utf-8", newline="") as stream:
            raw = stream.read()
        word = r"([A-Za-z][A-Za-z0-9]*(?: [A-Za-z0-9]+)*)"
        match = re.fullmatch(
            r'[ \t]*\{[ \t]*"name"[ \t]*:[ \t]*"' + word
            + r'"[ \t]*,[ \t]*"byline"[ \t]*:[ \t]*"' + word
            + r'"[ \t]*\}[ \t]*(?:\r?\n)?', raw,
        )
        if match is None or any(len(value) > 64 for value in match.groups()):
            raise ValueError("invalid fields")
        return match[1], match[2]
    except (OSError, UnicodeError, ValueError) as exc:
        raise HyperlabError("invalid product name input") from exc


def _product_path() -> Path:
    return Path(__file__).absolute().parents[2] / "product.yml"


class _ProductParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        """Keep discovered command help in the current product vocabulary."""
        name, _byline = _product_info(_product_path())
        return re.sub(r"\b(?:HyperLab|Hyperlab|HYPERLAB)\b", name,
                      super().format_help().replace("{product_name}", name))


class _ProductVersion(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        name, _byline = _product_info(_product_path())
        print(f"{name} (hyperlabctl {__version__})")
        parser.exit()


def _normalize_global_options(argv):
    """Allow global flags before or after a subcommand.

    The shell surfaces naturally say ``hyperlabctl vm list --json``. argparse
    normally accepts root options only before ``vm``; moving the known globals
    to the front keeps both spellings equivalent without duplicating options on
    every discovered subparser.
    """
    globals_ = []
    rest = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ("--json", "--no-color"):
            globals_.append(token)
        elif token == "--repo":
            if index + 1 >= len(argv):
                rest.append(token)
            else:
                globals_.extend((token, argv[index + 1]))
                index += 1
        elif token.startswith("--repo="):
            globals_.append(token)
        else:
            rest.append(token)
        index += 1
    return globals_ + rest


def build_parser():
    parser = _ProductParser(
        prog="hyperlabctl",
        description="Control surface for {product_name}. Reads the repository "
                    "contract and libvirt; owns no policy of its own.",
    )
    parser.add_argument("--version", action=_ProductVersion, nargs=0,
                        help="show program's version number and exit")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--no-color", dest="color", action="store_false", default=None,
                        help="never emit colour")
    parser.add_argument("--repo", metavar="PATH", help="repository checkout to read")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in commands():
        child = sub.add_parser(command.name, help=command.help)
        command.configure(child)
        child.set_defaults(_command=command)
    return parser


def main(argv=None, ctx=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        parser = build_parser()
        args = parser.parse_args(_normalize_global_options(list(argv)))
        if args.color is None:
            args.color = sys.stdout.isatty()

        if ctx is None:
            ctx = Context(Config(repo_root=args.repo), Runner())
        return args._command.run(args, ctx)
    except HyperlabError as exc:
        print("hyperlabctl: %s" % exc, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130

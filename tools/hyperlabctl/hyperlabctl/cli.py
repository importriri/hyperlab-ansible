"""Argument parsing. The subcommand list is discovered, never typed here."""

import argparse
import sys

from . import __version__
from .commands import commands
from .config import Config, Context
from .errors import HyperlabError
from .runner import Runner


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
    parser = argparse.ArgumentParser(
        prog="hyperlabctl",
        description="Control surface for the HyperLab. Reads the repository "
                    "contract and libvirt; owns no policy of its own.",
    )
    parser.add_argument("--version", action="version", version="hyperlabctl %s" % __version__)
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
    parser = build_parser()
    args = parser.parse_args(_normalize_global_options(list(argv)))
    if args.color is None:
        args.color = sys.stdout.isatty()

    if ctx is None:
        ctx = Context(Config(repo_root=args.repo), Runner())
    try:
        return args._command.run(args, ctx)
    except HyperlabError as exc:
        print("hyperlabctl: %s" % exc, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130

#!/usr/bin/env python3
"""Read-only HyperLab trust presentation coordinator.

Pipeline:

focused host surface
    -> host-owned provenance resolver
    -> reviewed trust identity
    -> pure wallpaper/RGB planner
    -> read-only presentation plan

This coordinator performs no compositor, RGB, trust, privilege or filesystem
mutation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


SCHEMA_VERSION = 1


class CoordinatorError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinatorError(message)


def load_module(
    path: Path,
    name: str,
) -> ModuleType:
    require(
        path.is_file(),
        f"required module missing: {path}",
    )

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    require(
        spec is not None
        and spec.loader is not None,
        f"cannot load module: {path}",
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def modules(
    repo: Path,
) -> tuple[ModuleType, ModuleType]:
    resolver = load_module(
        repo / "tools/surface_provenance.py",
        "hyperlab_surface_provenance",
    )

    engine = load_module(
        repo / "tools/trust_wallpaper_engine.py",
        "hyperlab_trust_wallpaper_engine",
    )

    return resolver, engine


def hold_plan(
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "mode": "hold",
        "presentation_identity": (
            provenance.get(
                "presentation_identity"
            )
            or "host"
        ),
        "trust": provenance.get("trust"),
        "trust_source": provenance.get(
            "trust_source"
        ),
        "domain": provenance.get("domain"),
        "reason": provenance.get(
            "reason",
            "unresolved",
        ),
        "provenance_resolved": False,
        "wallpaper_action": "hold",
        "wallpaper": None,
        "wallpaper_relative": None,
        "rgb_action": "hold",
        "rgb_provider": None,
        "rgb_zones": None,
        "guest_metadata_authoritative": False,
    }


def compose_plan(
    provenance: dict[str, Any],
    presentation: dict[str, Any],
) -> dict[str, Any]:
    require(
        provenance.get("resolved") is True,
        "resolved presentation requires resolved provenance",
    )

    trust = provenance.get("trust")

    require(
        isinstance(trust, str)
        and trust,
        "resolved provenance has no trust identity",
    )

    require(
        presentation.get("trust") == trust,
        "planner trust differs from provenance trust",
    )

    require(
        presentation.get("trust_source")
        == "host-owned",
        "planner lost host-owned trust contract",
    )

    require(
        presentation.get("wallpaper_may_set_trust")
        is False,
        "wallpaper gained trust authority",
    )

    require(
        presentation.get("rgb_follows_wallpaper")
        is False,
        "RGB began following artwork",
    )

    require(
        presentation.get("rgb_follows_trust")
        is True,
        "RGB disconnected from trust",
    )

    return {
        "schema": SCHEMA_VERSION,
        "mode": "planned",
        "presentation_identity": trust,
        "trust": trust,
        "trust_source": provenance.get(
            "trust_source"
        ),
        "domain": provenance.get("domain"),
        "network_profile": provenance.get(
            "network_profile"
        ),
        "surface_class": provenance.get(
            "surface_class"
        ),
        "provenance_resolved": True,
        "wallpaper_action": "would-set",
        "wallpaper": presentation["wallpaper"],
        "wallpaper_relative": (
            presentation["wallpaper_relative"]
        ),
        "wallpaper_index": (
            presentation["wallpaper_index"]
        ),
        "wallpaper_count": (
            presentation["wallpaper_count"]
        ),
        "next_rotation_epoch": (
            presentation["next_rotation_epoch"]
        ),
        "seconds_until_rotation": (
            presentation["seconds_until_rotation"]
        ),
        "rgb_action": "would-set",
        "rgb_provider": (
            presentation["rgb_provider"]
        ),
        "rgb_zones": presentation["rgb_zones"],
        "guest_metadata_authoritative": False,
    }


def build_plan(
    *,
    repo: Path,
    pool_root: Path,
    surface: dict[str, Any],
    registry_path: Path | None,
    proc_root: Path,
    epoch: float,
    resolver_module: ModuleType | None = None,
    engine_module: ModuleType | None = None,
) -> dict[str, Any]:
    if (
        resolver_module is None
        or engine_module is None
    ):
        loaded_resolver, loaded_engine = modules(
            repo
        )

        if resolver_module is None:
            resolver_module = loaded_resolver

        if engine_module is None:
            engine_module = loaded_engine

    registry = resolver_module.optional_registry(
        registry_path
    )

    provenance = resolver_module.resolve(
        repo=repo,
        surface=surface,
        registry=registry,
        proc_root=proc_root,
    )

    if (
        provenance.get("resolved") is not True
        or provenance.get(
            "wallpaper_allowed"
        ) is not True
        or provenance.get("rgb_allowed")
        is not True
    ):
        return hold_plan(provenance)

    trust = provenance.get("trust")

    require(
        isinstance(trust, str)
        and trust,
        "resolved provenance lacks trust",
    )

    pool = engine_module.load_pool(
        pool_root
    )

    presentation = engine_module.plan(
        pool_root,
        pool,
        trust,
        epoch,
    )

    return compose_plan(
        provenance,
        presentation,
    )


def parse_surface(
    raw: str,
) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoordinatorError(
            "surface JSON is invalid"
        ) from exc

    require(
        isinstance(value, dict),
        "surface JSON must be an object",
    )

    return value


def emit(
    payload: dict[str, Any],
) -> None:
    print(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )

    parser.add_argument(
        "--pool-root",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--proc-root",
        type=Path,
        default=Path("/proc"),
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("validate")

    one = sub.add_parser("plan")

    one.add_argument(
        "--surface-json",
        required=True,
    )

    one.add_argument(
        "--epoch",
        type=float,
        default=None,
    )

    stream = sub.add_parser("stream")

    stream.add_argument(
        "--epoch",
        type=float,
        default=None,
        help=(
            "Fixed test epoch. Production stream "
            "uses current time when omitted."
        ),
    )

    return parser


def main() -> int:
    args = argument_parser().parse_args()

    pool_root = (
        args.pool_root
        if args.pool_root is not None
        else (
            args.repo
            / "themes/assets/hyperlab-trust-v2"
        )
    )

    try:
        resolver, engine = modules(
            args.repo
        )

        if args.command == "validate":
            engine.load_pool(pool_root)

            print(
                "TRUST_PRESENTATION_COORDINATOR_SCHEMA=1"
            )
            print(
                "COORDINATOR_MODE=READ_ONLY"
            )
            print(
                "FOCUS_SOURCE=HOST_PID"
            )
            print(
                "TRUST_SOURCE=HOST_OWNED_PROVENANCE"
            )
            print(
                "UNRESOLVED_POLICY=HOLD"
            )
            print(
                "TRUST_PRESENTATION_COORDINATOR=PASS"
            )
            return 0

        fixed_epoch = args.epoch

        if args.command == "plan":
            epoch = (
                time.time()
                if fixed_epoch is None
                else fixed_epoch
            )

            emit(
                build_plan(
                    repo=args.repo,
                    pool_root=pool_root,
                    surface=parse_surface(
                        args.surface_json
                    ),
                    registry_path=args.registry,
                    proc_root=args.proc_root,
                    epoch=epoch,
                    resolver_module=resolver,
                    engine_module=engine,
                )
            )

            return 0

        if args.command == "stream":
            for line in sys.stdin:
                raw = line.strip()

                if not raw:
                    continue

                epoch = (
                    time.time()
                    if fixed_epoch is None
                    else fixed_epoch
                )

                emit(
                    build_plan(
                        repo=args.repo,
                        pool_root=pool_root,
                        surface=parse_surface(raw),
                        registry_path=args.registry,
                        proc_root=args.proc_root,
                        epoch=epoch,
                        resolver_module=resolver,
                        engine_module=engine,
                    )
                )

            return 0

        raise AssertionError(
            "unreachable coordinator command"
        )

    except (
        CoordinatorError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"HyperLab trust presentation coordinator: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

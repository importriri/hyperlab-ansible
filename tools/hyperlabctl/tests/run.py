#!/usr/bin/env python
"""Runs every test_*.py in this directory. Exit 1 if anything failed."""

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import harness  # noqa: E402

modules = [importlib.import_module(item.stem)
           for item in sorted(HERE.glob("test_*.py"))]
harness.main(modules)

#!/usr/bin/env python3
"""Compatibility entry point that delegates to the unified 53-texture builder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_texture_overrides import build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path, help="BABBDI installation directory")
    parser.add_argument("--output", required=True, type=Path, help="Texture override output directory")
    parser.add_argument("--work-dir", type=Path, help="Directory for source, result, and mask review files")
    parser.add_argument(
        "--handwriting-font",
        type=Path,
        default=None,
        help="Unused legacy flag kept for CLI compatibility",
    )
    args = parser.parse_args()
    try:
        return build(args)
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

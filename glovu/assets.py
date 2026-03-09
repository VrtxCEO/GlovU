from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """
    Return the absolute path to a bundled asset.

    Works in source tree and in PyInstaller onefile builds.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name

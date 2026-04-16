from __future__ import annotations

import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_TEMP_ROOT = PROJECT_ROOT / ".local" / "tmp"


def local_temp_root() -> Path:
    configured_root = os.getenv("PLAYER_WIKI_TEMP_DIR", "").strip()
    root = Path(configured_root) if configured_root else DEFAULT_LOCAL_TEMP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def temporary_directory(*, prefix: str = "player-wiki-") -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix, dir=str(local_temp_root()))

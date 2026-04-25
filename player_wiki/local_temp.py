from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import shutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_TEMP_ROOT = PROJECT_ROOT / ".local" / "tmp"


def local_temp_root() -> Path:
    configured_root = os.getenv("PLAYER_WIKI_TEMP_DIR", "").strip()
    root = Path(configured_root) if configured_root else DEFAULT_LOCAL_TEMP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


@contextmanager
def temporary_directory(*, prefix: str = "player-wiki-") -> Iterator[str]:
    root = local_temp_root()
    for _ in range(100):
        path = root / f"{prefix}{secrets.token_hex(8)}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        break
    else:
        raise FileExistsError(f"Could not create a unique temporary directory under {root}.")

    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)

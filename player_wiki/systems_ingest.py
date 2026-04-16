from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from .local_temp import temporary_directory


class SystemsIngestError(ValueError):
    pass


def _normalize_archive_member_path(raw_name: str) -> PurePosixPath | None:
    normalized = raw_name.replace("\\", "/").strip("/")
    if not normalized:
        return None

    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise SystemsIngestError("Import archives must not contain absolute or parent-relative paths.")
    return pure_path


def _resolve_extracted_data_root(extract_root: Path) -> Path:
    candidates = [extract_root]
    top_level_dirs = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(top_level_dirs) == 1:
        candidates.append(top_level_dirs[0])

    for candidate in candidates:
        if (candidate / "data").is_dir():
            return candidate

    raise SystemsIngestError(
        "Import archives must contain a compatible DND 5E source data/ directory at the root or inside one top-level folder."
    )


@contextmanager
def extracted_systems_archive(data_blob: bytes):
    try:
        archive = zipfile.ZipFile(BytesIO(data_blob))
    except zipfile.BadZipFile as exc:
        raise SystemsIngestError("Import archive must be a valid ZIP file.") from exc

    with archive:
        with temporary_directory(prefix="player-wiki-systems-import-") as temp_dir:
            extract_root = Path(temp_dir) / "archive"
            extract_root.mkdir(parents=True, exist_ok=True)
            wrote_any_files = False

            for member in archive.infolist():
                pure_path = _normalize_archive_member_path(member.filename)
                if pure_path is None:
                    continue

                destination = (extract_root / Path(*pure_path.parts)).resolve()
                if extract_root.resolve() not in destination.parents and destination != extract_root.resolve():
                    raise SystemsIngestError("Import archive contains an unsafe file path.")

                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source_handle, destination.open("wb") as destination_handle:
                    shutil.copyfileobj(source_handle, destination_handle)
                wrote_any_files = True

            if not wrote_any_files:
                raise SystemsIngestError("Import archive did not contain any files.")

            yield _resolve_extracted_data_root(extract_root)

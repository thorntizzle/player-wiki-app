"""Private publication boundary for newly managed Player Wiki images."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import errno
import re
import secrets
import stat

from .campaign_content_service import CampaignContentError
from .db import get_db
from .models import DEPRECATED_WIKI_PAGE_TYPES, DEPRECATED_WIKI_SECTIONS


MANAGED_WIKI_IMAGE_ROOT = "wiki-managed"
_MANAGED_REF = re.compile(r"wiki-managed/v1/[0-9a-f]{32}\.(?:png|jpg|jpeg|gif|webp)\Z")


def is_canonical_managed_wiki_image_ref(asset_ref: str) -> bool:
    return bool(_MANAGED_REF.fullmatch(asset_ref))


def is_managed_wiki_asset_target(assets_dir: str | Path, asset_ref: str) -> bool:
    """Classify both literal namespace paths and aliases resolving into it."""

    normalized = str(asset_ref or "").strip().replace("\\", "/").strip("/")
    parts = PurePosixPath(normalized).parts
    if parts and parts[0].casefold() == MANAGED_WIKI_IMAGE_ROOT:
        return True
    try:
        root = Path(assets_dir).resolve()
        target = (root / Path(*parts)).resolve()
        managed_root = root / MANAGED_WIKI_IMAGE_ROOT
        return target == managed_root or managed_root in target.parents
    except (OSError, RuntimeError, ValueError):
        # An unresolvable alias must not fall through to legacy asset handling.
        return True


def _checked_lexical_path(path: Path) -> Path:
    """Keep the original path while checking every existing ancestor."""

    path = path.absolute()
    for component in (*reversed(path.parents), path):
        try:
            details = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EPERM, errno.ELOOP, errno.ENOTDIR, errno.EISDIR}:
                raise CampaignContentError("Managed wiki image path is unsafe.") from exc
            raise
        if (stat.S_ISLNK(details.st_mode)
                or int(getattr(details, "st_file_attributes", 0)) & 0x400
                or (not stat.S_ISREG(details.st_mode) if component == path
                    else not stat.S_ISDIR(details.st_mode))):
            raise CampaignContentError("Managed wiki image path is unsafe.")
    return path


def managed_wiki_image_path(
    assets_dir: str | Path,
    asset_ref: str,
    *,
    require_absent: bool = False,
    create_parents: bool = False,
) -> Path:
    """Require the exact reserved path, without symlink or reparse aliases."""

    if not is_canonical_managed_wiki_image_ref(asset_ref):
        raise CampaignContentError("Managed wiki image reference is invalid.")
    if ".." in Path(assets_dir).parts:
        raise CampaignContentError("Managed wiki image root is unsafe.")
    path = _checked_lexical_path(
        Path(assets_dir).joinpath(*PurePosixPath(asset_ref).parts)
    )
    if create_parents:
        for parent in reversed(path.parents):
            try:
                parent.lstat()
            except FileNotFoundError:
                try:
                    parent.mkdir()
                except FileExistsError:
                    pass
            _checked_lexical_path(path)
        _checked_lexical_path(path)
    if require_absent:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise CampaignContentError("Managed wiki image destination is already in use.")
        _checked_lexical_path(path)
    return path


def allocate_managed_wiki_image_path(assets_dir: str | Path, extension: str) -> tuple[str, Path]:
    suffix = str(extension).lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        raise CampaignContentError("Managed wiki image extension is invalid.")
    for _ in range(10):
        asset_ref = f"{MANAGED_WIKI_IMAGE_ROOT}/v1/{secrets.token_hex(16)}{suffix}"
        try:
            return asset_ref, managed_wiki_image_path(assets_dir, asset_ref, require_absent=True)
        except CampaignContentError as exc:
            if "already in use" not in str(exc):
                raise
    raise CampaignContentError("Managed wiki image identity could not be allocated.")


def is_visible_managed_wiki_image(campaign_slug: str, current_session: int, asset_ref: str) -> bool:
    """Read one SQLite snapshot of page visibility and journal ownership."""

    from .committed_publication import active, image_bytes
    if active():
        return image_bytes(campaign_slug, asset_ref) is not None
    if not is_canonical_managed_wiki_image_ref(asset_ref):
        return False
    section_placeholders = ", ".join("?" for _ in DEPRECATED_WIKI_SECTIONS)
    type_placeholders = ", ".join("?" for _ in DEPRECATED_WIKI_PAGE_TYPES)
    row = get_db().execute(
        f"""
        SELECT 1 FROM campaign_pages AS page
        WHERE page.campaign_slug = ? AND page.image_path = ?
          AND page.published = 1 AND page.reveal_after_session <= ?
          AND lower(trim(page.section)) NOT IN ({section_placeholders})
          AND lower(trim(page.page_type)) NOT IN ({type_placeholders})
          AND NOT EXISTS (
              SELECT 1 FROM player_wiki_reconciliation_operations AS operation
              WHERE operation.campaign_slug = page.campaign_slug
                AND operation.page_ref = page.page_ref
                AND operation.state IN ('prepared', 'repository_pending', 'conflict')
          )
          AND NOT EXISTS (
              SELECT 1 FROM player_wiki_deletion_operations AS deletion
              WHERE deletion.campaign_slug = page.campaign_slug
                AND deletion.page_ref = page.page_ref
                AND deletion.state IN ('prepared', 'repository_pending', 'conflict')
          )
          AND NOT EXISTS (
              SELECT 1 FROM player_wiki_reconciliation_operations AS image_operation
              WHERE image_operation.campaign_slug = page.campaign_slug
                AND image_operation.desired_primary_ref = ?
                AND image_operation.state IN ('prepared', 'repository_pending', 'conflict')
          )
        LIMIT 1
        """,
        (
            campaign_slug, asset_ref, int(current_session),
            *sorted(DEPRECATED_WIKI_SECTIONS), *sorted(DEPRECATED_WIKI_PAGE_TYPES), asset_ref,
        ),
    ).fetchone()
    return row is not None

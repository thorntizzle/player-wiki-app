"""Private publication boundary for newly managed Player Wiki images."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
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


def _is_link_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CampaignContentError("Managed wiki image path is unsafe.") from exc
    return stat.S_ISLNK(details.st_mode) or bool(int(getattr(details, "st_file_attributes", 0)) & 0x400)


def managed_wiki_image_path(
    assets_dir: str | Path,
    asset_ref: str,
    *,
    require_absent: bool = False,
) -> Path:
    """Require the exact reserved path, without symlink or reparse aliases."""

    if not is_canonical_managed_wiki_image_ref(asset_ref):
        raise CampaignContentError("Managed wiki image reference is invalid.")
    supplied_root = Path(assets_dir)
    if _is_link_or_reparse(supplied_root):
        raise CampaignContentError("Managed wiki image root is unsafe.")
    try:
        root = supplied_root.resolve()
    except (OSError, RuntimeError) as exc:
        raise CampaignContentError("Managed wiki image root is unsafe.") from exc
    path = root.joinpath(*PurePosixPath(asset_ref).parts)
    for component in (root, root / MANAGED_WIKI_IMAGE_ROOT, root / MANAGED_WIKI_IMAGE_ROOT / "v1", path):
        if _is_link_or_reparse(component):
            raise CampaignContentError("Managed wiki image path is unsafe.")
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise CampaignContentError("Managed wiki image path is unsafe.") from exc
    if resolved != path:
        raise CampaignContentError("Managed wiki image path is unsafe.")
    if require_absent and path.exists():
        raise CampaignContentError("Managed wiki image destination is already in use.")
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

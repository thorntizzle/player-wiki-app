from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import mimetypes
from pathlib import Path, PurePosixPath
import shutil
from typing import Any

import yaml

from .auth_store import AuthStore, isoformat, utcnow
from .campaign_page_store import CampaignPageRecord, CampaignPageStore
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_repository import load_campaign_character_config
from .character_service import build_initial_state
from .character_store import CharacterStateStore
from .db import get_db
from .models import Campaign, Page, page_sort_key
from .repository import slugify


class CampaignContentError(ValueError):
    pass


CAMPAIGN_CONFIG_EDITABLE_KEYS = {
    "title",
    "summary",
    "system",
    "current_session",
    "source_wiki_root",
    "systems_library",
}


@dataclass(slots=True)
class CampaignConfigRecord:
    campaign_slug: str
    config_path: Path
    config: dict[str, Any]
    updated_at: str


@dataclass(slots=True)
class CampaignPageFileRecord:
    page_ref: str
    relative_path: str
    file_path: Path
    metadata: dict[str, Any]
    body_markdown: str
    page: Page
    updated_at: str


@dataclass(slots=True)
class CampaignAssetFileRecord:
    asset_ref: str
    relative_path: str
    file_path: Path
    size_bytes: int
    media_type: str
    updated_at: str


@dataclass(slots=True)
class CampaignCharacterFileRecord:
    character_slug: str
    character_dir: Path
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    updated_at: str
    state_created: bool = False


@dataclass(slots=True)
class DeletedCharacterContent:
    character_slug: str
    deleted_files: bool
    deleted_state: bool
    deleted_assignment: bool
    deleted_assets: bool


def _timestamp_from_path(path: Path) -> str:
    return isoformat(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))


def _normalize_relative_file_ref(value: str, *, required_suffix: str) -> PurePosixPath:
    normalized = value.strip().replace("\\", "/").strip("/")
    if not normalized:
        raise CampaignContentError("A relative file reference is required.")

    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise CampaignContentError("Relative file references must stay within the campaign directory.")

    if required_suffix:
        if pure_path.suffix and pure_path.suffix.lower() != required_suffix.lower():
            raise CampaignContentError(f"Only {required_suffix} files are supported.")
        if not pure_path.suffix:
            pure_path = pure_path.with_suffix(required_suffix)

    return pure_path


def _resolve_relative_path(root_dir: Path, relative_ref: str, *, required_suffix: str = "") -> tuple[Path, PurePosixPath]:
    pure_path = _normalize_relative_file_ref(relative_ref, required_suffix=required_suffix)
    root_dir = root_dir.resolve()
    resolved_path = (root_dir / Path(*pure_path.parts)).resolve()
    if resolved_path != root_dir and root_dir not in resolved_path.parents:
        raise CampaignContentError("Resolved file path escapes the campaign directory.")
    return resolved_path, pure_path


def _dump_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()


def _render_markdown_with_frontmatter(metadata: dict[str, Any], body_markdown: str) -> str:
    return f"---\n{_dump_yaml(metadata)}\n---\n\n{body_markdown.strip()}\n"


def _load_campaign_config_record(config_path: Path) -> CampaignConfigRecord:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    campaign_slug = str(payload.get("slug") or config_path.parent.name).strip() or config_path.parent.name
    return CampaignConfigRecord(
        campaign_slug=campaign_slug,
        config_path=config_path,
        config=dict(payload),
        updated_at=_timestamp_from_path(config_path),
    )


def _normalize_campaign_config_updates(updates: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(updates, dict):
        raise CampaignContentError("Campaign config updates must be an object.")

    unsupported_keys = sorted(key for key in updates if key not in CAMPAIGN_CONFIG_EDITABLE_KEYS)
    if unsupported_keys:
        raise CampaignContentError(
            "Unsupported campaign config fields: " + ", ".join(unsupported_keys)
        )

    normalized: dict[str, Any] = {}
    for key, value in updates.items():
        if key == "current_session":
            try:
                normalized_value = int(value)
            except (TypeError, ValueError) as exc:
                raise CampaignContentError("current_session must be an integer.") from exc
            if normalized_value < 0:
                raise CampaignContentError("current_session must be zero or greater.")
            normalized[key] = normalized_value
            continue

        normalized_value = str(value or "").strip()
        if key == "title" and not normalized_value:
            raise CampaignContentError("Campaign title is required.")
        normalized[key] = normalized_value

    return normalized


def get_campaign_config_file(campaigns_dir: Path, campaign_slug: str) -> CampaignConfigRecord:
    config_path = campaigns_dir / campaign_slug / "campaign.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Campaign config not found: {config_path}")
    return _load_campaign_config_record(config_path)


def update_campaign_config_file(
    campaigns_dir: Path,
    campaign_slug: str,
    *,
    updates: dict[str, Any],
) -> CampaignConfigRecord:
    record = get_campaign_config_file(campaigns_dir, campaign_slug)
    normalized_updates = _normalize_campaign_config_updates(updates)
    updated_config = dict(record.config)
    updated_config.update(normalized_updates)
    record.config_path.write_text(_dump_yaml(updated_config) + "\n", encoding="utf-8")
    return _load_campaign_config_record(record.config_path)


def _build_page_file_record(
    campaign: Campaign,
    page_record: CampaignPageRecord,
) -> CampaignPageFileRecord:
    content_dir = Path(campaign.player_content_dir)
    file_path = content_dir / Path(*PurePosixPath(page_record.relative_path).parts)
    return CampaignPageFileRecord(
        page_ref=page_record.page_ref,
        relative_path=page_record.relative_path,
        file_path=file_path,
        metadata=dict(page_record.metadata),
        body_markdown=page_record.body_markdown,
        page=page_record.page,
        updated_at=page_record.updated_at,
    )


def list_campaign_page_files(
    campaign: Campaign,
    *,
    page_store: CampaignPageStore,
) -> list[CampaignPageFileRecord]:
    content_dir = Path(campaign.player_content_dir)
    records = page_store.list_page_records(
        campaign.slug,
        content_dir=content_dir,
        include_body=False,
    )
    return sorted(
        [_build_page_file_record(campaign, record) for record in records],
        key=lambda item: (*page_sort_key(item.page), item.relative_path),
    )


def get_campaign_page_file(
    campaign: Campaign,
    page_ref: str,
    *,
    page_store: CampaignPageStore,
) -> CampaignPageFileRecord | None:
    content_dir = Path(campaign.player_content_dir)
    _, pure_relative_path = _resolve_relative_path(content_dir, page_ref, required_suffix=".md")
    record = page_store.get_page_record(
        campaign.slug,
        pure_relative_path.with_suffix("").as_posix(),
        content_dir=content_dir,
        include_body=True,
    )
    if record is None:
        return None
    return _build_page_file_record(campaign, record)


def write_campaign_page_file(
    campaign: Campaign,
    page_ref: str,
    *,
    metadata: dict[str, Any],
    body_markdown: str,
    page_store: CampaignPageStore,
) -> CampaignPageFileRecord:
    if not isinstance(metadata, dict):
        raise CampaignContentError("Page metadata must be an object.")
    if not isinstance(body_markdown, str):
        raise CampaignContentError("body_markdown must be a string.")

    connection = get_db()
    content_dir = Path(campaign.player_content_dir)
    file_path, pure_relative_path = _resolve_relative_path(content_dir, page_ref, required_suffix=".md")
    normalized_metadata = dict(metadata)
    normalized_metadata.setdefault("slug", pure_relative_path.with_suffix("").as_posix())
    previous_contents = file_path.read_text(encoding="utf-8") if file_path.exists() else None

    try:
        page_store.upsert_page(
            campaign.slug,
            pure_relative_path.with_suffix("").as_posix(),
            metadata=normalized_metadata,
            body_markdown=body_markdown,
            commit=False,
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            _render_markdown_with_frontmatter(normalized_metadata, body_markdown),
            encoding="utf-8",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        try:
            if previous_contents is None:
                if file_path.exists():
                    file_path.unlink()
                    _prune_empty_parent_dirs(file_path.parent, stop_dir=content_dir)
            else:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(previous_contents, encoding="utf-8")
        except OSError:
            pass
        raise

    record = page_store.get_page_record(
        campaign.slug,
        pure_relative_path.with_suffix("").as_posix(),
        include_body=True,
    )
    if record is None:
        raise RuntimeError("Campaign page was not readable after writing.")
    return _build_page_file_record(campaign, record)


def delete_campaign_page_file(
    campaign: Campaign,
    page_ref: str,
    *,
    page_store: CampaignPageStore,
) -> CampaignPageFileRecord | None:
    existing = get_campaign_page_file(campaign, page_ref, page_store=page_store)
    if existing is None:
        return None

    connection = get_db()
    previous_contents = (
        existing.file_path.read_text(encoding="utf-8")
        if existing.file_path.exists()
        else None
    )
    try:
        page_store.delete_page(campaign.slug, existing.page_ref, commit=False)
        if existing.file_path.exists():
            existing.file_path.unlink()
            _prune_empty_parent_dirs(existing.file_path.parent, stop_dir=Path(campaign.player_content_dir))
        connection.commit()
    except Exception:
        connection.rollback()
        try:
            if previous_contents is not None and not existing.file_path.exists():
                existing.file_path.parent.mkdir(parents=True, exist_ok=True)
                existing.file_path.write_text(previous_contents, encoding="utf-8")
        except OSError:
            pass
        raise

    return existing


def _guess_media_type(file_path: Path) -> str:
    media_type, _ = mimetypes.guess_type(file_path.name)
    return media_type or "application/octet-stream"


def _load_asset_file_record(assets_dir: Path, file_path: Path) -> CampaignAssetFileRecord:
    relative_path = file_path.relative_to(assets_dir).as_posix()
    return CampaignAssetFileRecord(
        asset_ref=relative_path,
        relative_path=relative_path,
        file_path=file_path,
        size_bytes=file_path.stat().st_size,
        media_type=_guess_media_type(file_path),
        updated_at=_timestamp_from_path(file_path),
    )


def list_campaign_asset_files(campaign: Campaign) -> list[CampaignAssetFileRecord]:
    assets_dir = Path(campaign.assets_dir)
    if not assets_dir.exists():
        return []

    return [
        _load_asset_file_record(assets_dir, file_path)
        for file_path in sorted(path for path in assets_dir.rglob("*") if path.is_file())
    ]


def get_campaign_asset_file_record(campaign: Campaign, asset_ref: str) -> CampaignAssetFileRecord | None:
    assets_dir = Path(campaign.assets_dir)
    file_path, _ = _resolve_relative_path(assets_dir, asset_ref)
    if not file_path.exists() or not file_path.is_file():
        return None
    return _load_asset_file_record(assets_dir, file_path)


def write_campaign_asset_file(
    campaign: Campaign,
    asset_ref: str,
    *,
    data_blob: bytes,
) -> CampaignAssetFileRecord:
    if not isinstance(data_blob, (bytes, bytearray)):
        raise CampaignContentError("Asset file data must be bytes.")

    assets_dir = Path(campaign.assets_dir)
    file_path, _ = _resolve_relative_path(assets_dir, asset_ref)
    if file_path.exists() and file_path.is_dir():
        raise CampaignContentError("Asset file references must point to files, not directories.")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(bytes(data_blob))
    return _load_asset_file_record(assets_dir, file_path)


def delete_campaign_asset_file(campaign: Campaign, asset_ref: str) -> CampaignAssetFileRecord | None:
    existing = get_campaign_asset_file_record(campaign, asset_ref)
    if existing is None:
        return None

    existing.file_path.unlink()
    _prune_empty_parent_dirs(existing.file_path.parent, stop_dir=Path(campaign.assets_dir))
    return existing


def _load_character_file_record(campaigns_dir: Path, campaign_slug: str, character_slug: str) -> CampaignCharacterFileRecord | None:
    config = load_campaign_character_config(campaigns_dir, campaign_slug)
    character_dir = config.characters_dir / character_slug
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    if not definition_path.exists() or not import_path.exists():
        return None

    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    import_payload = yaml.safe_load(import_path.read_text(encoding="utf-8")) or {}
    definition = CharacterDefinition.from_dict(definition_payload)
    import_metadata = CharacterImportMetadata.from_dict(import_payload)
    return CampaignCharacterFileRecord(
        character_slug=character_slug,
        character_dir=character_dir,
        definition=definition,
        import_metadata=import_metadata,
        updated_at=max(_timestamp_from_path(definition_path), _timestamp_from_path(import_path)),
    )


def list_campaign_character_files(campaigns_dir: Path, campaign_slug: str) -> list[CampaignCharacterFileRecord]:
    config = load_campaign_character_config(campaigns_dir, campaign_slug)
    if not config.characters_dir.exists():
        return []

    records: list[CampaignCharacterFileRecord] = []
    for definition_path in sorted(config.characters_dir.glob("*/definition.yaml")):
        record = _load_character_file_record(campaigns_dir, campaign_slug, definition_path.parent.name)
        if record is not None:
            records.append(record)
    return records


def get_campaign_character_file(
    campaigns_dir: Path,
    campaign_slug: str,
    character_slug: str,
) -> CampaignCharacterFileRecord | None:
    return _load_character_file_record(campaigns_dir, campaign_slug, character_slug)


def write_campaign_character_file(
    campaigns_dir: Path,
    campaign_slug: str,
    character_slug: str,
    *,
    definition_payload: dict[str, Any],
    import_metadata_payload: dict[str, Any] | None,
    state_store: CharacterStateStore,
) -> CampaignCharacterFileRecord:
    if not isinstance(definition_payload, dict):
        raise CampaignContentError("Character definition must be an object.")
    if import_metadata_payload is not None and not isinstance(import_metadata_payload, dict):
        raise CampaignContentError("import_metadata must be an object when provided.")

    config = load_campaign_character_config(campaigns_dir, campaign_slug)
    existing_record = get_campaign_character_file(campaigns_dir, campaign_slug, character_slug)

    normalized_definition_payload = dict(definition_payload)
    normalized_definition_payload["campaign_slug"] = campaign_slug
    normalized_definition_payload["character_slug"] = character_slug
    normalized_definition_payload.setdefault("status", "active")
    if not normalized_definition_payload.get("name"):
        normalized_definition_payload["name"] = slugify(character_slug).replace("-", " ").title()
    definition = CharacterDefinition.from_dict(normalized_definition_payload)

    default_import_payload = (
        existing_record.import_metadata.to_dict()
        if existing_record is not None
        else {
            "campaign_slug": campaign_slug,
            "character_slug": character_slug,
            "source_path": f"api://campaigns/{campaign_slug}/characters/{character_slug}",
            "imported_at_utc": isoformat(utcnow()),
            "parser_version": "api-v1",
            "import_status": "managed",
            "warnings": [],
        }
    )
    if import_metadata_payload:
        default_import_payload.update(import_metadata_payload)
    default_import_payload["campaign_slug"] = campaign_slug
    default_import_payload["character_slug"] = character_slug
    if not default_import_payload.get("imported_at_utc"):
        default_import_payload["imported_at_utc"] = isoformat(utcnow())
    if not default_import_payload.get("parser_version"):
        default_import_payload["parser_version"] = "api-v1"
    if not default_import_payload.get("import_status"):
        default_import_payload["import_status"] = "managed"
    import_metadata = CharacterImportMetadata.from_dict(default_import_payload)

    character_dir = config.characters_dir / character_slug
    character_dir.mkdir(parents=True, exist_ok=True)
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    definition_path.write_text(_dump_yaml(definition.to_dict()) + "\n", encoding="utf-8")
    import_path.write_text(_dump_yaml(import_metadata.to_dict()) + "\n", encoding="utf-8")

    state_result = state_store.initialize_state_if_missing(definition, build_initial_state(definition))
    record = _load_character_file_record(campaigns_dir, campaign_slug, character_slug)
    if record is None:
        raise RuntimeError("Character files were not readable after writing.")
    record.state_created = state_result.created
    return record


def delete_campaign_character_file(
    campaigns_dir: Path,
    campaign_slug: str,
    character_slug: str,
    *,
    state_store: CharacterStateStore,
    auth_store: AuthStore,
) -> DeletedCharacterContent | None:
    config = load_campaign_character_config(campaigns_dir, campaign_slug)
    character_dir = config.characters_dir / character_slug
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"

    deleted_files = False
    if definition_path.exists():
        definition_path.unlink()
        deleted_files = True
    if import_path.exists():
        import_path.unlink()
        deleted_files = True
    if character_dir.exists() and not any(character_dir.iterdir()):
        character_dir.rmdir()

    portrait_assets_dir = config.campaign_dir / "assets" / "characters" / character_slug
    deleted_assets = False
    if portrait_assets_dir.exists() and portrait_assets_dir.is_dir():
        shutil.rmtree(portrait_assets_dir)
        deleted_assets = True

    deleted_state = state_store.delete_state(campaign_slug, character_slug) is not None
    deleted_assignment = auth_store.delete_character_assignment(campaign_slug, character_slug) is not None

    if not deleted_files and not deleted_state and not deleted_assignment and not deleted_assets:
        return None

    return DeletedCharacterContent(
        character_slug=character_slug,
        deleted_files=deleted_files,
        deleted_state=deleted_state,
        deleted_assignment=deleted_assignment,
        deleted_assets=deleted_assets,
    )


def _prune_empty_parent_dirs(path: Path, *, stop_dir: Path) -> None:
    current = path.resolve()
    stop_dir = stop_dir.resolve()
    while current != stop_dir and stop_dir in current.parents:
        if any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent

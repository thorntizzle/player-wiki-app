from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import CharacterPathSafetyError, resolve_character_path, validate_character_slug
from .character_service import build_initial_state
from .character_store import CharacterStateStore
from .system_policy import DND_5E_SYSTEM_CODE, normalize_system_code


@dataclass(slots=True)
class CampaignCharacterConfig:
    campaign_slug: str
    system: str
    campaign_dir: Path
    characters_dir: Path
    source_root: Path
    source_glob: str


@dataclass(slots=True)
class _CharacterPayloadCacheRecord:
    definition_signature: tuple[int, int]
    import_signature: tuple[int, int]
    system: str
    definition_payload: Any
    import_payload: Any


def load_campaign_character_config(campaigns_dir: Path, campaign_slug: str) -> CampaignCharacterConfig:
    config_path = campaigns_dir / campaign_slug / "campaign.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Campaign config not found: {config_path}")

    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    campaign_dir = config_path.parent
    characters_dir = campaign_dir / raw_config.get("character_dir", "characters")
    source_root = Path(raw_config.get("character_source_root", ""))
    source_glob = str(raw_config.get("character_source_glob", "**/* - Character Sheet.md"))

    return CampaignCharacterConfig(
        campaign_slug=raw_config.get("slug", campaign_slug),
        system=normalize_system_code(raw_config.get("system")) or DND_5E_SYSTEM_CODE,
        campaign_dir=campaign_dir,
        characters_dir=characters_dir,
        source_root=source_root,
        source_glob=source_glob,
    )


class CharacterRepository:
    def __init__(self, campaigns_dir: Path, state_store: CharacterStateStore) -> None:
        self.campaigns_dir = campaigns_dir
        self.state_store = state_store
        self._character_payload_cache: dict[tuple[str, str], _CharacterPayloadCacheRecord] = {}

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int]:
        stats = path.stat()
        return (stats.st_mtime_ns, stats.st_size)

    @staticmethod
    def _load_yaml_payload(path: Path) -> Any:
        raw_payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return raw_payload

    def _get_cached_character_payloads(
        self,
        *,
        campaign_slug: str,
        character_slug: str,
        definition_path: Path,
        import_path: Path,
        system: str,
    ) -> tuple[Any, Any]:
        definition_signature = self._file_signature(definition_path)
        import_signature = self._file_signature(import_path)
        cache_key = (campaign_slug, character_slug)
        cached = self._character_payload_cache.get(cache_key)
        if (
            cached is not None
            and cached.system == system
            and cached.definition_signature == definition_signature
            and cached.import_signature == import_signature
        ):
            return deepcopy(cached.definition_payload), deepcopy(cached.import_payload)

        definition_payload = self._load_yaml_payload(definition_path)
        import_payload = self._load_yaml_payload(import_path)
        self._character_payload_cache[cache_key] = _CharacterPayloadCacheRecord(
            definition_signature=definition_signature,
            import_signature=import_signature,
            system=system,
            definition_payload=deepcopy(definition_payload),
            import_payload=deepcopy(import_payload),
        )
        return deepcopy(definition_payload), deepcopy(import_payload)

    @staticmethod
    def is_character_visible(record: CharacterRecord) -> bool:
        return record.definition.status == "active"

    @staticmethod
    def _is_reconciliation_protected(
        campaign_slug: str,
        character_slug: str,
    ) -> bool:
        from .character_reconciliation import is_character_reconciliation_protected

        return is_character_reconciliation_protected(campaign_slug, character_slug)

    def invalidate_character(self, campaign_slug: str, character_slug: str) -> None:
        self._character_payload_cache.pop((campaign_slug, character_slug), None)

    def list_characters(self, campaign_slug: str) -> list[CharacterRecord]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        if not config.characters_dir.exists():
            return []

        records: list[CharacterRecord] = []
        for definition_path in sorted(config.characters_dir.glob("*/definition.yaml")):
            character_slug = definition_path.parent.name
            if self._is_reconciliation_protected(campaign_slug, character_slug):
                continue
            record = self.get_character(campaign_slug, character_slug)
            if record is not None:
                records.append(record)
        return records

    def list_visible_characters(self, campaign_slug: str) -> list[CharacterRecord]:
        return [record for record in self.list_characters(campaign_slug) if self.is_character_visible(record)]

    def get_character(self, campaign_slug: str, character_slug: str) -> CharacterRecord | None:
        return self._load_character(
            campaign_slug,
            character_slug,
            allow_reconciliation=False,
            initialize_missing_state=True,
        )

    def load_character_for_reconciliation(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterRecord | None:
        return self._load_character(
            campaign_slug,
            character_slug,
            allow_reconciliation=True,
            initialize_missing_state=False,
        )

    def _load_character(
        self,
        campaign_slug: str,
        character_slug: str,
        *,
        allow_reconciliation: bool,
        initialize_missing_state: bool,
    ) -> CharacterRecord | None:
        try:
            validate_character_slug(character_slug)
        except CharacterPathSafetyError:
            return None
        if (
            not allow_reconciliation
            and self._is_reconciliation_protected(campaign_slug, character_slug)
        ):
            return None
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        try:
            character_dir = resolve_character_path(config.characters_dir, character_slug)
            definition_path = resolve_character_path(
                config.characters_dir, character_slug, "definition.yaml"
            )
            import_path = resolve_character_path(
                config.characters_dir, character_slug, "import.yaml"
            )
        except CharacterPathSafetyError:
            return None
        if not definition_path.exists() or not import_path.exists():
            return None

        definition_payload, import_payload = self._get_cached_character_payloads(
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            definition_path=definition_path,
            import_path=import_path,
            system=config.system,
        )
        definition_payload = deepcopy(definition_payload)
        if (
            str(definition_payload.get("campaign_slug") or "") != campaign_slug
            or str(definition_payload.get("character_slug") or "") != character_slug
        ):
            return None
        definition_payload.setdefault("system", config.system)
        definition = CharacterDefinition.from_dict(definition_payload)
        state_record = self.state_store.get_state(campaign_slug, character_slug)
        if state_record is None and initialize_missing_state:
            state_record = self.state_store.initialize_state_if_missing(
                definition,
                build_initial_state(definition),
            ).record
        if state_record is None:
            return None
        return CharacterRecord(
            definition=definition,
            import_metadata=CharacterImportMetadata.from_dict(import_payload),
            state_record=state_record,
        )

    def get_visible_character(self, campaign_slug: str, character_slug: str) -> CharacterRecord | None:
        record = self.get_character(campaign_slug, character_slug)
        if record is None or not self.is_character_visible(record):
            return None
        return record

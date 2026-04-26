from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
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

    @staticmethod
    def is_character_visible(record: CharacterRecord) -> bool:
        return record.definition.status == "active"

    def list_characters(self, campaign_slug: str) -> list[CharacterRecord]:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        if not config.characters_dir.exists():
            return []

        records: list[CharacterRecord] = []
        for definition_path in sorted(config.characters_dir.glob("*/definition.yaml")):
            character_slug = definition_path.parent.name
            record = self.get_character(campaign_slug, character_slug)
            if record is not None:
                records.append(record)
        return records

    def list_visible_characters(self, campaign_slug: str) -> list[CharacterRecord]:
        return [record for record in self.list_characters(campaign_slug) if self.is_character_visible(record)]

    def get_character(self, campaign_slug: str, character_slug: str) -> CharacterRecord | None:
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        character_dir = config.characters_dir / character_slug
        definition_path = character_dir / "definition.yaml"
        import_path = character_dir / "import.yaml"
        if not definition_path.exists() or not import_path.exists():
            return None

        definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
        definition_payload.setdefault("system", config.system)
        import_payload = yaml.safe_load(import_path.read_text(encoding="utf-8")) or {}
        definition = CharacterDefinition.from_dict(definition_payload)
        state_record = self.state_store.get_state(campaign_slug, character_slug)
        if state_record is None:
            state_record = self.state_store.initialize_state_if_missing(
                definition,
                build_initial_state(definition),
            ).record
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

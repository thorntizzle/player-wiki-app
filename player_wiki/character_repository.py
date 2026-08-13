from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_definition_import_paths,
    validate_character_slug,
)
from .character_service import build_initial_state
from .character_store import CharacterStateStore
from .system_policy import DND_5E_SYSTEM_CODE, normalize_system_code


@dataclass(frozen=True, slots=True)
class CampaignCharacterConfig:
    campaign_slug: str
    system: str
    campaign_dir: Path
    characters_dir: Path
    source_root: Path
    source_glob: str


@dataclass(slots=True)
class _CharacterPayloadCacheRecord:
    definition_path: Path
    definition_signature: tuple[int, int, str]
    import_path: Path
    import_signature: tuple[int, int, str]
    system: str
    definition_payload: Any
    import_payload: Any


@dataclass(frozen=True, slots=True)
class _CampaignCharacterConfigCacheRecord:
    config_path: Path
    config_signature: tuple[int, int, str]
    config: CampaignCharacterConfig


@dataclass(frozen=True, slots=True)
class CharacterSnapshotFileSignature:
    character_slug: str
    definition_path: Path
    definition_signature: tuple[int, int, str]
    import_path: Path
    import_signature: tuple[int, int, str]


@dataclass(frozen=True, slots=True)
class CharacterSnapshotSourceFileToken:
    campaign_config_path: Path
    campaign_config_signature: tuple[int, int, str]
    configured_campaign_slug: str
    system: str
    characters_dir: Path
    character_files: tuple[CharacterSnapshotFileSignature, ...]


def _campaign_character_config_from_bytes(
    config_path: Path,
    campaign_slug: str,
    payload: bytes,
) -> CampaignCharacterConfig:
    raw_config = yaml.safe_load(payload.decode("utf-8")) or {}
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


def load_campaign_character_config(campaigns_dir: Path, campaign_slug: str) -> CampaignCharacterConfig:
    config_path = campaigns_dir / campaign_slug / "campaign.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Campaign config not found: {config_path}")
    return _campaign_character_config_from_bytes(
        config_path,
        campaign_slug,
        config_path.read_bytes(),
    )


class CharacterRepository:
    def __init__(self, campaigns_dir: Path, state_store: CharacterStateStore) -> None:
        self.campaigns_dir = campaigns_dir
        self.state_store = state_store
        self._character_payload_cache: dict[tuple[str, str], _CharacterPayloadCacheRecord] = {}
        self._campaign_config_cache: dict[
            str,
            _CampaignCharacterConfigCacheRecord,
        ] = {}

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int]:
        stats = path.stat()
        return (stats.st_mtime_ns, stats.st_size)

    @staticmethod
    def _load_yaml_payload(path: Path, payload: bytes | None = None) -> Any:
        exact_payload = path.read_bytes() if payload is None else payload
        raw_payload = yaml.safe_load(exact_payload.decode("utf-8")) or {}
        return raw_payload

    def _read_file_with_content_signature(
        self,
        path: Path,
    ) -> tuple[tuple[int, int, str], bytes]:
        stat_signature = self._file_signature(path)
        payload = path.read_bytes()
        return (
            stat_signature[0],
            stat_signature[1],
            sha256(payload).hexdigest(),
        ), payload

    def _get_campaign_character_config(
        self,
        campaign_slug: str,
        *,
        resolved_config_path: Path | None = None,
        config_payload: bytes | None = None,
        config_signature: tuple[int, int, str] | None = None,
    ) -> CampaignCharacterConfig:
        campaigns_root = self.campaigns_dir.resolve()
        config_path = campaigns_root / campaign_slug / "campaign.yaml"
        resolved_config_path = (
            config_path.resolve()
            if resolved_config_path is None
            else resolved_config_path
        )
        if (
            campaigns_root not in resolved_config_path.parents
            or resolved_config_path != config_path
        ):
            raise FileNotFoundError(f"Campaign config not found: {config_path}")
        if config_payload is None or config_signature is None:
            try:
                config_stat_signature = self._validated_file_signature(
                    resolved_config_path
                )
                config_payload = resolved_config_path.read_bytes()
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"Campaign config not found: {config_path}"
                ) from exc
            if config_stat_signature is None:
                return _campaign_character_config_from_bytes(
                    resolved_config_path,
                    campaign_slug,
                    config_payload,
                )
            config_signature = (
                config_stat_signature[0],
                config_stat_signature[1],
                sha256(config_payload).hexdigest(),
            )
        cached = self._campaign_config_cache.get(campaign_slug)
        if (
            cached is not None
            and cached.config_path == resolved_config_path
            and cached.config_signature == config_signature
        ):
            return cached.config
        config = _campaign_character_config_from_bytes(
            resolved_config_path,
            campaign_slug,
            config_payload,
        )
        self._campaign_config_cache[campaign_slug] = (
            _CampaignCharacterConfigCacheRecord(
                config_path=resolved_config_path,
                config_signature=config_signature,
                config=config,
            )
        )
        return config

    def get_snapshot_source_file_token(
        self,
        campaign_slug: str,
        character_slugs: list[str] | tuple[str, ...],
        *,
        previous: CharacterSnapshotSourceFileToken | None = None,
    ) -> CharacterSnapshotSourceFileToken | None:
        try:
            campaigns_root = self.campaigns_dir.resolve()
            campaign_config_path = campaigns_root / campaign_slug / "campaign.yaml"
            resolved_campaign_config_path = campaign_config_path.resolve()
            if (
                campaigns_root not in resolved_campaign_config_path.parents
                or resolved_campaign_config_path != campaign_config_path
            ):
                return None
            campaign_config_stat_signature = self._validated_file_signature(
                resolved_campaign_config_path
            )
            if campaign_config_stat_signature is None:
                return None
            campaign_config_payload = resolved_campaign_config_path.read_bytes()
            campaign_config_signature = (
                campaign_config_stat_signature[0],
                campaign_config_stat_signature[1],
                sha256(campaign_config_payload).hexdigest(),
            )

            config = self._get_campaign_character_config(
                campaign_slug,
                resolved_config_path=resolved_campaign_config_path,
                config_payload=campaign_config_payload,
                config_signature=campaign_config_signature,
            )
            configured_campaign_slug = config.campaign_slug
            system = config.system
            characters_dir = config.characters_dir.resolve()

            character_files: list[CharacterSnapshotFileSignature] = []
            for character_slug in sorted(set(character_slugs)):
                definition_path, import_path = (
                    resolve_character_definition_import_paths(
                        characters_dir,
                        character_slug,
                    )
                )
                definition_stat_signature = self._validated_file_signature(
                    definition_path
                )
                import_stat_signature = self._validated_file_signature(import_path)
                if (
                    definition_stat_signature is None
                    or import_stat_signature is None
                ):
                    return None
                definition_payload = definition_path.read_bytes()
                import_payload = import_path.read_bytes()
                definition_signature = (
                    definition_stat_signature[0],
                    definition_stat_signature[1],
                    sha256(definition_payload).hexdigest(),
                )
                import_signature = (
                    import_stat_signature[0],
                    import_stat_signature[1],
                    sha256(import_payload).hexdigest(),
                )
                character_files.append(
                    CharacterSnapshotFileSignature(
                        character_slug=character_slug,
                        definition_path=definition_path,
                        definition_signature=definition_signature,
                        import_path=import_path,
                        import_signature=import_signature,
                    )
                )
        except (CharacterPathSafetyError, OSError, TypeError, ValueError, yaml.YAMLError):
            return None

        return CharacterSnapshotSourceFileToken(
            campaign_config_path=resolved_campaign_config_path,
            campaign_config_signature=campaign_config_signature,
            configured_campaign_slug=configured_campaign_slug,
            system=system,
            characters_dir=characters_dir,
            character_files=tuple(character_files),
        )

    def _validated_file_signature(self, path: Path) -> tuple[int, int] | None:
        signature = self._file_signature(path)
        if any(type(value) is not int or value < 0 for value in signature):
            return None
        return signature

    def _get_cached_character_payloads(
        self,
        *,
        campaign_slug: str,
        character_slug: str,
        definition_path: Path,
        import_path: Path,
        system: str,
    ) -> tuple[Any, Any]:
        definition_signature, definition_bytes = (
            self._read_file_with_content_signature(definition_path)
        )
        import_signature, import_bytes = self._read_file_with_content_signature(
            import_path
        )
        cache_key = (campaign_slug, character_slug)
        cached = self._character_payload_cache.get(cache_key)
        if (
            cached is not None
            and cached.definition_path == definition_path
            and cached.import_path == import_path
            and cached.system == system
            and cached.definition_signature == definition_signature
            and cached.import_signature == import_signature
        ):
            return deepcopy(cached.definition_payload), deepcopy(cached.import_payload)

        definition_payload = self._load_yaml_payload(
            definition_path,
            definition_bytes,
        )
        import_payload = self._load_yaml_payload(import_path, import_bytes)
        self._character_payload_cache[cache_key] = _CharacterPayloadCacheRecord(
            definition_path=definition_path,
            definition_signature=definition_signature,
            import_path=import_path,
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
        config = self._get_campaign_character_config(campaign_slug)
        if not config.characters_dir.exists():
            return []

        records: list[CharacterRecord] = []
        for definition_path in sorted(config.characters_dir.glob("*/definition.yaml")):
            character_slug = definition_path.parent.name
            if self._is_reconciliation_protected(campaign_slug, character_slug):
                continue
            record = self._load_character(
                campaign_slug,
                character_slug,
                allow_reconciliation=False,
                initialize_missing_state=True,
                campaign_config=config,
            )
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
        campaign_config: CampaignCharacterConfig | None = None,
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
        config = (
            self._get_campaign_character_config(campaign_slug)
            if campaign_config is None
            else campaign_config
        )
        try:
            definition_path, import_path = (
                resolve_character_definition_import_paths(
                    config.characters_dir,
                    character_slug,
                )
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

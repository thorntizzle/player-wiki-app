from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

import yaml

from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_definition_import_paths,
    validate_character_slug,
)
from .character_service import build_initial_state
from .character_store import CharacterStateStore
from .source_health import (
    SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES,
    SourceHealthConsumer,
    SourceHealthInventoryPage,
    SourceHealthReference,
    SourceHealthResolution,
    SourceHealthResolutionBatch,
    SourceHealthTarget,
)
from .system_policy import DND_5E_SYSTEM_CODE, normalize_system_code

SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES = 524_288
SOURCE_HEALTH_INACTIVE_CHARACTER_EPOCH = sha256(b"source-health-character-inactive-v1").hexdigest()
SESSION_READINESS_CHARACTER_LIMIT = 50


def _read_source_health_definition(path: Path, *, prior_bytes: int) -> bytes:
    """Read one already-contained definition within Source Health-only byte caps."""

    if path.stat().st_size > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES:
        raise ValueError("Character Source Health definition exceeds its file cap.")
    payload = path.read_bytes()
    if len(payload) > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES:
        raise ValueError("Character Source Health definition exceeds its file cap.")
    if prior_bytes + len(payload) > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES:
        raise ValueError("Character Source Health definitions exceed their request cap.")
    return payload


@dataclass(frozen=True, slots=True)
class CampaignCharacterConfig:
    campaign_slug: str
    system: str
    campaign_dir: Path
    characters_dir: Path
    source_root: Path
    source_glob: str


@dataclass(frozen=True, slots=True)
class SessionReadinessCharacterSummary:
    available_character_slugs: tuple[str, ...] = ()


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
    from .committed_publication import active, config
    if active():
        row, _ = config(campaign_slug)
        return _campaign_character_config_from_bytes(config_path, campaign_slug, row["primary_bytes"])
    if not config_path.exists():
        raise FileNotFoundError(f"Campaign config not found: {config_path}")
    return _campaign_character_config_from_bytes(
        config_path,
        campaign_slug,
        config_path.read_bytes(),
    )


def _source_health_systems_reference(
    raw_value: object,
    *,
    default_system: str,
) -> SourceHealthReference | None:
    if not isinstance(raw_value, dict):
        return None
    value = dict(raw_value)
    entry_key = str(value.get("entry_key") or "").strip()
    slug = str(value.get("slug") or "").strip()
    rule_key = str(value.get("rule_key") or "").strip()
    if not (entry_key or slug or rule_key):
        return None
    return SourceHealthReference(
        target_kind="systems",
        library_slug=str(value.get("library_slug") or default_system).strip(),
        entry_key=entry_key,
        slug=slug,
        rule_key=rule_key,
        source_id=str(value.get("source_id") or "").strip().upper(),
        system_code=normalize_system_code(value.get("system_code") or default_system),
        consumer_version=str(
            value.get("source_version") or value.get("version") or ""
        ).strip(),
        version_scheme=str(value.get("version_scheme") or "").strip(),
    )


def _source_health_page_reference(raw_value: object) -> SourceHealthReference | None:
    if isinstance(raw_value, dict):
        raw_value = (
            raw_value.get("page_ref")
            or raw_value.get("slug")
            or raw_value.get("page_slug")
        )
        if not isinstance(raw_value, str):
            return None
    page_ref = str(raw_value or "").strip().replace("\\", "/").strip("/")
    if not page_ref or any(part in {"", ".", ".."} for part in page_ref.split("/")):
        return None
    return SourceHealthReference(
        target_kind="campaign_page",
        target_id=page_ref,
    )


def _source_health_character_order_key(character_slug: str) -> tuple[str, str]:
    validated_slug = validate_character_slug(character_slug)
    return (validated_slug.casefold(), validated_slug)


def _source_health_character_order_digest(character_slug: str) -> str:
    normalized_slug, exact_slug = _source_health_character_order_key(character_slug)
    return sha256(f"{normalized_slug}\0{exact_slug}".encode("utf-8")).hexdigest()


def _source_health_character_continuation(offset: int, character_slug: str) -> str:
    return (
        f"character:v1:{offset}:"
        f"{_source_health_character_order_digest(character_slug)}"
    )


def _source_health_character_start(
    continuation: str,
    definition_paths: list[tuple[str, Path]],
    *,
    snapshot_digest: str = "",
) -> tuple[int, tuple[str, str] | None]:
    raw_continuation = str(continuation or "").strip()
    if not raw_continuation:
        return (0, None)
    parts = raw_continuation.split(":")
    version = "v2" if snapshot_digest else "v1"
    if (len(parts) != (5 if snapshot_digest else 4)
            or parts[:2] != ["character", version]
            or snapshot_digest and parts[4] != snapshot_digest):
        raise ValueError("Invalid Character Source Health continuation.")
    if not parts[2].isdigit() or str(int(parts[2])) != parts[2]:
        raise ValueError("Invalid Character Source Health continuation.")
    offset = int(parts[2])
    digest = parts[3]
    if (
        offset <= 0
        or offset > 1_000_000_000
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("Invalid Character Source Health continuation.")
    prior_keys = [
        _source_health_character_order_key(character_slug)
        for character_slug, _definition_path in definition_paths
        if digest == _source_health_character_order_digest(character_slug)
    ]
    if len(prior_keys) != 1:
        raise ValueError("Stale Character Source Health continuation.")
    if offset > len(definition_paths):
        raise ValueError("Stale Character Source Health continuation.")
    return (offset, prior_keys[0])


def _committed_character_cursor(offset: int, slug: str, digest: str) -> str:
    return f"character:v2:{offset}:{_source_health_character_order_digest(slug)}:{digest}"


def _source_health_exact_character_slug(
    reference: SourceHealthReference,
) -> str | None:
    if reference.target_kind != "character":
        return None
    locators = tuple(
        value
        for value in (
            str(reference.target_id or "").strip(),
            str(reference.slug or "").strip(),
            str(reference.entry_key or "").strip(),
        )
        if value
    )
    if not locators or len(set(locators)) != 1:
        return None
    try:
        return validate_character_slug(locators[0])
    except CharacterPathSafetyError:
        return None


def _source_health_character_target(
    campaign_slug: str,
    character_slug: str,
    *,
    system_code: str,
    enabled: bool = True,
    accessible: bool = True,
) -> SourceHealthTarget:
    return SourceHealthTarget(
        target_kind="character",
        canonical_identity=f"character:{campaign_slug}:{character_slug}",
        system_code=system_code,
        target_type="character",
        enabled=enabled,
        accessible=accessible,
        destination=(
            f"/campaigns/{campaign_slug}/characters/{character_slug}"
            if accessible
            else ""
        ),
    )


def _character_source_health_consumers(
    campaign_slug: str,
    character_slug: str,
    system_code: str,
    definition: dict[str, Any],
) -> list[SourceHealthConsumer]:
    destination = f"/campaigns/{campaign_slug}/characters/{character_slug}"
    rows: list[SourceHealthConsumer] = []

    def add_systems(path: str, value: object, accepted_types: tuple[str, ...]) -> None:
        reference = _source_health_systems_reference(
            value,
            default_system=system_code,
        )
        if reference is None:
            return
        rows.append(
            SourceHealthConsumer(
                consumer_type="character",
                consumer_key=f"{character_slug}:{path}",
                surface="Character",
                reference=reference,
                accepted_target_types=accepted_types,
                destination=destination,
            )
        )

    def add_page(path: str, value: object) -> None:
        reference = _source_health_page_reference(value)
        if reference is None:
            return
        rows.append(
            SourceHealthConsumer(
                consumer_type="character",
                consumer_key=f"{character_slug}:{path}",
                surface="Character",
                reference=reference,
                destination=destination,
            )
        )

    profile = dict(definition.get("profile") or {})
    class_rows = [row for row in list(profile.get("classes") or []) if isinstance(row, dict)]
    if class_rows:
        for index, class_row in enumerate(class_rows):
            add_systems(
                f"profile.classes[{index}].systems_ref",
                class_row.get("systems_ref") or class_row.get("class_ref"),
                ("class",),
            )
            add_systems(
                f"profile.classes[{index}].subclass_ref",
                class_row.get("subclass_ref"),
                ("subclass",),
            )
    else:
        add_systems("profile.class_ref", profile.get("class_ref"), ("class",))
        add_systems("profile.subclass_ref", profile.get("subclass_ref"), ("subclass",))
    add_systems("profile.species_ref", profile.get("species_ref"), ("race", "species"))
    add_systems("profile.background_ref", profile.get("background_ref"), ("background",))
    add_page("profile.species_page_ref", profile.get("species_page_ref"))
    add_page("profile.background_page_ref", profile.get("background_page_ref"))

    for index, feature in enumerate(list(definition.get("features") or [])):
        if not isinstance(feature, dict):
            continue
        add_systems(
            f"features[{index}].systems_ref",
            feature.get("systems_ref"),
            ("classfeature", "subclassfeature", "optionalfeature", "feat", "feature"),
        )
        add_page(f"features[{index}].page_ref", feature.get("page_ref"))

    spellcasting = dict(definition.get("spellcasting") or {})
    for index, spell in enumerate(list(spellcasting.get("spells") or [])):
        if not isinstance(spell, dict):
            continue
        add_systems(
            f"spellcasting.spells[{index}].systems_ref",
            spell.get("systems_ref"),
            ("spell",),
        )
        add_page(f"spellcasting.spells[{index}].page_ref", spell.get("page_ref"))

    for index, item in enumerate(list(definition.get("equipment_catalog") or [])):
        if not isinstance(item, dict):
            continue
        add_systems(
            f"equipment_catalog[{index}].systems_ref",
            item.get("systems_ref"),
            ("item",),
        )
        add_page(f"equipment_catalog[{index}].page_ref", item.get("page_ref"))

    xianxia = dict(definition.get("xianxia") or {})
    for collection_name, accepted_types in (
        ("martial_arts", ("martial_art",)),
        ("generic_techniques", ("generic_technique", "technique", "maneuver")),
    ):
        for index, record in enumerate(list(xianxia.get(collection_name) or [])):
            if isinstance(record, dict):
                add_systems(
                    f"xianxia.{collection_name}[{index}].systems_ref",
                    record.get("systems_ref"),
                    accepted_types,
                )
    equipment = dict(xianxia.get("equipment") or {})
    for collection_name in ("necessary_weapons", "necessary_tools"):
        for index, record in enumerate(list(equipment.get(collection_name) or [])):
            if isinstance(record, dict):
                add_systems(
                    f"xianxia.equipment.{collection_name}[{index}].systems_ref",
                    record.get("systems_ref"),
                    ("equipment", "item", "weapon", "tool", "armor"),
                )

    return rows


class CharacterRepository:
    def __init__(self, campaigns_dir: Path, state_store: CharacterStateStore) -> None:
        self.campaigns_dir = campaigns_dir
        self.state_store = state_store
        self._character_payload_cache: dict[tuple[str, str], _CharacterPayloadCacheRecord] = {}
        self._campaign_config_cache: dict[
            str,
            _CampaignCharacterConfigCacheRecord,
        ] = {}

    @contextmanager
    def _committed_character_snapshot(self, campaign_slug: str):
        """Bind config, pointer membership and exact pairs to one SQLite read view."""
        from .committed_publication import CommittedSourceConflict, active, config
        from .db import get_db

        connection = get_db()
        owned = not connection.in_transaction
        if owned:
            connection.execute("BEGIN")
        try:
            if not active(connection):
                raise CommittedSourceConflict("Committed Character proof needs repair.")
            config_row, settings = config(campaign_slug, connection=connection)
            rows = connection.execute(
                "SELECT object_ref, revision FROM committed_source_current "
                "WHERE campaign_slug=? AND object_kind='character'",
                (campaign_slug,),
            ).fetchall()
            pointers = {}
            for pointer in rows:
                slug = pointer["object_ref"]
                try:
                    validate_character_slug(slug)
                except CharacterPathSafetyError as exc:
                    raise CommittedSourceConflict("Committed Character proof needs repair.") from exc
                pointers[slug] = int(pointer["revision"])
            yield connection, config_row, settings, pointers
        finally:
            if owned:
                connection.rollback()

    @staticmethod
    def _committed_definition(campaign_slug, slug, source, settings):
        from .committed_publication import CommittedSourceConflict

        try:
            definition = yaml.safe_load(source["primary_bytes"].decode("utf-8"))
            if (not isinstance(definition, dict)
                    or definition.get("campaign_slug") != campaign_slug
                    or definition.get("character_slug") != slug
                    or normalize_system_code(definition.get("system"))
                    != normalize_system_code(settings.get("system"))):
                raise ValueError("Invalid Character definition identity.")
            return definition
        except (UnicodeError, yaml.YAMLError, ValueError, TypeError) as exc:
            raise CommittedSourceConflict("Committed Character proof needs repair.") from exc

    @staticmethod
    def _committed_import(campaign_slug, slug, source):
        from .committed_publication import CommittedSourceConflict

        try:
            imported = yaml.safe_load(source["secondary_bytes"].decode("utf-8"))
            if (not isinstance(imported, dict)
                    or imported.get("campaign_slug") != campaign_slug
                    or imported.get("character_slug") != slug):
                raise ValueError("Invalid Character import identity.")
            return imported
        except (UnicodeError, yaml.YAMLError, ValueError, TypeError) as exc:
            raise CommittedSourceConflict("Committed Character proof needs repair.") from exc

    @staticmethod
    def _committed_source(campaign_slug, slug, revision, connection):
        from .committed_character_publication import exact_character
        from .committed_publication import CommittedSourceConflict

        source = exact_character(campaign_slug, slug, connection=connection,
                                 allow_tombstone=True)
        if source is None or source["revision"] != revision:
            raise CommittedSourceConflict("Committed Character proof needs repair.")
        return source

    @staticmethod
    def _committed_inventory_digest(config_row, pointers, connection, campaign_slug):
        proofs = connection.execute(
            "SELECT c.object_ref, c.revision, a.status, a.revision, "
            "g.primary_sha256, g.secondary_sha256, g.tombstone "
            "FROM committed_source_current c "
            "LEFT JOIN committed_source_admission a ON a.campaign_slug=c.campaign_slug "
            "AND a.object_kind=c.object_kind AND a.object_ref=c.object_ref "
            "LEFT JOIN committed_source_generations g ON g.campaign_slug=c.campaign_slug "
            "AND g.object_kind=c.object_kind AND g.object_ref=c.object_ref "
            "AND g.revision=c.revision "
            "WHERE c.campaign_slug=? AND c.object_kind='character'",
            (campaign_slug,),
        ).fetchall()
        if len(proofs) != len(pointers):
            raise ValueError("Committed Character inventory changed; repair required.")
        digest = sha256(repr((
            config_row["revision"], sorted(tuple(row) for row in proofs),
        )).encode("utf-8"))
        digest.update(b"\0character-journals-v1")
        try:
            for journal_type, query in (
                (
                    "reconciliation",
                    "SELECT character_slug, operation_id, state "
                    "FROM character_reconciliation_operations WHERE campaign_slug=? "
                    "AND state IN ('prepared','repository_pending','conflict') "
                    "ORDER BY character_slug, operation_id, state",
                ),
                (
                    "deletion",
                    "SELECT character_slug, operation_id, state "
                    "FROM character_deletion_operations WHERE campaign_slug=? "
                    "AND state IN ('prepared','repository_pending','conflict') "
                    "ORDER BY character_slug, operation_id, state",
                ),
                (
                    "publication",
                    "SELECT object_ref, operation_id, state "
                    "FROM committed_source_publications WHERE campaign_slug=? "
                    "AND object_kind='character' AND state IN ('prepared','conflict') "
                    "ORDER BY object_ref, operation_id, state",
                ),
            ):
                for slug, operation_id, state in connection.execute(query, (campaign_slug,)):
                    validate_character_slug(slug)
                    if (len(slug.encode("utf-8")) > 255
                            or not isinstance(operation_id, str)
                            or len(operation_id) != 32
                            or any(char not in "0123456789abcdef" for char in operation_id)
                            or state not in {"prepared", "repository_pending", "conflict"}
                            or (journal_type == "publication" and state == "repository_pending")):
                        raise ValueError("Invalid Character journal identity.")
                    evidence = repr((journal_type, slug, operation_id, state)).encode("utf-8")
                    digest.update(len(evidence).to_bytes(4, "big"))
                    digest.update(evidence)
        except (sqlite3.Error, CharacterPathSafetyError, TypeError, ValueError, UnicodeError):
            raise ValueError("Committed Character inventory needs repair.") from None
        return digest.hexdigest()

    def source_health_inventory_epoch(self, campaign_slug: str) -> str:
        """Return only the Character inventory metadata identity in one read view."""
        from .committed_publication import active
        from .db import get_db

        connection = get_db()
        owned = not connection.in_transaction
        if owned:
            connection.execute("BEGIN")
        try:
            if not active(connection):
                return SOURCE_HEALTH_INACTIVE_CHARACTER_EPOCH
            with self._committed_character_snapshot(campaign_slug) as (
                snapshot, config_row, _settings, pointers,
            ):
                return self._committed_inventory_digest(
                    config_row, pointers, snapshot, campaign_slug,
                )
        finally:
            if owned:
                connection.rollback()

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
        from .committed_publication import active
        if active():
            return load_campaign_character_config(self.campaigns_dir, campaign_slug)
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
        from .committed_publication import active, CommittedSourceConflict
        if active():
            with self._committed_character_snapshot(campaign_slug) as (connection, _, settings, pointers):
                records = []
                for slug in sorted(pointers):
                    source = self._committed_source(campaign_slug, slug, pointers[slug], connection)
                    if source["tombstone"]:
                        continue
                    self._committed_definition(campaign_slug, slug, source, settings)
                    record = self._load_character(
                        campaign_slug, slug, allow_reconciliation=False,
                        initialize_missing_state=False,
                    )
                    if record is None:
                        raise CommittedSourceConflict("Committed Character proof needs repair.")
                    records.append(record)
                return records
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

    def summarize_session_readiness_characters(
        self,
        campaign_slug: str,
        *,
        limit: int = SESSION_READINESS_CHARACTER_LIMIT,
        initialize_missing_state: bool = False,
    ) -> SessionReadinessCharacterSummary:
        """Return a bounded active-definition roster without entering Character state."""

        if initialize_missing_state:
            raise ValueError("Session readiness cannot initialize Character state.")
        parsed_limit = int(limit)
        if parsed_limit < 1 or parsed_limit > SESSION_READINESS_CHARACTER_LIMIT:
            raise ValueError("Session readiness Character limit is invalid.")

        from .committed_publication import active
        if active():
            with self._committed_character_snapshot(campaign_slug) as (connection, _, settings, pointers):
                if len(pointers) > parsed_limit:
                    raise ValueError("Session readiness Character definitions exceed their cap.")
                available_slugs = []
                definition_bytes = 0
                for slug in sorted(pointers):
                    source = self._committed_source(campaign_slug, slug, pointers[slug], connection)
                    if source["tombstone"]:
                        continue
                    payload = source["primary_bytes"]
                    if (len(payload) > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES
                            or definition_bytes + len(payload) > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES):
                        raise ValueError("Session readiness Character definitions exceed their byte cap.")
                    definition_bytes += len(payload)
                    definition = self._committed_definition(campaign_slug, slug, source, settings)
                    if definition.get("status") == "active":
                        available_slugs.append(slug)
                return SessionReadinessCharacterSummary(tuple(available_slugs))

        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        if not config.characters_dir.exists():
            return SessionReadinessCharacterSummary()

        discovered_paths = sorted(config.characters_dir.glob("*/definition.yaml"))
        if len(discovered_paths) > parsed_limit:
            raise ValueError("Session readiness Character definitions exceed their cap.")

        available_slugs: list[str] = []
        definition_bytes = 0
        for discovered_path in discovered_paths:
            character_slug = discovered_path.parent.name
            validate_character_slug(character_slug)
            definition_path, import_path = resolve_character_definition_import_paths(
                config.characters_dir,
                character_slug,
            )
            if not definition_path.is_file() or not import_path.is_file():
                raise ValueError("Session readiness Character files are incomplete.")
            payload_bytes = _read_source_health_definition(
                definition_path,
                prior_bytes=definition_bytes,
            )
            definition_bytes += len(payload_bytes)
            try:
                raw_definition = yaml.safe_load(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, yaml.YAMLError) as exc:
                raise ValueError("Invalid Character definition.") from exc
            if not isinstance(raw_definition, dict):
                raise ValueError("Invalid Character definition.")
            if (
                str(raw_definition.get("campaign_slug") or "").strip()
                != campaign_slug
                or str(raw_definition.get("character_slug") or "").strip()
                != character_slug
            ):
                raise ValueError("Invalid Character definition ownership.")
            if str(raw_definition.get("status") or "").strip() == "active":
                available_slugs.append(character_slug)

        return SessionReadinessCharacterSummary(
            available_character_slugs=tuple(available_slugs),
        )

    def list_source_health_consumers(
        self,
        campaign_slug: str,
        *,
        continuation: str = "",
        limit: int = 50,
    ) -> SourceHealthInventoryPage:
        """Read one stable page of definitions without imports, state, derivation, or caches."""

        page_limit = min(max(int(limit), 1), 50)
        from .committed_publication import active
        if active():
            with self._committed_character_snapshot(campaign_slug) as (connection, config_row, settings, pointers):
                ordered = sorted(pointers, key=_source_health_character_order_key)
                digest = self._committed_inventory_digest(config_row, pointers, connection, campaign_slug)
                paths = [(slug, Path()) for slug in ordered]
                offset, prior_key = _source_health_character_start(
                    continuation, paths, snapshot_digest=digest,
                )
                if prior_key is not None and (
                    offset > len(ordered)
                    or _source_health_character_order_key(ordered[offset - 1]) != prior_key
                ):
                    raise ValueError("Stale Character Source Health continuation.")
                selected = ordered[offset:offset + page_limit]
                consumers = []
                targets = []
                definitions = {}
                byte_count = 0
                file_count = 0
                for slug in selected:
                    source = self._committed_source(campaign_slug, slug, pointers[slug], connection)
                    if source["tombstone"]:
                        continue
                    payload = source["primary_bytes"]
                    if (len(payload) > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES
                            or byte_count + len(payload) > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES):
                        raise ValueError("Character Source Health definitions exceed their byte cap.")
                    byte_count += len(payload)
                    file_count += 1
                    definition = self._committed_definition(campaign_slug, slug, source, settings)
                    status = str(definition.get("status") or "").strip()
                    targets.append(_source_health_character_target(
                        campaign_slug, slug, system_code=normalize_system_code(definition.get("system")),
                        enabled=status == "active",
                    ))
                    if status == "active":
                        definitions[slug] = dict(definition)
                        consumers.extend(_character_source_health_consumers(
                            campaign_slug, slug, normalize_system_code(definition.get("system")), definition,
                        ))
                next_offset = offset + len(selected)
                return SourceHealthInventoryPage(
                    consumers=tuple(consumers), targets=tuple(targets),
                    continuation=(
                        _committed_character_cursor(next_offset, selected[-1], digest)
                        if next_offset < len(ordered) and selected else ""
                    ),
                    definition_file_count=file_count, definition_bytes=byte_count,
                    character_definitions=definitions,
                    character_epoch=digest,
                )
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        if not config.characters_dir.exists():
            return SourceHealthInventoryPage(
                character_epoch=SOURCE_HEALTH_INACTIVE_CHARACTER_EPOCH,
            )

        definition_paths: list[tuple[str, Path]] = []
        for discovered_path in config.characters_dir.glob("*/definition.yaml"):
            character_slug = discovered_path.parent.name
            try:
                validate_character_slug(character_slug)
            except CharacterPathSafetyError:
                continue
            definition_paths.append((character_slug, discovered_path))
        definition_paths.sort(key=lambda item: _source_health_character_order_key(item[0]))
        cursor_offset, prior_order_key = _source_health_character_start(
            continuation,
            definition_paths,
        )
        remaining_paths = [
            item
            for item in definition_paths
            if prior_order_key is None
            or _source_health_character_order_key(item[0]) > prior_order_key
        ]
        selected = remaining_paths[: page_limit + 1]
        has_more = len(selected) > page_limit
        selected = selected[:page_limit]

        consumers: list[SourceHealthConsumer] = []
        targets: list[SourceHealthTarget] = []
        character_definitions: dict[str, dict[str, Any]] = {}
        definition_file_count = 0
        definition_bytes = 0
        for character_slug, _discovered_path in selected:
            try:
                definition_path, _import_path = (
                    resolve_character_definition_import_paths(
                        config.characters_dir,
                        character_slug,
                    )
                )
            except CharacterPathSafetyError:
                targets.append(
                    _source_health_character_target(
                        campaign_slug,
                        character_slug,
                        system_code=config.system,
                        accessible=False,
                    )
                )
                continue
            try:
                payload_bytes = _read_source_health_definition(
                    definition_path,
                    prior_bytes=definition_bytes,
                )
            except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
                continue
            except OSError:
                targets.append(
                    _source_health_character_target(
                        campaign_slug,
                        character_slug,
                        system_code=config.system,
                        accessible=False,
                    )
                )
                continue
            definition_file_count += 1
            definition_bytes += len(payload_bytes)
            try:
                raw_definition = yaml.safe_load(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, yaml.YAMLError) as exc:
                raise ValueError("Invalid Character definition.") from exc
            if not isinstance(raw_definition, dict):
                raise ValueError("Invalid Character definition.")
            if (
                str(raw_definition.get("campaign_slug") or "").strip()
                != campaign_slug
                or str(raw_definition.get("character_slug") or "").strip()
                != character_slug
            ):
                targets.append(
                    _source_health_character_target(
                        campaign_slug,
                        character_slug,
                        system_code=config.system,
                        accessible=False,
                    )
                )
                continue
            definition_system = (
                normalize_system_code(raw_definition.get("system") or config.system)
                or config.system
            )
            status = str(raw_definition.get("status") or "").strip()
            targets.append(
                _source_health_character_target(
                    campaign_slug,
                    character_slug,
                    system_code=definition_system,
                    enabled=status == "active",
                )
            )
            if status != "active":
                continue
            character_definitions[character_slug] = dict(raw_definition)
            consumers.extend(
                _character_source_health_consumers(
                    campaign_slug,
                    character_slug,
                    definition_system,
                    raw_definition,
                )
            )

        return SourceHealthInventoryPage(
            consumers=tuple(consumers),
            targets=tuple(targets),
            continuation=(
                _source_health_character_continuation(
                    cursor_offset + len(selected),
                    selected[-1][0],
                )
                if has_more and selected
                else ""
            ),
            definition_file_count=definition_file_count,
            definition_bytes=definition_bytes,
            character_definitions=character_definitions,
            character_epoch=SOURCE_HEALTH_INACTIVE_CHARACTER_EPOCH,
        )

    def resolve_source_health_character_targets(
        self,
        campaign_slug: str,
        references: tuple[SourceHealthReference, ...],
    ) -> SourceHealthResolutionBatch:
        """Resolve a bounded exact Character subset without state, imports, or caches."""

        unique_references = tuple(dict.fromkeys(tuple(references or ())))
        resolutions: dict[SourceHealthReference, SourceHealthResolution] = {
            reference: SourceHealthResolution() for reference in unique_references
        }
        references_by_slug: dict[str, list[SourceHealthReference]] = {}
        for reference in unique_references:
            character_slug = _source_health_exact_character_slug(reference)
            if character_slug is not None:
                references_by_slug.setdefault(character_slug, []).append(reference)
        if len(references_by_slug) > 50:
            raise ValueError("Character Source Health exact resolution is capped at 50 refs.")
        if not references_by_slug:
            return SourceHealthResolutionBatch(resolutions=resolutions)

        from .committed_publication import active
        if active():
            with self._committed_character_snapshot(campaign_slug) as (connection, _, settings, pointers):
                count = 0
                byte_count = 0
                definitions = {}
                for slug, matching in references_by_slug.items():
                    resolution = SourceHealthResolution()
                    if slug in pointers:
                        source = self._committed_source(campaign_slug, slug, pointers[slug], connection)
                        if not source["tombstone"]:
                            payload = source["primary_bytes"]
                            if (len(payload) > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES
                                    or byte_count + len(payload) > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES):
                                raise ValueError("Character Source Health definitions exceed their byte cap.")
                            byte_count += len(payload)
                            count += 1
                            definition = self._committed_definition(campaign_slug, slug, source, settings)
                            status = str(definition.get("status") or "").strip()
                            resolution = SourceHealthResolution(targets=(
                                _source_health_character_target(
                                    campaign_slug, slug,
                                    system_code=normalize_system_code(definition.get("system")),
                                    enabled=status == "active",
                                ),
                            ))
                            if status == "active":
                                definitions[slug] = dict(definition)
                    for reference in matching:
                        resolutions[reference] = resolution
                return SourceHealthResolutionBatch(
                    resolutions=resolutions, definition_file_count=count,
                    definition_bytes=byte_count, character_definitions=definitions,
                )

        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        definition_file_count = 0
        definition_bytes = 0
        definition_payloads: dict[str, dict[str, Any]] = {}
        for character_slug, matching_references in references_by_slug.items():
            try:
                definition_path, import_path = (
                    resolve_character_definition_import_paths(
                        config.characters_dir,
                        character_slug,
                    )
                )
            except CharacterPathSafetyError:
                resolution = SourceHealthResolution(
                    targets=(
                        _source_health_character_target(
                            campaign_slug,
                            character_slug,
                            system_code=config.system,
                            accessible=False,
                        ),
                    ),
                    contains_inaccessible=True,
                )
            else:
                try:
                    payload_bytes = _read_source_health_definition(
                        definition_path,
                        prior_bytes=definition_bytes,
                    )
                except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
                    resolution = SourceHealthResolution()
                except OSError:
                    resolution = SourceHealthResolution(
                        targets=(
                            _source_health_character_target(
                                campaign_slug,
                                character_slug,
                                system_code=config.system,
                                accessible=False,
                            ),
                        ),
                        contains_inaccessible=True,
                    )
                else:
                    definition_file_count += 1
                    definition_bytes += len(payload_bytes)
                    try:
                        raw_definition = yaml.safe_load(payload_bytes.decode("utf-8"))
                    except (UnicodeDecodeError, yaml.YAMLError) as exc:
                        raise ValueError("Invalid Character definition.") from exc
                    if not isinstance(raw_definition, dict):
                        raise ValueError("Invalid Character definition.")
                    definition_system = (
                        normalize_system_code(
                            raw_definition.get("system") or config.system
                        )
                        or config.system
                    )
                    identity_matches = (
                        str(raw_definition.get("campaign_slug") or "").strip()
                        == campaign_slug
                        and str(raw_definition.get("character_slug") or "").strip()
                        == character_slug
                    )
                    if not identity_matches:
                        resolution = SourceHealthResolution(
                            targets=(
                                _source_health_character_target(
                                    campaign_slug,
                                    character_slug,
                                    system_code=definition_system,
                                    accessible=False,
                                ),
                            ),
                            contains_inaccessible=True,
                        )
                    else:
                        status = str(raw_definition.get("status") or "").strip()
                        resolution = SourceHealthResolution(
                            targets=(
                                _source_health_character_target(
                                    campaign_slug,
                                    character_slug,
                                    system_code=definition_system,
                                    enabled=status == "active",
                                ),
                            )
                        )
                        if status == "active":
                            definition_payloads[character_slug] = dict(raw_definition)
            for reference in matching_references:
                resolutions[reference] = resolution

        return SourceHealthResolutionBatch(
            resolutions=resolutions,
            definition_file_count=definition_file_count,
            definition_bytes=definition_bytes,
            character_definitions=definition_payloads,
        )

    def overlay_source_health_character_fingerprints(
        self,
        campaign_slug: str,
        references: tuple[SourceHealthReference, ...],
        resolutions: Mapping[SourceHealthReference, SourceHealthResolution],
        character_definitions: Mapping[str, Mapping[str, object]],
        prior_definition_bytes: int,
        *,
        target_version_adapter: Callable[[CharacterRecord], str],
    ) -> SourceHealthResolutionBatch:
        """Overlay eligible Character hashes with one state query and no cache use."""

        if not callable(target_version_adapter):
            raise ValueError("Invalid Character combat-seed adapter.")
        if (
            type(prior_definition_bytes) is not int
            or not 0
            <= prior_definition_bytes
            <= SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
        ):
            raise ValueError("Invalid Character definition byte budget.")
        overlaid = dict(resolutions)
        refs_by_slug: dict[str, list[SourceHealthReference]] = {}
        for reference in tuple(dict.fromkeys(references)):
            character_slug = _source_health_exact_character_slug(reference)
            if character_slug is None:
                raise ValueError("Invalid Character fingerprint reference.")
            resolution = overlaid.get(reference, SourceHealthResolution())
            targets = {
                (target.target_kind, target.canonical_identity): target
                for target in tuple(resolution.targets or ())
            }
            if resolution.ambiguous or len(targets) != 1:
                continue
            target = next(iter(targets.values()))
            if (
                resolution.contains_inaccessible
                or not target.accessible
                or not target.enabled
                or target.review_blocked
                or target.wrong_system
                or target.target_type != "character"
                or (
                    reference.system_code
                    and target.system_code
                    and reference.system_code != target.system_code
                )
            ):
                continue
            refs_by_slug.setdefault(character_slug, []).append(reference)
        if len(refs_by_slug) > 50:
            raise ValueError("Character fingerprint batch exceeds its cap.")

        from .committed_publication import active, CommittedSourceConflict
        if active():
            with self._committed_character_snapshot(campaign_slug) as (connection, _, settings, pointers):
                protected = self.state_store.list_reconciliation_protected_slugs(
                    campaign_slug, tuple(refs_by_slug),
                )
                import_count = 0
                import_bytes = 0
                for slug, matching in refs_by_slug.items():
                    if slug not in pointers:
                        raise CommittedSourceConflict("Committed Character proof needs repair.")
                    source = self._committed_source(campaign_slug, slug, pointers[slug], connection)
                    if source["tombstone"]:
                        raise CommittedSourceConflict("Committed Character proof needs repair.")
                    definition = self._committed_definition(campaign_slug, slug, source, settings)
                    if (definition != character_definitions.get(slug)
                            or definition.get("status") != "active"):
                        raise CommittedSourceConflict("Committed Character snapshot changed; repair required.")
                    if slug in protected:
                        for reference in matching:
                            ordinary = overlaid[reference]
                            overlaid[reference] = replace(
                                ordinary,
                                targets=tuple(replace(target, accessible=False, destination="")
                                              for target in ordinary.targets),
                                contains_inaccessible=True,
                            )
                        continue
                    payload = source["secondary_bytes"]
                    if (len(payload) > SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES
                            or prior_definition_bytes + import_bytes + len(payload)
                            > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES):
                        raise ValueError("Character Source Health imports exceed their byte cap.")
                    import_count += 1
                    import_bytes += len(payload)
                    imported = self._committed_import(campaign_slug, slug, source)
                    state = self.state_store.get_state(campaign_slug, slug)
                    if state is None:
                        raise CommittedSourceConflict("Committed Character state needs repair.")
                    record = CharacterRecord(
                        definition=CharacterDefinition.from_dict(dict(definition)),
                        import_metadata=CharacterImportMetadata.from_dict(imported),
                        state_record=state, committed_revision=int(source["revision"]),
                    )
                    version = str(target_version_adapter(record))
                    if len(version) != 64 or any(c not in "0123456789abcdef" for c in version):
                        raise ValueError("Invalid Character combat-seed fingerprint.")
                    for reference in matching:
                        ordinary = overlaid[reference]
                        overlaid[reference] = replace(
                            ordinary,
                            targets=tuple(replace(target, target_version=version,
                                                  version_scheme="combat-seed-v1-sha256")
                                          for target in ordinary.targets),
                        )
                return SourceHealthResolutionBatch(
                    resolutions=overlaid, import_file_count=import_count,
                    import_bytes=import_bytes,
                )

        protected_slugs = self.state_store.list_reconciliation_protected_slugs(
            campaign_slug,
            tuple(refs_by_slug),
        )
        ready_slugs: list[str] = []
        for character_slug, matching_references in refs_by_slug.items():
            raw_definition = character_definitions.get(character_slug)
            if raw_definition is None:
                raise ValueError("Character definition snapshot is unavailable.")
            if character_slug in protected_slugs:
                for reference in matching_references:
                    ordinary = overlaid[reference]
                    overlaid[reference] = replace(
                        ordinary,
                        targets=tuple(
                            replace(target, accessible=False, destination="")
                            for target in ordinary.targets
                        ),
                        contains_inaccessible=True,
                    )
                continue
            ready_slugs.append(character_slug)

        state_by_slug = self.state_store.list_states(
            campaign_slug,
            tuple(ready_slugs),
        ) if ready_slugs else {}
        import_file_count = 0
        import_bytes = 0
        config = load_campaign_character_config(self.campaigns_dir, campaign_slug)
        for character_slug in ready_slugs:
            matching_references = refs_by_slug[character_slug]
            state_record = state_by_slug.get(character_slug)
            if state_record is None:
                for reference in matching_references:
                    overlaid[reference] = SourceHealthResolution()
                continue
            try:
                _definition_path, import_path = resolve_character_definition_import_paths(
                    config.characters_dir,
                    character_slug,
                )
            except CharacterPathSafetyError:
                for reference in matching_references:
                    ordinary = overlaid[reference]
                    overlaid[reference] = replace(
                        ordinary,
                        targets=tuple(
                            replace(target, accessible=False, destination="")
                            for target in ordinary.targets
                        ),
                        contains_inaccessible=True,
                    )
                continue
            try:
                payload_bytes = _read_source_health_definition(
                    import_path,
                    prior_bytes=prior_definition_bytes + import_bytes,
                )
            except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
                for reference in matching_references:
                    overlaid[reference] = SourceHealthResolution()
                continue
            except OSError:
                for reference in matching_references:
                    ordinary = overlaid[reference]
                    overlaid[reference] = replace(
                        ordinary,
                        targets=tuple(
                            replace(target, accessible=False, destination="")
                            for target in ordinary.targets
                        ),
                        contains_inaccessible=True,
                    )
                continue
            import_file_count += 1
            import_bytes += len(payload_bytes)
            try:
                raw_import = yaml.safe_load(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, yaml.YAMLError) as exc:
                raise ValueError("Invalid Character import metadata.") from exc
            if not isinstance(raw_import, dict):
                raise ValueError("Invalid Character import metadata.")
            if (
                str(raw_import.get("campaign_slug") or "").strip() != campaign_slug
                or str(raw_import.get("character_slug") or "").strip()
                != character_slug
            ):
                for reference in matching_references:
                    overlaid[reference] = SourceHealthResolution()
                continue
            raw_definition = dict(character_definitions[character_slug])
            if (
                str(raw_definition.get("campaign_slug") or "").strip()
                != campaign_slug
                or str(raw_definition.get("character_slug") or "").strip()
                != character_slug
                or str(raw_definition.get("status") or "").strip() != "active"
            ):
                raise ValueError("Character definition snapshot changed.")
            raw_definition.setdefault("system", config.system)
            record = CharacterRecord(
                definition=CharacterDefinition.from_dict(raw_definition),
                import_metadata=CharacterImportMetadata.from_dict(raw_import),
                state_record=state_record,
            )
            source_version = str(target_version_adapter(record))
            if (
                len(source_version) != 64
                or any(character not in "0123456789abcdef" for character in source_version)
            ):
                raise ValueError("Invalid Character combat-seed fingerprint.")
            for reference in matching_references:
                ordinary = overlaid[reference]
                overlaid[reference] = replace(
                    ordinary,
                    targets=tuple(
                        replace(
                            target,
                            target_version=source_version,
                            version_scheme="combat-seed-v1-sha256",
                        )
                        for target in ordinary.targets
                    ),
                )

        return SourceHealthResolutionBatch(
            resolutions=overlaid,
            import_file_count=import_file_count,
            import_bytes=import_bytes,
        )

    def get_character(self, campaign_slug: str, character_slug: str) -> CharacterRecord | None:
        return self._load_character(
            campaign_slug,
            character_slug,
            allow_reconciliation=False,
            initialize_missing_state=True,
        )

    def get_combat_seed_character(
        self,
        campaign_slug: str,
        character_slug: str,
    ) -> CharacterRecord | None:
        """Load one active, complete character without initializing missing state."""
        record = self._load_character(
            campaign_slug,
            character_slug,
            allow_reconciliation=False,
            initialize_missing_state=False,
        )
        if record is None or not self.is_character_visible(record):
            return None
        return record

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
        from .committed_publication import active
        if active():
            from .committed_character_publication import load_for_write
            return load_for_write(self, campaign_slug, character_slug)
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
        if (state_record is None and initialize_missing_state
                and normalize_system_code(definition.system) != DND_5E_SYSTEM_CODE):
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

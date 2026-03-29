from __future__ import annotations

import json
import copy
import re
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from .repository import normalize_lookup, slugify
from .systems_service import SystemsService
from .systems_store import SystemsStore

INLINE_TAG_PATTERN = re.compile(r"\{@([^{}]+)\}")

SPELL_SCHOOL_LABELS = {
    "A": "Abjuration",
    "C": "Conjuration",
    "D": "Divination",
    "E": "Enchantment",
    "V": "Evocation",
    "I": "Illusion",
    "N": "Necromancy",
    "T": "Transmutation",
}

SIZE_LABELS = {
    "T": "Tiny",
    "S": "Small",
    "M": "Medium",
    "L": "Large",
    "H": "Huge",
    "G": "Gargantuan",
}

ABILITY_LABELS = {
    "str": "STR",
    "dex": "DEX",
    "con": "CON",
    "int": "INT",
    "wis": "WIS",
    "cha": "CHA",
}

ABILITY_NAME_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

ATTACK_TAG_LABELS = {
    "mw": "Melee Weapon Attack:",
    "rw": "Ranged Weapon Attack:",
    "mw,rw": "Melee or Ranged Weapon Attack:",
    "ms": "Melee Spell Attack:",
    "rs": "Ranged Spell Attack:",
    "ms,rs": "Melee or Ranged Spell Attack:",
}

ALIGNMENT_LABELS = {
    "L": "Lawful",
    "N": "Neutral",
    "C": "Chaotic",
    "G": "Good",
    "E": "Evil",
    "U": "Unaligned",
    "A": "Any Alignment",
}

SUBRACE_STANDALONE_TITLES = {
    ("drow", "elf"): "Drow",
    ("duergar", "dwarf"): "Duergar",
    ("eladrin", "elf"): "Eladrin",
    ("githyanki", "gith"): "Githyanki",
    ("githzerai", "gith"): "Githzerai",
    ("shadarkai", "elf"): "Shadar-kai",
}

SUBRACE_PREFIX_RACE_NAMES = {
    "aasimar",
    "dragonborn",
    "dwarf",
    "elf",
    "gnome",
    "halfling",
    "human",
    "tiefling",
}

PLAYER_SAFE_SOURCE_IDS = {"PHB", "XGE", "TCE", "EGW"}
PLAYER_SAFE_ENTRY_TYPES = {
    "action",
    "background",
    "class",
    "classfeature",
    "condition",
    "feat",
    "item",
    "optionalfeature",
    "race",
    "sense",
    "skill",
    "spell",
    "status",
    "subclass",
    "subclassfeature",
    "variantrule",
}
SUPPORTED_ENTRY_TYPES = (
    "action",
    "background",
    "class",
    "classfeature",
    "condition",
    "disease",
    "feat",
    "item",
    "monster",
    "optionalfeature",
    "race",
    "sense",
    "skill",
    "spell",
    "status",
    "subclass",
    "subclassfeature",
    "variantrule",
)

# The supported library catalog currently carries 2014 class sources plus the
# selected player-safe books. Legacy compatibility aliases that point at
# unsupported parent class sources should not import into the shared library.
UNSUPPORTED_CLASS_VARIANT_SOURCE_IDS = {"XPHB", "EFA"}
SUPPORTED_SUBCLASS_SOURCE_IDS = PLAYER_SAFE_SOURCE_IDS | {"DMG", "MM", "MTF", "VGM"}

EXCLUDED_MEDIA_KEYS = {
    "altArt",
    "foundryImg",
    "hasFluff",
    "hasFluffImages",
    "hasToken",
    "image",
    "images",
    "soundClip",
    "token",
    "tokenHref",
    "tokenUrl",
}


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    entry_type: str
    relative_path: str
    json_key: str
    split_by_source: bool = False

    def resolve_path(self, data_root: Path, source_id: str) -> Path:
        if self.split_by_source:
            return data_root / self.relative_path.format(source_slug=source_id.lower())
        return data_root / self.relative_path


@dataclass(slots=True)
class Dnd5eImportResult:
    source_id: str
    import_run_id: int
    import_version: str
    imported_count: int
    imported_by_type: dict[str, int]
    source_files: list[str]


DATASETS = (
    DatasetDefinition("spell", "data/spells/spells-{source_slug}.json", "spell", split_by_source=True),
    DatasetDefinition("monster", "data/bestiary/bestiary-{source_slug}.json", "monster", split_by_source=True),
    DatasetDefinition("action", "data/actions.json", "action"),
    DatasetDefinition("condition", "data/conditionsdiseases.json", "condition"),
    DatasetDefinition("disease", "data/conditionsdiseases.json", "disease"),
    DatasetDefinition("status", "data/conditionsdiseases.json", "status"),
    DatasetDefinition("background", "data/backgrounds.json", "background"),
    DatasetDefinition("feat", "data/feats.json", "feat"),
    DatasetDefinition("item", "data/items-base.json", "baseitem"),
    DatasetDefinition("item", "data/items.json", "item"),
    DatasetDefinition("optionalfeature", "data/optionalfeatures.json", "optionalfeature"),
    DatasetDefinition("race", "data/races.json", "race"),
    DatasetDefinition("sense", "data/senses.json", "sense"),
    DatasetDefinition("skill", "data/skills.json", "skill"),
    DatasetDefinition("variantrule", "data/variantrules.json", "variantrule"),
)

CLASS_DATASET_KEYS = {
    "class": "class",
    "classfeature": "classFeature",
    "subclass": "subclass",
    "subclassfeature": "subclassFeature",
}


class Dnd5eSystemsImporter:
    def __init__(
        self,
        *,
        store: SystemsStore,
        systems_service: SystemsService,
        data_root: Path,
        library_slug: str = "DND-5E",
    ) -> None:
        self.store = store
        self.systems_service = systems_service
        self.data_root = Path(data_root)
        self.library_slug = library_slug

    def import_sources(
        self,
        source_ids: list[str],
        *,
        entry_types: list[str] | None = None,
        started_by_user_id: int | None = None,
        import_version: str | None = None,
        source_path_label: str | None = None,
    ) -> list[Dnd5eImportResult]:
        results: list[Dnd5eImportResult] = []
        for source_id in source_ids:
            results.append(
                self.import_source(
                    source_id,
                    entry_types=entry_types,
                    started_by_user_id=started_by_user_id,
                    import_version=import_version,
                    source_path_label=source_path_label,
                )
            )
        return results

    def import_source(
        self,
        source_id: str,
        *,
        entry_types: list[str] | None = None,
        started_by_user_id: int | None = None,
        import_version: str | None = None,
        source_path_label: str | None = None,
    ) -> Dnd5eImportResult:
        normalized_source_id = source_id.strip().upper()
        if not normalized_source_id:
            raise ValueError("Choose a source ID to import.")
        if not self.data_root.exists():
            raise FileNotFoundError(f"DND 5E source data root not found: {self.data_root}")

        self.systems_service.ensure_builtin_library_seeded(self.library_slug)
        source_record = self.store.get_source(self.library_slug, normalized_source_id)
        if source_record is None:
            raise ValueError(f"Unsupported DND 5E source ID: {normalized_source_id}")

        selected_entry_types = self._normalize_entry_types(entry_types)
        effective_import_version = str(import_version or self.data_root.name).strip() or self.data_root.name
        effective_source_path = str(source_path_label or self.data_root).strip() or str(self.data_root)
        import_run = self.store.create_import_run(
            library_slug=self.library_slug,
            source_id=normalized_source_id,
            import_version=effective_import_version,
            source_path=effective_source_path,
            summary={"entry_types": selected_entry_types},
            started_by_user_id=started_by_user_id,
        )

        imported_by_type: Counter[str] = Counter()
        source_files: list[str] = []
        try:
            entries = self._load_entries_for_source(
                normalized_source_id,
                entry_types=selected_entry_types,
                source_files=source_files,
                imported_by_type=imported_by_type,
            )
            imported_count = self.store.replace_entries_for_source(
                self.library_slug,
                normalized_source_id,
                entries=entries,
                entry_types=selected_entry_types,
            )
            summary = {
                "entry_types": selected_entry_types,
                "imported_by_type": dict(imported_by_type),
                "imported_count": imported_count,
                "source_files": source_files,
            }
            self.store.complete_import_run(import_run.id, summary=summary)
            return Dnd5eImportResult(
                source_id=normalized_source_id,
                import_run_id=import_run.id,
                import_version=effective_import_version,
                imported_count=imported_count,
                imported_by_type=dict(imported_by_type),
                source_files=source_files,
            )
        except Exception as exc:
            self.store.fail_import_run(
                import_run.id,
                summary={
                    "entry_types": selected_entry_types,
                    "imported_by_type": dict(imported_by_type),
                    "source_files": source_files,
                    "error": str(exc),
                },
            )
            raise

    def _load_entries_for_source(
        self,
        source_id: str,
        *,
        entry_types: list[str],
        source_files: list[str],
        imported_by_type: Counter[str],
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        used_entry_keys: set[str] = set()
        used_slugs: set[str] = set()
        seen_source_files: set[str] = set()
        for dataset in DATASETS:
            if dataset.entry_type not in entry_types:
                continue
            path = dataset.resolve_path(self.data_root, source_id)
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            raw_entries = self._load_dataset_raw_entries(payload, dataset=dataset, source_id=source_id)
            if not isinstance(raw_entries, list):
                continue
            matching_entries = [
                raw_entry
                for raw_entry in raw_entries
                if isinstance(raw_entry, dict) and str(raw_entry.get("source", "")).upper() == source_id
            ]
            if not matching_entries:
                continue
            relative_source_path = str(path.relative_to(self.data_root)).replace("\\", "/")
            self._append_source_file(relative_source_path, source_files=source_files, seen_source_files=seen_source_files)
            for raw_entry in matching_entries:
                built_entry = self._build_entry(
                    dataset.entry_type,
                    raw_entry,
                    source_path=relative_source_path,
                    used_entry_keys=used_entry_keys,
                    used_slugs=used_slugs,
                )
                if built_entry is None:
                    continue
                entries.append(built_entry)
                imported_by_type[built_entry["entry_type"]] += 1
        self._load_class_folder_entries_for_source(
            source_id,
            entry_types=entry_types,
            source_files=source_files,
            seen_source_files=seen_source_files,
            used_entry_keys=used_entry_keys,
            used_slugs=used_slugs,
            entries=entries,
            imported_by_type=imported_by_type,
        )
        return entries

    def _load_dataset_raw_entries(
        self,
        payload: dict[str, Any],
        *,
        dataset: DatasetDefinition,
        source_id: str,
    ) -> list[dict[str, Any]]:
        if dataset.entry_type != "race":
            raw_entries = payload.get(dataset.json_key, [])
            return raw_entries if isinstance(raw_entries, list) else []
        return self._build_race_raw_entries(payload, source_id)

    def _build_race_raw_entries(self, payload: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
        race_rows = payload.get("race", [])
        subrace_rows = payload.get("subrace", [])
        if not isinstance(race_rows, list):
            race_rows = []
        if not isinstance(subrace_rows, list):
            subrace_rows = []

        raw_entries: list[dict[str, Any]] = [
            row
            for row in race_rows
            if isinstance(row, dict) and str(row.get("source", "")).upper() == source_id
        ]

        base_race_lookup = {
            (
                normalize_lookup(str(row.get("name", "") or "")),
                str(row.get("source", "")).upper(),
            ): row
            for row in race_rows
            if isinstance(row, dict) and str(row.get("name", "")).strip() and str(row.get("source", "")).strip()
        }
        for row in subrace_rows:
            if not isinstance(row, dict) or str(row.get("source", "")).upper() != source_id:
                continue
            built = self._build_subrace_as_race_entry(row, base_race_lookup)
            if built is not None:
                raw_entries.append(built)
        return raw_entries

    def _build_subrace_as_race_entry(
        self,
        raw_subrace: dict[str, Any],
        base_race_lookup: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        subrace_name = str(raw_subrace.get("name", "") or "").strip()
        race_name = str(raw_subrace.get("raceName", "") or "").strip()
        race_source = str(raw_subrace.get("raceSource", "") or raw_subrace.get("source", "")).upper()
        if not subrace_name or not race_name:
            return None

        title = self._build_subrace_race_title(subrace_name=subrace_name, race_name=race_name)
        if not title:
            return None

        base_race = base_race_lookup.get((normalize_lookup(race_name), race_source))
        if base_race is None:
            return None

        merged = copy.deepcopy(base_race)
        merged.update(copy.deepcopy(raw_subrace))
        merged["name"] = title
        merged["raceName"] = race_name
        merged["raceSource"] = race_source
        merged["subraceName"] = subrace_name
        merged["entries"] = self._merge_race_entries(base_race.get("entries"), raw_subrace.get("entries"))
        return merged

    def _build_subrace_race_title(self, *, subrace_name: str, race_name: str) -> str:
        normalized_subrace_name = normalize_lookup(subrace_name)
        normalized_race_name = normalize_lookup(race_name)
        if not normalized_subrace_name:
            return ""
        if normalized_subrace_name == "variant":
            return f"Variant {race_name}"
        if normalized_subrace_name == normalized_race_name:
            return race_name

        standalone_title = SUBRACE_STANDALONE_TITLES.get((normalized_subrace_name, normalized_race_name))
        if standalone_title:
            return standalone_title
        if normalized_race_name in SUBRACE_PREFIX_RACE_NAMES:
            return f"{subrace_name} {race_name}"
        return f"{race_name} ({subrace_name})"

    def _merge_race_entries(self, base_entries: Any, subrace_entries: Any) -> list[Any]:
        merged: list[Any] = copy.deepcopy(base_entries) if isinstance(base_entries, list) else []
        if not isinstance(subrace_entries, list):
            return merged
        for entry in subrace_entries:
            copied_entry = copy.deepcopy(entry)
            overwrite_target = ""
            if isinstance(copied_entry, dict):
                data = copied_entry.get("data")
                if isinstance(data, dict):
                    overwrite_target = str(data.get("overwrite", "") or "").strip()
            if overwrite_target:
                replaced = False
                for index, base_entry in enumerate(merged):
                    if isinstance(base_entry, dict) and str(base_entry.get("name", "") or "").strip() == overwrite_target:
                        merged[index] = copied_entry
                        replaced = True
                        break
                if replaced:
                    continue
            merged.append(copied_entry)
        return merged

    def _load_class_folder_entries_for_source(
        self,
        source_id: str,
        *,
        entry_types: list[str],
        source_files: list[str],
        seen_source_files: set[str],
        used_entry_keys: set[str],
        used_slugs: set[str],
        entries: list[dict[str, Any]],
        imported_by_type: Counter[str],
    ) -> None:
        requested_class_types = {
            entry_type: CLASS_DATASET_KEYS[entry_type]
            for entry_type in entry_types
            if entry_type in CLASS_DATASET_KEYS
        }
        if not requested_class_types:
            return

        class_dir = self.data_root / "data/class"
        index_path = class_dir / "index.json"
        if not index_path.exists():
            return
        with index_path.open(encoding="utf-8") as handle:
            index_payload = json.load(handle)
        if not isinstance(index_payload, dict):
            return

        loaded_any_file = False
        for relative_name in sorted(index_payload.values()):
            path = class_dir / str(relative_name)
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                continue
            relative_source_path = str(path.relative_to(self.data_root)).replace("\\", "/")
            file_loaded = False
            for entry_type, json_key in requested_class_types.items():
                raw_entries = payload.get(json_key, [])
                if not isinstance(raw_entries, list):
                    continue
                matching_entries = [
                    raw_entry
                    for raw_entry in raw_entries
                    if isinstance(raw_entry, dict) and str(raw_entry.get("source", "")).upper() == source_id
                ]
                if not matching_entries:
                    continue
                if not file_loaded:
                    self._append_source_file(
                        relative_source_path,
                        source_files=source_files,
                        seen_source_files=seen_source_files,
                    )
                    file_loaded = True
                    loaded_any_file = True
                for raw_entry in matching_entries:
                    built_entry = self._build_entry(
                        entry_type,
                        raw_entry,
                        source_path=relative_source_path,
                        used_entry_keys=used_entry_keys,
                        used_slugs=used_slugs,
                    )
                    if built_entry is None:
                        continue
                    entries.append(built_entry)
                    imported_by_type[built_entry["entry_type"]] += 1

        if loaded_any_file:
            self._append_source_file(
                str(index_path.relative_to(self.data_root)).replace("\\", "/"),
                source_files=source_files,
                seen_source_files=seen_source_files,
            )

    def _append_source_file(
        self,
        relative_source_path: str,
        *,
        source_files: list[str],
        seen_source_files: set[str],
    ) -> None:
        if relative_source_path in seen_source_files:
            return
        seen_source_files.add(relative_source_path)
        source_files.append(relative_source_path)

    def _build_entry(
        self,
        entry_type: str,
        raw_entry: dict[str, Any],
        *,
        source_path: str,
        used_entry_keys: set[str],
        used_slugs: set[str],
    ) -> dict[str, Any] | None:
        title = str(raw_entry.get("name", "")).strip()
        source_id = str(raw_entry.get("source", "")).upper()
        if not title or not source_id:
            return None
        if self._should_skip_entry(entry_type, raw_entry):
            return None

        metadata, body, rendered_html = self._build_entry_content(entry_type, raw_entry)
        identity_seed = self._build_entry_identity_seed(entry_type, raw_entry)
        entry_key = self._make_unique_identifier(
            f"{self.library_slug.lower()}|{entry_type}|{source_id.lower()}|{identity_seed}",
            used=used_entry_keys,
            page=raw_entry.get("page"),
        )
        slug = self._make_unique_identifier(
            f"{source_id.lower()}-{entry_type}-{identity_seed}",
            used=used_slugs,
            page=raw_entry.get("page"),
        )
        search_chunks = [
            title,
            entry_type,
            source_id,
            self._extract_text(metadata),
            self._extract_text(body),
        ]
        return {
            "entry_key": entry_key,
            "entry_type": entry_type,
            "slug": slug,
            "title": title,
            "source_page": str(raw_entry.get("page", "") or ""),
            "source_path": source_path,
            "search_text": " ".join(chunk for chunk in search_chunks if chunk).strip().lower(),
            "player_safe_default": self._is_player_safe_default(source_id, entry_type),
            "dm_heavy": self._is_dm_heavy(source_id, entry_type),
            "metadata": metadata,
            "body": body,
            "rendered_html": rendered_html,
        }

    def _should_skip_entry(self, entry_type: str, raw_entry: dict[str, Any]) -> bool:
        if entry_type in {"subclass", "subclassfeature"}:
            class_source = str(raw_entry.get("classSource", "") or "").upper()
            if class_source in UNSUPPORTED_CLASS_VARIANT_SOURCE_IDS:
                return True
        if entry_type == "subclassfeature":
            subclass_source = str(raw_entry.get("subclassSource", "") or "").upper()
            if subclass_source and subclass_source not in SUPPORTED_SUBCLASS_SOURCE_IDS:
                return True
        return False

    def _build_entry_content(
        self,
        entry_type: str,
        raw_entry: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        if entry_type == "class":
            return self._build_class_content(raw_entry)
        if entry_type == "subclass":
            return self._build_subclass_content(raw_entry)
        if entry_type == "spell":
            return self._build_spell_content(raw_entry)
        if entry_type == "monster":
            return self._build_monster_content(raw_entry)
        return self._build_generic_content(entry_type, raw_entry)

    def _build_class_content(self, raw_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        metadata = {
            "hit_die": self._clean_data(raw_entry.get("hd")),
            "proficiency": self._clean_data(raw_entry.get("proficiency")),
            "starting_proficiencies": self._clean_data(raw_entry.get("startingProficiencies")),
            "starting_equipment": self._clean_data(raw_entry.get("startingEquipment")),
            "multiclassing": self._clean_data(raw_entry.get("multiclassing")),
            "subclass_title": self._clean_data(raw_entry.get("subclassTitle")),
            "optionalfeature_progression": self._clean_data(raw_entry.get("optionalfeatureProgression")),
        }
        feature_progression = self._build_feature_progression_sections(raw_entry.get("classFeatures"))
        body = {
            "feature_progression": feature_progression,
            "starting_proficiencies": self._build_class_starting_proficiencies_section(raw_entry.get("startingProficiencies")),
            "starting_equipment": self._build_class_starting_equipment_section(raw_entry.get("startingEquipment")),
            "optionalfeature_progression": self._build_optionalfeature_progression_section(
                raw_entry.get("optionalfeatureProgression")
            ),
            "multiclassing": self._build_multiclassing_section(raw_entry.get("multiclassing")),
        }
        metadata_pairs = [
            ("Hit Die", self._format_hit_die(raw_entry.get("hd"))),
            ("Saving Throw Proficiencies", self._format_ability_code_list(raw_entry.get("proficiency"))),
            ("Subclass Type", self._format_compact_value(raw_entry.get("subclassTitle"))),
        ]
        body["rendered"] = {
            "summary_html": self._render_entry_html(metadata_pairs=metadata_pairs, sections=[]),
            "starting_proficiencies_html": self._render_entry_html(
                metadata_pairs=[],
                sections=[("Starting Proficiencies", body["starting_proficiencies"])],
            ),
            "starting_equipment_html": self._render_entry_html(
                metadata_pairs=[],
                sections=[("Starting Equipment", body["starting_equipment"])],
            ),
            "feature_progression_html": self._render_entry_html(
                metadata_pairs=[],
                sections=[("Class Features By Level", body["feature_progression"])],
            ),
            "optionalfeature_progression_html": self._render_entry_html(
                metadata_pairs=[],
                sections=[("Optional Feature Progression", body["optionalfeature_progression"])],
            ),
            "multiclassing_html": self._render_entry_html(
                metadata_pairs=[],
                sections=[("Multiclassing", body["multiclassing"])],
            ),
        }
        rendered_html = "\n".join(
            part
            for part in (
                body["rendered"]["summary_html"],
                body["rendered"]["starting_proficiencies_html"],
                body["rendered"]["starting_equipment_html"],
                body["rendered"]["feature_progression_html"],
                body["rendered"]["optionalfeature_progression_html"],
                body["rendered"]["multiclassing_html"],
            )
            if part
        )
        return metadata, body, rendered_html

    def _build_subclass_content(self, raw_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        metadata = {
            "class_name": self._clean_data(raw_entry.get("className")),
            "class_source": self._clean_data(raw_entry.get("classSource")),
            "optionalfeature_progression": self._clean_data(raw_entry.get("optionalfeatureProgression")),
        }
        body = {
            "feature_progression": self._build_feature_progression_sections(raw_entry.get("subclassFeatures")),
            "optionalfeature_progression": self._build_optionalfeature_progression_section(
                raw_entry.get("optionalfeatureProgression")
            ),
        }
        metadata_pairs = [
            ("Class", self._format_compact_value(raw_entry.get("className"))),
            ("Class Source", self._format_compact_value(raw_entry.get("classSource"))),
        ]
        sections = [
            ("Subclass Features By Level", body["feature_progression"]),
            ("Optional Feature Progression", body["optionalfeature_progression"]),
        ]
        rendered_html = self._render_entry_html(metadata_pairs=metadata_pairs, sections=sections)
        return metadata, body, rendered_html

    def _build_spell_content(self, raw_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        metadata = {
            "level": raw_entry.get("level"),
            "school": raw_entry.get("school"),
            "casting_time": self._clean_data(raw_entry.get("time")),
            "range": self._clean_data(raw_entry.get("range")),
            "components": self._clean_data(raw_entry.get("components")),
            "duration": self._clean_data(raw_entry.get("duration")),
            "classes": self._clean_data(raw_entry.get("classes")),
        }
        body = {
            "entries": self._clean_data(raw_entry.get("entries")),
            "entries_higher_level": self._clean_data(raw_entry.get("entriesHigherLevel")),
        }
        metadata_pairs = [
            ("Level", self._format_spell_level_school(raw_entry.get("level"), raw_entry.get("school"))),
            ("Casting Time", self._format_spell_time(raw_entry.get("time"))),
            ("Range", self._format_spell_range(raw_entry.get("range"))),
            ("Components", self._format_spell_components(raw_entry.get("components"))),
            ("Duration", self._format_spell_duration(raw_entry.get("duration"))),
            ("Classes", self._format_spell_classes(raw_entry.get("classes"))),
        ]
        sections = [("Spell Description", body["entries"])]
        if body["entries_higher_level"]:
            sections.append(("At Higher Levels", body["entries_higher_level"]))
        rendered_html = self._render_entry_html(metadata_pairs=metadata_pairs, sections=sections)
        return metadata, body, rendered_html

    def _build_monster_content(self, raw_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        metadata = {
            "size": self._clean_data(raw_entry.get("size")),
            "type": self._clean_data(raw_entry.get("type")),
            "alignment": self._clean_data(raw_entry.get("alignment")),
            "ac": self._clean_data(raw_entry.get("ac")),
            "hp": self._clean_data(raw_entry.get("hp")),
            "speed": self._clean_data(raw_entry.get("speed")),
            "abilities": {
                "str": raw_entry.get("str"),
                "dex": raw_entry.get("dex"),
                "con": raw_entry.get("con"),
                "int": raw_entry.get("int"),
                "wis": raw_entry.get("wis"),
                "cha": raw_entry.get("cha"),
            },
            "saving_throws": self._clean_data(raw_entry.get("save")),
            "skills": self._clean_data(raw_entry.get("skill")),
            "vulnerable": self._clean_data(raw_entry.get("vulnerable")),
            "resist": self._clean_data(raw_entry.get("resist")),
            "immune": self._clean_data(raw_entry.get("immune")),
            "condition_immune": self._clean_data(raw_entry.get("conditionImmune")),
            "senses": self._clean_data(raw_entry.get("senses")),
            "passive": raw_entry.get("passive"),
            "languages": self._clean_data(raw_entry.get("languages")),
            "cr": self._clean_data(raw_entry.get("cr")),
        }
        body = {
            "traits": self._clean_data(raw_entry.get("trait")),
            "actions": self._clean_data(raw_entry.get("action")),
            "bonus_actions": self._clean_data(raw_entry.get("bonus")),
            "reactions": self._clean_data(raw_entry.get("reaction")),
            "legendary_actions": self._clean_data(raw_entry.get("legendary")),
            "mythic_actions": self._clean_data(raw_entry.get("mythic")),
        }
        metadata_pairs = [
            ("Size", self._format_size_list(raw_entry.get("size"))),
            ("Creature Type", self._format_creature_type(raw_entry.get("type"))),
            ("Alignment", self._format_alignment(raw_entry.get("alignment"))),
            ("Armor Class", self._format_monster_ac(raw_entry.get("ac"))),
            ("Hit Points", self._format_monster_hp(raw_entry.get("hp"))),
            ("Speed", self._format_monster_speed(raw_entry.get("speed"))),
            ("Saving Throws", self._format_dict_bonus_list(raw_entry.get("save"))),
            ("Skills", self._format_dict_bonus_list(raw_entry.get("skill"))),
            ("Senses", self._format_monster_senses(raw_entry.get("senses"), raw_entry.get("passive"))),
            ("Languages", self._format_compact_value(raw_entry.get("languages"))),
            ("Challenge", self._format_monster_cr(raw_entry.get("cr"))),
        ]
        sections: list[tuple[str, Any]] = [("Ability Scores", metadata["abilities"])]
        if body["traits"]:
            sections.append(("Traits", body["traits"]))
        if body["actions"]:
            sections.append(("Actions", body["actions"]))
        if body["bonus_actions"]:
            sections.append(("Bonus Actions", body["bonus_actions"]))
        if body["reactions"]:
            sections.append(("Reactions", body["reactions"]))
        if body["legendary_actions"]:
            sections.append(("Legendary Actions", body["legendary_actions"]))
        if body["mythic_actions"]:
            sections.append(("Mythic Actions", body["mythic_actions"]))
        rendered_html = self._render_entry_html(metadata_pairs=metadata_pairs, sections=sections)
        return metadata, body, rendered_html

    def _build_generic_content(
        self,
        entry_type: str,
        raw_entry: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        metadata: dict[str, Any]
        metadata_pairs: list[tuple[str, str]]
        if entry_type == "item":
            metadata = {
                "type": self._clean_data(raw_entry.get("type")),
                "rarity": self._clean_data(raw_entry.get("rarity")),
                "attunement": self._clean_data(raw_entry.get("reqAttune")),
                "weight": raw_entry.get("weight"),
                "base_item": self._clean_data(raw_entry.get("baseItem")),
            }
            metadata_pairs = [
                ("Item Type", self._format_compact_value(raw_entry.get("type"))),
                ("Rarity", self._format_compact_value(raw_entry.get("rarity"))),
                ("Attunement", self._format_compact_value(raw_entry.get("reqAttune"))),
                ("Weight", self._format_weight(raw_entry.get("weight"))),
                ("Base Item", self._format_compact_value(raw_entry.get("baseItem"))),
            ]
        elif entry_type == "background":
            metadata = {
                "skill_proficiencies": self._clean_data(raw_entry.get("skillProficiencies")),
                "tool_proficiencies": self._clean_data(raw_entry.get("toolProficiencies")),
                "language_proficiencies": self._clean_data(raw_entry.get("languageProficiencies")),
                "starting_equipment": self._clean_data(raw_entry.get("startingEquipment")),
            }
            metadata_pairs = [
                ("Skill Proficiencies", self._format_compact_value(raw_entry.get("skillProficiencies"))),
                ("Tool Proficiencies", self._format_compact_value(raw_entry.get("toolProficiencies"))),
                ("Languages", self._format_compact_value(raw_entry.get("languageProficiencies"))),
            ]
        elif entry_type == "classfeature":
            metadata = {
                "class_name": self._clean_data(raw_entry.get("className")),
                "class_source": self._clean_data(raw_entry.get("classSource")),
                "level": raw_entry.get("level"),
            }
            metadata_pairs = [
                ("Class", self._format_compact_value(raw_entry.get("className"))),
                ("Class Source", self._format_compact_value(raw_entry.get("classSource"))),
                ("Level", self._format_compact_value(raw_entry.get("level"))),
            ]
        elif entry_type == "feat":
            metadata = {
                "prerequisite": self._clean_data(raw_entry.get("prerequisite")),
                "category": self._clean_data(raw_entry.get("category")),
                "ability": self._clean_data(raw_entry.get("ability")),
            }
            metadata_pairs = [
                ("Prerequisite", self._format_compact_value(raw_entry.get("prerequisite"))),
                ("Category", self._format_compact_value(raw_entry.get("category"))),
                ("Ability Increase", self._format_compact_value(raw_entry.get("ability"))),
            ]
        elif entry_type == "optionalfeature":
            metadata = {
                "feature_type": self._clean_data(raw_entry.get("featureType")),
                "prerequisite": self._clean_data(raw_entry.get("prerequisite")),
                "consumes": self._clean_data(raw_entry.get("consumes")),
            }
            metadata_pairs = [
                ("Feature Type", self._format_compact_value(raw_entry.get("featureType"))),
                ("Prerequisite", self._format_compact_value(raw_entry.get("prerequisite"))),
                ("Consumes", self._format_compact_value(raw_entry.get("consumes"))),
            ]
        elif entry_type == "race":
            metadata = {
                "base_race_name": self._clean_data(raw_entry.get("raceName")),
                "subrace_name": self._clean_data(raw_entry.get("subraceName")),
                "size": self._clean_data(raw_entry.get("size")),
                "speed": self._clean_data(raw_entry.get("speed")),
                "ability": self._clean_data(raw_entry.get("ability")),
                "languages": self._clean_data(raw_entry.get("languageProficiencies")),
                "skill_proficiencies": self._clean_data(raw_entry.get("skillProficiencies")),
                "feats": self._clean_data(raw_entry.get("feats")),
            }
            metadata_pairs = [
                ("Base Race", self._format_compact_value(raw_entry.get("raceName"))),
                ("Subrace", self._format_compact_value(raw_entry.get("subraceName"))),
                ("Size", self._format_size_list(raw_entry.get("size"))),
                ("Speed", self._format_monster_speed(raw_entry.get("speed"))),
                ("Ability Scores", self._format_compact_value(raw_entry.get("ability"))),
                ("Languages", self._format_compact_value(raw_entry.get("languageProficiencies"))),
                ("Skills", self._format_compact_value(raw_entry.get("skillProficiencies"))),
                ("Feats", self._format_compact_value(raw_entry.get("feats"))),
            ]
        elif entry_type == "skill":
            metadata = {"ability": self._clean_data(raw_entry.get("ability"))}
            metadata_pairs = [("Ability", self._format_ability_code(raw_entry.get("ability")))]
        elif entry_type == "sense":
            metadata = {}
            metadata_pairs = []
        elif entry_type == "subclassfeature":
            metadata = {
                "class_name": self._clean_data(raw_entry.get("className")),
                "class_source": self._clean_data(raw_entry.get("classSource")),
                "subclass_name": self._clean_data(raw_entry.get("subclassShortName")),
                "subclass_source": self._clean_data(raw_entry.get("subclassSource")),
                "level": raw_entry.get("level"),
            }
            metadata_pairs = [
                ("Class", self._format_compact_value(raw_entry.get("className"))),
                ("Subclass", self._format_compact_value(raw_entry.get("subclassShortName"))),
                ("Level", self._format_compact_value(raw_entry.get("level"))),
            ]
        elif entry_type == "action":
            metadata = {"time": self._clean_data(raw_entry.get("time"))}
            metadata_pairs = [("Time", self._format_spell_time(raw_entry.get("time")))]
        elif entry_type == "variantrule":
            metadata = {"rule_type": self._clean_data(raw_entry.get("ruleType"))}
            metadata_pairs = [("Rule Type", self._format_compact_value(raw_entry.get("ruleType")))]
        else:
            metadata = {}
            metadata_pairs = []

        body = {"entries": self._clean_data(raw_entry.get("entries"))}
        rendered_html = self._render_entry_html(
            metadata_pairs=metadata_pairs,
            sections=[("Rules Text", body["entries"])],
        )
        return metadata, body, rendered_html

    def _build_entry_identity_seed(self, entry_type: str, raw_entry: dict[str, Any]) -> str:
        title = str(raw_entry.get("name", "")).strip()
        parts = [normalize_lookup(title) or slugify(title) or "entry"]
        if entry_type == "subclass":
            parts.extend(
                (
                    normalize_lookup(str(raw_entry.get("className", "") or "")),
                    normalize_lookup(str(raw_entry.get("classSource", "") or "")),
                )
            )
        elif entry_type == "classfeature":
            parts.extend(
                (
                    normalize_lookup(str(raw_entry.get("className", "") or "")),
                    normalize_lookup(str(raw_entry.get("classSource", "") or "")),
                    normalize_lookup(str(raw_entry.get("level", "") or "")),
                )
            )
        elif entry_type == "subclassfeature":
            parts.extend(
                (
                    normalize_lookup(str(raw_entry.get("className", "") or "")),
                    normalize_lookup(str(raw_entry.get("classSource", "") or "")),
                    normalize_lookup(str(raw_entry.get("subclassShortName", "") or "")),
                    normalize_lookup(str(raw_entry.get("subclassSource", "") or "")),
                    normalize_lookup(str(raw_entry.get("level", "") or "")),
                )
            )
        return "-".join(part for part in parts if part)

    def _build_feature_progression_sections(self, feature_refs: Any) -> list[dict[str, Any]]:
        if not isinstance(feature_refs, list):
            return []
        grouped: dict[str, list[str]] = {}
        for value in feature_refs:
            label = self._format_feature_reference(value)
            if not label:
                continue
            level = self._extract_feature_reference_level(value) or "Other"
            grouped.setdefault(level, []).append(label)
        rows: list[dict[str, Any]] = []
        for level in sorted(grouped.keys(), key=self._feature_level_sort_key):
            rows.append({"name": f"Level {level}" if level != "Other" else "Other", "entries": grouped[level]})
        return rows

    def _build_class_starting_proficiencies_section(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        rows = [
            ("Armor", value.get("armor")),
            ("Weapons", value.get("weapons")),
            ("Tools", value.get("tools")),
            ("Skills", value.get("skills")),
        ]
        return self._build_named_entry_items(rows, collapse_simple_lists=True)

    def _build_class_starting_equipment_section(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        rows = [
            ("Default Equipment", value.get("default")),
            ("Gold Alternative", value.get("goldAlternative")),
        ]
        return self._build_named_entry_items(rows)

    def _build_optionalfeature_progression_section(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            label = self._clean_text(str(item.get("name", "") or "")) or "Optional Feature Progression"
            detail_lines: list[str] = []
            feature_type = self._format_compact_value(item.get("featureType"))
            if feature_type:
                detail_lines.append(f"Feature Type: {feature_type}")
            progression = item.get("progression")
            if isinstance(progression, dict) and progression:
                progression_parts = [
                    f"Level {level}: {self._format_compact_value(count)}"
                    for level, count in sorted(progression.items(), key=lambda pair: self._feature_level_sort_key(pair[0]))
                ]
                if progression_parts:
                    detail_lines.append("Progression: " + ", ".join(progression_parts))
            rows.append({"name": label, "entries": detail_lines})
        return rows

    def _build_multiclassing_section(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        rows = [
            ("Requirements", value.get("requirements")),
            ("Proficiencies Gained", value.get("proficienciesGained")),
        ]
        return self._build_named_entry_items(rows)

    def _build_named_entry_items(
        self,
        rows: list[tuple[str, Any]],
        *,
        collapse_simple_lists: bool = False,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name, entry_value in rows:
            cleaned_value = self._clean_data(entry_value)
            if cleaned_value in (None, "", [], {}):
                continue
            if collapse_simple_lists:
                cleaned_value = self._collapse_simple_scalar_list(cleaned_value)
            items.append({"name": name, "entries": cleaned_value})
        return items

    def _collapse_simple_scalar_list(self, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        if not value:
            return value
        if any(isinstance(item, (dict, list)) for item in value):
            return value
        rendered_items = [self._format_compact_value(item) for item in value]
        rendered_items = [item for item in rendered_items if item]
        return ", ".join(rendered_items) if rendered_items else value

    def _format_feature_reference(self, value: Any) -> str:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split("|")]
            return self._clean_text(parts[0]) if parts and parts[0].strip() else self._clean_text(value)
        if isinstance(value, dict):
            raw_reference = (
                value.get("classFeature")
                or value.get("subclassFeature")
                or value.get("optionalfeature")
            )
            label = self._format_feature_reference(raw_reference)
            if not label:
                label = self._clean_text(self._format_compact_value(value))
            if value.get("gainSubclassFeature"):
                return f"{label} (choose subclass feature)"
            return label
        return self._clean_text(self._format_compact_value(value))

    def _extract_feature_reference_level(self, value: Any) -> str | None:
        raw_reference = ""
        if isinstance(value, str):
            raw_reference = value
        elif isinstance(value, dict):
            raw_reference = (
                str(value.get("classFeature", "") or "")
                or str(value.get("subclassFeature", "") or "")
                or str(value.get("optionalfeature", "") or "")
            )
        if not raw_reference:
            return None
        for part in reversed([segment.strip() for segment in raw_reference.split("|")]):
            if part.isdigit():
                return part
        return None

    def _feature_level_sort_key(self, value: Any) -> tuple[int, str]:
        text = str(value or "").strip()
        if text.isdigit():
            return (0, f"{int(text):03d}")
        return (1, text.lower())

    def _render_entry_html(
        self,
        *,
        metadata_pairs: list[tuple[str, str]],
        sections: list[tuple[str, Any]],
    ) -> str:
        parts: list[str] = []
        filtered_pairs = [(label, value) for label, value in metadata_pairs if value]
        if filtered_pairs:
            parts.append('<section class="systems-entry-summary">')
            for label, value in filtered_pairs:
                parts.append(
                    f'<p><strong>{escape(label)}:</strong> <span>{escape(value)}</span></p>'
                )
            parts.append("</section>")

        for section_title, section_value in sections:
            if not section_value:
                continue
            parts.append("<section>")
            parts.append(f"<h2>{escape(section_title)}</h2>")
            parts.append(self._render_content_block(section_value, heading_level=3))
            parts.append("</section>")
        return "\n".join(parts)

    def _render_content_block(self, value: Any, *, heading_level: int) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            cleaned = self._clean_text(value)
            return f"<p>{escape(cleaned)}</p>" if cleaned else ""
        if isinstance(value, (int, float)):
            return f"<p>{escape(str(value))}</p>"
        if isinstance(value, list):
            return "\n".join(
                block
                for item in value
                for block in [self._render_content_block(item, heading_level=heading_level)]
                if block
            )
        if isinstance(value, dict):
            value_type = str(value.get("type", "") or "")
            if self._looks_like_ability_block(value):
                return self._render_ability_scores(value)
            if value_type == "list":
                items = value.get("items", [])
                if not isinstance(items, list):
                    return ""
                list_items = [self._render_list_item(item, heading_level=heading_level) for item in items]
                list_items = [item for item in list_items if item]
                if not list_items:
                    return ""
                return "<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>"
            if value_type == "options":
                option_items = value.get("entries", [])
                if not isinstance(option_items, list):
                    return ""
                intro_parts: list[str] = []
                count = value.get("count")
                if count not in (None, ""):
                    intro_parts.append(
                        f"<p>Choose {escape(str(count))} option{'s' if str(count) != '1' else ''}:</p>"
                    )
                list_items = [self._render_list_item(item, heading_level=heading_level) for item in option_items]
                list_items = [item for item in list_items if item]
                if list_items:
                    intro_parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
                return "".join(intro_parts)
            if value_type == "table":
                return self._render_table(value)
            if value_type.lower() in {"abilitydc", "abilityattackmod"}:
                return self._render_ability_formula(value)
            if value_type.lower() in {"refclassfeature", "refoptionalfeature", "refsubclassfeature"}:
                reference_label = self._render_reference_label(value)
                return f"<p>{escape(reference_label)}</p>" if reference_label else ""
            name = self._clean_text(str(value.get("name", "") or ""))
            entries = value.get("entries")
            entry_value = entries if entries is not None else value.get("entry")
            rendered_entries = self._render_content_block(entry_value, heading_level=min(heading_level + 1, 6))
            if name and rendered_entries:
                heading_tag = f"h{heading_level}"
                return f"<section><{heading_tag}>{escape(name)}</{heading_tag}>{rendered_entries}</section>"
            if name:
                return f"<p><strong>{escape(name)}.</strong></p>"
            if rendered_entries:
                return rendered_entries
        return f"<p>{escape(self._clean_text(self._format_compact_value(value)))}</p>"

    def _render_list_item(self, item: Any, *, heading_level: int) -> str:
        if isinstance(item, dict) and str(item.get("type", "") or "") == "item":
            name = self._clean_text(str(item.get("name", "") or ""))
            entry_value = item.get("entry", item.get("entries"))
            entry_text = self._strip_outer_paragraph(self._render_content_block(entry_value, heading_level=heading_level))
            if name and entry_text:
                return f"<strong>{escape(name)}</strong> {entry_text}"
            if name:
                return f"<strong>{escape(name)}</strong>"
            return entry_text
        return self._strip_outer_paragraph(self._render_content_block(item, heading_level=heading_level))

    def _render_reference_label(self, value: dict[str, Any]) -> str:
        for key in ("optionalfeature", "classFeature", "subclassFeature"):
            raw_reference = value.get(key)
            if raw_reference:
                return self._format_feature_reference(raw_reference)
        return ""

    def _render_table(self, value: dict[str, Any]) -> str:
        headers = value.get("colLabels", [])
        rows = value.get("rows", [])
        if not isinstance(rows, list):
            return ""
        parts = ['<div class="table-scroll"><table>']
        caption = self._clean_text(str(value.get("caption", "") or ""))
        if caption:
            parts.append(f"<caption>{escape(caption)}</caption>")
        if isinstance(headers, list) and headers:
            parts.append("<thead><tr>")
            for header in headers:
                parts.append(f"<th>{escape(self._clean_text(self._format_compact_value(header)))}</th>")
            parts.append("</tr></thead>")
        parts.append("<tbody>")
        for row in rows:
            if not isinstance(row, list):
                continue
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{escape(self._clean_text(self._format_compact_value(cell)))}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
        return "".join(parts)

    def _render_ability_scores(self, value: dict[str, Any]) -> str:
        headers = []
        cells = []
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            score = value.get(ability)
            if score is None:
                continue
            headers.append(f"<th>{ABILITY_LABELS[ability]}</th>")
            cells.append(f"<td>{escape(str(score))}</td>")
        if not headers:
            return ""
        return (
            '<div class="table-scroll"><table>'
            + "<thead><tr>"
            + "".join(headers)
            + "</tr></thead><tbody><tr>"
            + "".join(cells)
            + "</tr></tbody></table></div>"
        )

    def _render_ability_formula(self, value: dict[str, Any]) -> str:
        value_type = str(value.get("type", "") or "").strip().lower()
        name = self._clean_text(str(value.get("name", "") or "")) or "Spell"
        ability_phrase = self._format_ability_attribute_phrase(value.get("attributes"))
        if value_type == "abilitydc":
            formula = (
                f"8 + your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "8 + your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} save DC:</strong> {escape(formula)}</p>"
        if value_type == "abilityattackmod":
            formula = (
                f"your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} attack modifier:</strong> {escape(formula)}</p>"
        return ""

    def _format_ability_attribute_phrase(self, value: Any) -> str:
        if isinstance(value, list):
            labels = [
                ABILITY_NAME_LABELS.get(str(item or "").strip().lower(), str(item or "").strip())
                for item in value
                if str(item or "").strip()
            ]
        elif value is None:
            labels = []
        else:
            raw_value = str(value or "").strip()
            labels = [ABILITY_NAME_LABELS.get(raw_value.lower(), raw_value)] if raw_value else []
        if not labels:
            return ""
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} or {labels[1]}"
        return ", ".join(labels[:-1]) + f", or {labels[-1]}"

    def _looks_like_ability_block(self, value: dict[str, Any]) -> bool:
        return any(key in value for key in ("str", "dex", "con", "int", "wis", "cha"))

    def _strip_outer_paragraph(self, html: str) -> str:
        cleaned = html.strip()
        if cleaned.startswith("<p>") and cleaned.endswith("</p>"):
            return cleaned[3:-4].strip()
        return cleaned

    def _clean_data(self, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, nested_value in value.items():
                if key in EXCLUDED_MEDIA_KEYS:
                    continue
                rendered_value = self._clean_data(nested_value)
                if rendered_value in (None, "", [], {}):
                    continue
                cleaned[key] = rendered_value
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                rendered_item = self._clean_data(item)
                if rendered_item in (None, "", [], {}):
                    continue
                cleaned_list.append(rendered_item)
            return cleaned_list
        return value

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return self._clean_text(value)
        if isinstance(value, list):
            return " ".join(filter(None, (self._extract_text(item) for item in value))).strip()
        if isinstance(value, dict):
            parts = []
            for key, nested_value in value.items():
                if key in {"type", "style", "data"}:
                    continue
                extracted = self._extract_text(nested_value)
                if extracted:
                    parts.append(extracted)
            return " ".join(parts).strip()
        return str(value)

    def _clean_text(self, value: str) -> str:
        stripped = self._strip_inline_tags(value)
        return re.sub(r"\s+", " ", stripped).strip()

    def _strip_inline_tags(self, value: str) -> str:
        rendered = str(value or "")
        while True:
            updated = INLINE_TAG_PATTERN.sub(self._replace_inline_tag, rendered)
            if updated == rendered:
                return updated
            rendered = updated

    def _replace_inline_tag(self, match: re.Match[str]) -> str:
        body = match.group(1).strip()
        tag, _, remainder = body.partition(" ")
        normalized_tag = tag.lower()
        raw_text = remainder.strip()
        primary_text = raw_text.split("|", 1)[0].strip()
        if normalized_tag == "atk":
            return ATTACK_TAG_LABELS.get(raw_text.lower(), primary_text or raw_text)
        if normalized_tag == "hit":
            if not primary_text:
                return ""
            if primary_text.startswith(("+", "-")):
                return primary_text
            return f"+{primary_text}"
        if normalized_tag == "h":
            return "Hit:"
        if normalized_tag == "dc":
            return f"DC {primary_text}"
        if normalized_tag in {"damage", "dice", "chance", "recharge", "skill", "condition", "status", "disease"}:
            return primary_text
        if normalized_tag in {
            "action",
            "background",
            "book",
            "class",
            "classfeature",
            "creature",
            "deity",
            "feat",
            "filter",
            "item",
            "language",
            "object",
            "optfeature",
            "race",
            "sense",
            "spell",
            "table",
            "trap",
            "variantrule",
            "vehicle",
        }:
            return primary_text
        return primary_text or raw_text or normalized_tag

    def _normalize_entry_types(self, entry_types: list[str] | None) -> list[str]:
        if not entry_types:
            return list(SUPPORTED_ENTRY_TYPES)
        normalized: list[str] = []
        seen: set[str] = set()
        for entry_type in entry_types:
            normalized_type = str(entry_type).strip().lower()
            if normalized_type not in SUPPORTED_ENTRY_TYPES:
                raise ValueError(f"Unsupported entry type: {entry_type}")
            if normalized_type in seen:
                continue
            seen.add(normalized_type)
            normalized.append(normalized_type)
        return normalized

    def _make_unique_identifier(self, base: str, *, used: set[str], page: Any) -> str:
        candidate = base
        if candidate not in used:
            used.add(candidate)
            return candidate
        if page not in (None, ""):
            candidate = f"{base}-p{page}"
            if candidate not in used:
                used.add(candidate)
                return candidate
        suffix = 2
        while True:
            candidate = f"{base}-{suffix}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            suffix += 1

    def _is_player_safe_default(self, source_id: str, entry_type: str) -> bool:
        return source_id in PLAYER_SAFE_SOURCE_IDS and entry_type in PLAYER_SAFE_ENTRY_TYPES

    def _is_dm_heavy(self, source_id: str, entry_type: str) -> bool:
        return entry_type == "monster" or source_id not in PLAYER_SAFE_SOURCE_IDS

    def _format_hit_die(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        number = value.get("number")
        faces = value.get("faces")
        if number in (None, "") or faces in (None, ""):
            return self._format_compact_value(value)
        return f"{number}d{faces}"

    def _format_ability_code(self, value: Any) -> str:
        code = str(value or "").strip().lower()
        return ABILITY_LABELS.get(code, code.upper())

    def _format_ability_code_list(self, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(
                rendered
                for rendered in (self._format_ability_code(item) for item in value)
                if rendered
            )
        return self._format_ability_code(value)

    def _format_spell_level_school(self, level: Any, school: Any) -> str:
        school_label = SPELL_SCHOOL_LABELS.get(str(school or "").upper(), str(school or "").upper())
        try:
            normalized_level = int(level)
        except (TypeError, ValueError):
            normalized_level = None
        if normalized_level is None:
            return school_label or ""
        if normalized_level == 0:
            return f"Cantrip ({school_label})"
        suffix = "th"
        if normalized_level == 1:
            suffix = "st"
        elif normalized_level == 2:
            suffix = "nd"
        elif normalized_level == 3:
            suffix = "rd"
        return f"{normalized_level}{suffix}-level {school_label}".strip()

    def _format_spell_time(self, value: Any) -> str:
        if not isinstance(value, list):
            return self._format_compact_value(value)
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            number = item.get("number")
            unit = str(item.get("unit", "") or "")
            rendered = " ".join(part for part in (str(number) if number is not None else "", unit.replace("_", " ")) if part).strip()
            condition = item.get("condition")
            if condition:
                rendered = f"{rendered}, {self._format_compact_value(condition)}" if rendered else self._format_compact_value(condition)
            if rendered:
                parts.append(rendered)
        return ", ".join(parts)

    def _format_spell_range(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        range_type = str(value.get("type", "") or "").replace("_", " ")
        distance = value.get("distance")
        if not isinstance(distance, dict):
            return range_type.title() if range_type else ""
        amount = distance.get("amount")
        distance_type = str(distance.get("type", "") or "").replace("_", " ")
        if amount is None:
            return distance_type.title() if distance_type else range_type.title()
        return f"{amount} {distance_type}".strip()

    def _format_spell_components(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        parts: list[str] = []
        if value.get("v"):
            parts.append("V")
        if value.get("s"):
            parts.append("S")
        material = value.get("m")
        if isinstance(material, dict):
            material_text = self._format_compact_value(material.get("text"))
            parts.append(f"M ({material_text})" if material_text else "M")
        elif material:
            parts.append(f"M ({self._format_compact_value(material)})")
        return ", ".join(parts)

    def _format_spell_duration(self, value: Any) -> str:
        if not isinstance(value, list):
            return self._format_compact_value(value)
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            duration_type = str(item.get("type", "") or "").replace("_", " ")
            if duration_type == "timed":
                duration = item.get("duration", {})
                if isinstance(duration, dict):
                    amount = duration.get("amount")
                    unit = str(duration.get("type", "") or "").replace("_", " ")
                    rendered = " ".join(part for part in (str(amount) if amount is not None else "", unit) if part).strip()
                else:
                    rendered = ""
                if item.get("concentration"):
                    rendered = f"Concentration, up to {rendered}" if rendered else "Concentration"
                parts.append(rendered or duration_type.title())
            else:
                parts.append(duration_type.title())
        return ", ".join(part for part in parts if part)

    def _format_spell_classes(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        class_list = value.get("fromClassList")
        if not isinstance(class_list, list):
            return self._format_compact_value(value)
        names = []
        for item in class_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if name:
                names.append(name)
        return ", ".join(names)

    def _format_size_list(self, value: Any) -> str:
        if not isinstance(value, list):
            return self._format_compact_value(value)
        labels = [SIZE_LABELS.get(str(item), str(item)) for item in value]
        return ", ".join(label for label in labels if label)

    def _format_creature_type(self, value: Any) -> str:
        if isinstance(value, str):
            return value.title()
        if isinstance(value, dict):
            creature_type = str(value.get("type", "") or "")
            tags = value.get("tags", [])
            rendered_tags = self._format_compact_value(tags)
            if creature_type and rendered_tags:
                return f"{creature_type.title()} ({rendered_tags})"
            return creature_type.title() or rendered_tags
        return self._format_compact_value(value)

    def _format_alignment(self, value: Any) -> str:
        if isinstance(value, list):
            labels = [ALIGNMENT_LABELS.get(str(item), str(item)) for item in value]
            return " ".join(label for label in labels if label).strip()
        return self._format_compact_value(value)

    def _format_monster_ac(self, value: Any) -> str:
        if not isinstance(value, list):
            return self._format_compact_value(value)
        parts: list[str] = []
        for item in value:
            if isinstance(item, (int, float)):
                parts.append(str(item))
                continue
            if not isinstance(item, dict):
                continue
            ac_value = item.get("ac")
            from_text = self._format_compact_value(item.get("from"))
            if ac_value is not None and from_text:
                parts.append(f"{ac_value} ({from_text})")
            elif ac_value is not None:
                parts.append(str(ac_value))
        return ", ".join(parts)

    def _format_monster_hp(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        average = value.get("average")
        formula = str(value.get("formula", "") or "").strip()
        if average is not None and formula:
            return f"{average} ({formula})"
        if average is not None:
            return str(average)
        return formula

    def _format_monster_speed(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value} ft."
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        parts: list[str] = []
        for movement_type in ("walk", "burrow", "climb", "fly", "swim"):
            if movement_type not in value:
                continue
            amount = value[movement_type]
            amount_text = self._format_compact_value(amount)
            if amount_text == "True":
                amount_text = "equal to walking speed"
            elif amount_text and amount_text != "equal to walking speed":
                amount_text = f"{amount_text} ft."
            parts.append(f"{movement_type.title()} {amount_text}".strip())
        return ", ".join(parts)

    def _format_monster_senses(self, senses: Any, passive: Any) -> str:
        parts = []
        senses_text = self._format_compact_value(senses)
        if senses_text:
            parts.append(senses_text)
        if passive not in (None, ""):
            parts.append(f"passive Perception {passive}")
        return ", ".join(parts)

    def _format_monster_cr(self, value: Any) -> str:
        if isinstance(value, dict):
            cr = value.get("cr")
            xp = value.get("xp")
            if cr is not None and xp is not None:
                return f"{cr} ({xp} XP)"
            if cr is not None:
                return str(cr)
        return self._format_compact_value(value)

    def _format_dict_bonus_list(self, value: Any) -> str:
        if not isinstance(value, dict):
            return self._format_compact_value(value)
        parts = []
        for key, bonus in value.items():
            label = ABILITY_LABELS.get(str(key), str(key).replace("_", " ").title())
            rendered_bonus = str(bonus)
            if rendered_bonus and not rendered_bonus.startswith(("+", "-")) and rendered_bonus.lstrip("0123456789") == "":
                rendered_bonus = f"+{rendered_bonus}"
            parts.append(f"{label} {rendered_bonus}")
        return ", ".join(parts)

    def _format_weight(self, value: Any) -> str:
        if value in (None, ""):
            return ""
        return f"{value} lb."

    def _format_compact_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return self._clean_text(value)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            parts = [self._format_compact_value(item) for item in value]
            return ", ".join(part for part in parts if part)
        if isinstance(value, dict):
            parts = []
            for key, nested_value in value.items():
                if key in {"type", "style", "data"}:
                    continue
                rendered_value = self._format_compact_value(nested_value)
                if not rendered_value:
                    continue
                label = str(key).replace("_", " ").title()
                parts.append(f"{label}: {rendered_value}")
            return "; ".join(parts)
        return str(value)

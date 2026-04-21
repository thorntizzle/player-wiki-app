from __future__ import annotations

import argparse
from copy import deepcopy
import fnmatch
import re
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

import yaml

from .auth_store import isoformat, utcnow
from .character_builder import (
    _extract_campaign_page_ref,
    _merge_name_candidates,
    _normalize_explicit_link_identity,
    _normalize_page_ref_payload,
    _resolve_native_character_level,
    _spell_payload_key,
    normalize_definition_to_native_model,
)
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_profile import ensure_profile_class_rows
from .character_repository import CampaignCharacterConfig, load_campaign_character_config
from .character_service import build_initial_state, merge_state_with_definition
from .character_store import CharacterStateStore, CharacterStateWriteResult
from .db import init_database
from .repository import slugify

PARSER_VERSION = "2026-04-06.4"
REST_TRACKER_PATTERN = re.compile(
    r"^(?P<label>.+?)\s*[-:]\s*(?P<value>\d+)\s*/\s*(?P<reset>Long Rest|Short Rest|Daily|Other|Manual|Never)\b",
    re.IGNORECASE,
)
PROGRESS_PATTERN = re.compile(
    r"^(?P<label>.+?)\s+(?P<current>\d+)\s*/\s*(?P<max>\d+)\b",
    re.IGNORECASE,
)
SOURCE_ID_PATTERN = re.compile(
    r"^(?P<source_id>(?=[A-Za-z0-9']*[A-Z].*[A-Z])[A-Za-z][A-Za-z0-9']{1,9})(?:\s+(?P<page>\d+(?:-\d+)?))?$"
)
ANONYMOUS_ACTION_COST_PATTERN = re.compile(
    r"^(?P<value>\d+)\s*/\s*(?P<reset>Long Rest|Short Rest|Daily|Other|Manual|Never)\s*-\s*"
    r"(?:(?P<count>\d+)\s+)?(?P<activation>Bonus Action|Action|Reaction|Special)$",
    re.IGNORECASE,
)
NAMED_ACTION_COST_PATTERN = re.compile(
    r"^(?P<label>.+?)\s*[:\-]\s*(?:(?P<count>\d+)\s+)?(?P<activation>Bonus Action|Action|Reaction|Special)$",
    re.IGNORECASE,
)
ACTION_SECTION_ACTIVATION_HINTS = {
    "actions": "action",
    "bonus actions": "bonus_action",
    "reactions": "reaction",
}
GENERIC_ACTION_BLOCK_TITLES = {"standard actions"}
GENERIC_FOLLOWUP_SUFFIXES = {"attack", "action", "bonus action", "reaction", "special"}
STANDALONE_METADATA_TITLES = {"action", "bonus action", "reaction", "special"}
DETACHED_METADATA_VALUE_PATTERN = re.compile(
    r"^(?:bonus action|reaction|special|\d+\s+(?:action|actions|minute|minutes|hour|hours|day|days))$",
    re.IGNORECASE,
)
ABILITY_CHOICE_FEATURE_NAMES = {
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
}
NATIVE_MANAGED_CUSTOM_FEATURE_CATEGORY = "custom_feature"
NATIVE_MANAGED_CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"


class CharacterImportError(Exception):
    pass


@dataclass(slots=True)
class CharacterImportResult:
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    character_dir: Path
    state_created: bool


def iter_character_source_files(config: CampaignCharacterConfig) -> list[Path]:
    if not config.source_root.exists():
        raise CharacterImportError(f"Character source root does not exist: {config.source_root}")

    files: list[Path] = []
    for path in sorted(config.source_root.rglob("*.md")):
        relative_path = path.relative_to(config.source_root).as_posix()
        if fnmatch.fnmatch(relative_path, config.source_glob.replace("\\", "/")):
            files.append(path)
    return files


def resolve_source_path(config: CampaignCharacterConfig, source_arg: str) -> Path:
    direct_candidate = Path(source_arg)
    if direct_candidate.is_absolute() and direct_candidate.exists():
        return direct_candidate

    normalized = source_arg.replace("\\", "/").strip("/")
    candidates = [config.source_root / normalized, config.source_root / f"{normalized}.md"]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches: list[Path] = []
    lowered = source_arg.lower()
    for source_path in iter_character_source_files(config):
        relative_path = source_path.relative_to(config.source_root).as_posix().lower()
        title = source_path.stem.lower()
        if lowered in relative_path or lowered in title:
            matches.append(source_path)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CharacterImportError(f"No character sheet matched '{source_arg}'.")

    options = "\n".join(
        f"  - {match.relative_to(config.source_root).as_posix()}" for match in matches[:10]
    )
    raise CharacterImportError(f"Character sheet '{source_arg}' is ambiguous. Matches:\n{options}")


def split_sections(markdown_text: str, marker: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in markdown_text.replace("\r\n", "\n").splitlines():
        if line.startswith(f"{marker} "):
            current_key = line[len(marker) + 1 :].strip()
            sections[current_key] = []
            continue
        if current_key is not None:
            sections[current_key].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def extract_first_table(section_text: str) -> list[dict[str, str]]:
    lines = section_text.splitlines()
    block: list[str] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            block.append(stripped)
            in_table = True
            continue
        if in_table:
            break
    if len(block) < 2:
        return []
    headers = [cell.strip() for cell in block[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in block[2:]:
        values = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(
            {
                headers[index]: values[index] if index < len(values) else ""
                for index in range(len(headers))
            }
        )
    return rows


def parse_bullet_items(section_text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        if stripped.startswith("- "):
            if current:
                items.append("\n".join(current).strip())
            current = [stripped[2:].strip()]
        elif current:
            current.append(stripped)
    if current:
        items.append("\n".join(current).strip())
    return items


def split_text_blocks(section_text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        current.append(stripped)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def normalize_feature_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def activation_type_from_section_title(section_title: str) -> str:
    return ACTION_SECTION_ACTIVATION_HINTS.get(normalize_feature_text(section_title), "passive")


def normalize_feature_header_name(header: str, tracker_matches: list[dict[str, Any]]) -> str:
    if tracker_matches:
        label = str(tracker_matches[0].get("label") or "").strip()
        if label:
            return label
    named_action_match = NAMED_ACTION_COST_PATTERN.match(header.strip())
    if named_action_match:
        return named_action_match.group("label").strip()
    return header.strip()


def merge_feature_metadata(
    feature: dict[str, Any],
    *,
    activation_type: str,
    tracker_ref: str | None = None,
) -> None:
    existing_activation = str(feature.get("activation_type") or "").strip().lower()
    if activation_type and activation_type != "passive" and existing_activation in {"", "passive"}:
        feature["activation_type"] = activation_type
    if tracker_ref and not str(feature.get("tracker_ref") or "").strip():
        feature["tracker_ref"] = tracker_ref


def split_feature_source_reference(header: str) -> dict[str, str] | None:
    stripped = str(header or "").strip()
    if " - " not in stripped:
        return None
    name, suffix = (part.strip() for part in stripped.rsplit(" - ", 1))
    if not name or not suffix:
        return None
    if not SOURCE_ID_PATTERN.fullmatch(suffix):
        return None
    return {
        "name": name,
        "source": suffix,
    }


def is_generic_followup_feature(name: str, previous_name: str) -> bool:
    normalized_name = normalize_feature_text(name)
    normalized_previous = normalize_feature_text(previous_name)
    if not normalized_name or not normalized_previous or not normalized_name.startswith(normalized_previous):
        return False
    suffix = normalized_name[len(normalized_previous) :].strip()
    return suffix in GENERIC_FOLLOWUP_SUFFIXES


def feature_name_aliases(name: str) -> list[str]:
    stripped = str(name or "").strip()
    aliases: list[str] = []
    for separator in (":", " - "):
        if separator not in stripped:
            continue
        left, right = (part.strip() for part in stripped.split(separator, 1))
        for alias in (right, left):
            if alias and alias not in aliases:
                aliases.append(alias)
    return aliases


def is_standalone_metadata_feature(name: str) -> bool:
    normalized_name = normalize_feature_text(name)
    if normalized_name in STANDALONE_METADATA_TITLES:
        return True
    return bool(DETACHED_METADATA_VALUE_PATTERN.fullmatch(normalized_name))


def should_merge_tracker_only_followup_feature(
    name: str,
    previous_feature: dict[str, Any],
) -> bool:
    previous_name = str(previous_feature.get("name") or "")
    if normalize_feature_text(name) == normalize_feature_text(previous_name):
        return True
    previous_description = str(previous_feature.get("description_markdown") or "").strip()
    previous_source = str(previous_feature.get("source") or "").strip()
    previous_tracker_ref = str(previous_feature.get("tracker_ref") or "").strip()
    return (
        not previous_description
        and not previous_source
        and not previous_tracker_ref
        and ":" not in previous_name
    )


def find_feature_alias_target(
    name: str,
    features: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not features:
        return None
    if " - " not in str(name or ""):
        return None
    for alias in feature_name_aliases(name):
        normalized_alias = normalize_feature_text(alias)
        if not normalized_alias:
            continue
        for feature in reversed(features):
            if normalize_feature_text(str(feature.get("name") or "")) != normalized_alias:
                continue
            if (
                str(feature.get("description_markdown") or "").strip()
                or str(feature.get("source") or "").strip()
                or feature.get("systems_ref")
                or feature.get("page_ref")
            ):
                return feature
    return None


def is_ability_choice_followup_feature(
    name: str,
    *,
    category: str,
    previous_feature: dict[str, Any] | None,
    description: str,
    source_value: str,
) -> bool:
    if category != "feat" or previous_feature is None:
        return False
    if source_value.strip() or not description.strip():
        return False
    normalized_name = normalize_feature_text(name.replace("•", " ").replace("â€¢", " "))
    if normalized_name not in ABILITY_CHOICE_FEATURE_NAMES:
        return False
    return str(previous_feature.get("category") or "").strip() == "feat"


def merge_ability_choice_followup_feature(
    feature: dict[str, Any],
    *,
    name: str,
    description: str,
    activation_type: str,
    tracker_ref: str | None = None,
) -> None:
    label = str(name or "").replace("•", "").replace("â€¢", "").strip()
    addition = description.strip()
    if label:
        addition = f"Chosen ability: {label}.\n{addition}" if addition else f"Chosen ability: {label}."
    existing_description = str(feature.get("description_markdown") or "").strip()
    if addition:
        feature["description_markdown"] = f"{existing_description}\n\n{addition}".strip() if existing_description else addition
    merge_feature_metadata(
        feature,
        activation_type=activation_type,
        tracker_ref=tracker_ref,
    )


def find_action_feature_merge_target(
    feature: dict[str, Any],
    name_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if " - " not in str(feature.get("name") or ""):
        return None
    description_key = normalize_feature_text(str(feature.get("description_markdown") or ""))
    if not description_key:
        return None
    for alias in feature_name_aliases(str(feature.get("name") or "")):
        existing = name_lookup.get(normalize_feature_text(alias))
        if existing is None:
            continue
        existing_description_key = normalize_feature_text(str(existing.get("description_markdown") or ""))
        if existing_description_key != description_key:
            continue
        if (
            str(existing.get("source") or "").strip()
            or existing.get("systems_ref")
            or existing.get("page_ref")
        ):
            return existing
    return None


def looks_like_action_feature_header(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if normalize_feature_text(stripped) in GENERIC_ACTION_BLOCK_TITLES:
        return True
    if REST_TRACKER_PATTERN.match(stripped):
        return True
    if NAMED_ACTION_COST_PATTERN.match(stripped):
        return True
    if ":" in stripped:
        return True
    if stripped[-1:] in {".", "!", "?"}:
        return False
    return bool(re.match(r"^[A-Z][^.!?]{0,80}$", stripped)) and len(stripped.split()) <= 8


def parse_action_feature_blocks(section_text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_header = ""
    current_lines: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if current_header:
                current_lines.append("")
            continue
        if looks_like_action_feature_header(stripped):
            if current_header:
                blocks.append(
                    {
                        "header": current_header,
                        "description": "\n".join(current_lines).strip(),
                    }
                )
            current_header = stripped
            current_lines = []
            continue
        if current_header:
            current_lines.append(stripped)
            continue
        current_header = stripped
        current_lines = []
    if current_header:
        blocks.append({"header": current_header, "description": "\n".join(current_lines).strip()})
    return [block for block in blocks if str(block.get("header") or "").strip()]


def merge_feature_record(destination: dict[str, Any], source: dict[str, Any]) -> None:
    if not str(destination.get("description_markdown") or "").strip() and str(source.get("description_markdown") or "").strip():
        destination["description_markdown"] = source["description_markdown"]
    if not str(destination.get("source") or "").strip() and str(source.get("source") or "").strip():
        destination["source"] = source["source"]
    merge_feature_metadata(
        destination,
        activation_type=str(source.get("activation_type") or "passive"),
        tracker_ref=str(source.get("tracker_ref") or "").strip() or None,
    )


def merge_action_features_into_features(
    features: list[dict[str, Any]],
    action_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_features = [dict(feature) for feature in features]
    name_lookup: dict[str, dict[str, Any]] = {}
    for feature in merged_features:
        normalized_name = normalize_feature_text(str(feature.get("name") or ""))
        if normalized_name and normalized_name not in name_lookup:
            name_lookup[normalized_name] = feature

    action_feature_names = {
        normalize_feature_text(str(feature.get("name") or ""))
        for feature in action_features
        if str(feature.get("name") or "").strip()
    }
    for feature in action_features:
        normalized_name = normalize_feature_text(str(feature.get("name") or ""))
        existing = name_lookup.get(normalized_name)
        if existing is None:
            existing = find_action_feature_merge_target(feature, name_lookup)
        if existing is not None:
            merge_feature_record(existing, feature)
            continue
        cloned = dict(feature)
        merged_features.append(cloned)
        if normalized_name:
            name_lookup[normalized_name] = cloned

    compacted_features: list[dict[str, Any]] = []
    for feature in merged_features:
        name = str(feature.get("name") or "").strip()
        normalized_name = normalize_feature_text(name)
        if (
            ":" in name
            and normalized_name not in action_feature_names
            and str(feature.get("tracker_ref") or "").strip()
            and not str(feature.get("description_markdown") or "").strip()
            and not str(feature.get("source") or "").strip()
        ):
            parent_name = name.rsplit(":", 1)[0].strip()
            parent = name_lookup.get(normalize_feature_text(parent_name))
            if parent is not None and parent is not feature:
                merge_feature_metadata(parent, activation_type="passive", tracker_ref=str(feature.get("tracker_ref") or ""))
                continue
        compacted_features.append(feature)
    return compacted_features


def clean_text_value(value: str) -> str:
    return value.strip().replace("`", "")


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == "--":
        return None
    match = re.search(r"-?\d+", cleaned.replace(",", ""))
    return int(match.group(0)) if match else None


def parse_signed_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == "--":
        return None
    match = re.search(r"[+-]?\d+", cleaned.replace(",", ""))
    return int(match.group(0)) if match else None


def parse_csv_values(value: str) -> list[str]:
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_class_level(class_level_text: str) -> list[dict[str, Any]]:
    match = re.match(r"(?P<class_name>.+?)\s+(?P<level>\d+)$", class_level_text.strip())
    if not match:
        return [{"class_name": class_level_text.strip(), "subclass_name": "", "level": 0}]
    return [
        {
            "class_name": match.group("class_name").strip(),
            "subclass_name": "",
            "level": int(match.group("level")),
        }
    ]


def build_feature_category(group_name: str) -> str:
    normalized = group_name.lower()
    tokens = set(re.findall(r"[a-z']+", normalized))
    if "species" in tokens or "traits" in tokens:
        return "species_trait"
    if "feat" in tokens or "feats" in tokens:
        return "feat"
    if "item" in tokens or "items" in tokens:
        return "item_feature"
    if "campaign" in tokens:
        return "campaign_feature"
    return "class_feature"


def build_activation_type(value: str) -> str:
    normalized = normalize_feature_text(value)
    if "bonus action" in normalized:
        return "bonus_action"
    if "reaction" in normalized:
        return "reaction"
    if re.search(r"\b\d+\s+action\b", normalized) or normalized.endswith(" action"):
        return "action"
    if "special" in normalized or re.search(r"\b\d+\s+(hour|minute)s?\b", normalized):
        return "special"
    return "passive"


def build_tracker_template(
    label: str,
    *,
    current: int,
    max_value: int | None,
    reset_token: str,
    category: str,
    display_order: int,
    notes: str = "",
    source_hint: str = "",
) -> dict[str, Any]:
    reset_lookup = {
        "long rest": ("long_rest", "max", "confirm_before_reset"),
        "short rest": ("short_rest", "max", "confirm_before_reset"),
        "daily": ("daily", "max", "confirm_before_reset"),
        "manual": ("manual", "unchanged", "manual_only"),
        "never": ("never", "unchanged", "manual_only"),
        "other": ("other", "unchanged", "manual_only"),
    }
    reset_on, reset_to, rest_behavior = reset_lookup.get(
        reset_token.lower(),
        ("manual", "unchanged", "manual_only"),
    )
    return {
        "id": slugify(label),
        "label": label,
        "category": category,
        "initial_current": current,
        "max": max_value if max_value is not None else current,
        "reset_on": reset_on,
        "reset_to": reset_to,
        "rest_behavior": rest_behavior,
        "notes": notes or source_hint,
        "display_order": display_order,
    }


def merge_tracker(
    tracker_templates: dict[str, dict[str, Any]],
    tracker: dict[str, Any],
    warnings: list[str],
) -> None:
    existing = tracker_templates.get(tracker["id"])
    if existing is None:
        tracker_templates[tracker["id"]] = tracker
        return
    if existing["max"] != tracker["max"] or existing["reset_on"] != tracker["reset_on"]:
        warnings.append(
            f"Conflicting tracker definition for '{tracker['label']}'. Kept the first parsed version."
        )


def extract_trackers_from_text(
    section_text: str,
    *,
    category: str,
    display_start: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    trackers: list[dict[str, Any]] = []
    display_order = display_start
    for raw_line in section_text.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue

        rest_match = REST_TRACKER_PATTERN.match(line)
        if rest_match:
            trackers.append(
                build_tracker_template(
                    rest_match.group("label").strip(),
                    current=int(rest_match.group("value")),
                    max_value=int(rest_match.group("value")),
                    reset_token=rest_match.group("reset"),
                    category=category,
                    display_order=display_order,
                    source_hint=line,
                )
            )
            display_order += 1
            continue

        progress_match = PROGRESS_PATTERN.match(line)
        if progress_match:
            label = progress_match.group("label").strip()
            if len(label) < 3:
                continue
            current_value = int(progress_match.group("current"))
            max_value = int(progress_match.group("max"))
            if current_value > max_value:
                warnings.append(
                    f"Skipped suspicious progress tracker line '{line}' because current exceeded max."
                )
                continue
            trackers.append(
                build_tracker_template(
                    label,
                    current=current_value,
                    max_value=max_value,
                    reset_token="manual",
                    category="custom_progress",
                    display_order=display_order,
                    source_hint=line,
                )
            )
            display_order += 1

    return trackers


def build_personality_markdown(subsections: dict[str, str]) -> str:
    ordered = [name for name in ("Personality Traits", "Ideals", "Bonds", "Flaws") if subsections.get(name)]
    blocks = [f"### {name}\n{subsections[name].strip()}" for name in ordered]
    return "\n\n".join(blocks).strip()


def parse_sheet_summary(section_text: str, warnings: list[str]) -> dict[str, Any]:
    summary_rows = extract_first_table(section_text)
    if not summary_rows:
        warnings.append("Sheet Summary table was not found.")
        return {}
    summary = {row.get("Field", "").strip(): row.get("Value", "").strip() for row in summary_rows}
    class_level_text = clean_text_value(summary.get("Class & Level", ""))
    return {
        "sheet_name": clean_text_value(summary.get("Sheet Name", "")),
        "display_name": clean_text_value(summary.get("Sheet Name", "")),
        "class_level_text": class_level_text,
        "classes": parse_class_level(class_level_text) if class_level_text else [],
        "species": clean_text_value(summary.get("Species", "")),
        "background": clean_text_value(summary.get("Background", "")),
        "alignment": clean_text_value(summary.get("Alignment", "")),
        "experience_model": clean_text_value(summary.get("Experience", "")),
        "size": clean_text_value(summary.get("Size", "")),
        "gender": clean_text_value(summary.get("Gender", "")),
        "age": clean_text_value(summary.get("Age", "")),
        "height": clean_text_value(summary.get("Height", "")),
        "weight": clean_text_value(summary.get("Weight", "")),
        "eyes": clean_text_value(summary.get("Eyes", "")),
        "hair": clean_text_value(summary.get("Hair", "")),
        "skin": clean_text_value(summary.get("Skin", "")),
        "faith": "",
        "guild": "",
        "biography_markdown": "",
        "personality_markdown": "",
    }


def parse_core_stats(section_text: str, warnings: list[str]) -> dict[str, Any]:
    stats_rows = extract_first_table(section_text)
    if not stats_rows:
        warnings.append("Defenses And Core Stats table was not found.")
        return {}
    stats_map = {row.get("Metric", "").strip(): row.get("Value", "").strip() for row in stats_rows}
    return {
        "armor_class": parse_int(stats_map.get("Armor Class")),
        "initiative_bonus": parse_signed_int(stats_map.get("Initiative")),
        "speed": clean_text_value(stats_map.get("Speed", "")),
        "max_hp": parse_int(stats_map.get("Max HP")),
        "proficiency_bonus": parse_signed_int(stats_map.get("Proficiency Bonus")),
        "passive_perception": parse_int(stats_map.get("Passive Perception")),
        "passive_insight": parse_int(stats_map.get("Passive Insight")),
        "passive_investigation": parse_int(stats_map.get("Passive Investigation")),
        "ability_scores": {},
    }


def parse_ability_scores(section_text: str) -> dict[str, dict[str, int | None]]:
    ability_rows = extract_first_table(section_text)
    scores: dict[str, dict[str, int | None]] = {}
    for row in ability_rows:
        ability = row.get("Ability", "").strip().lower()
        if not ability:
            continue
        scores[ability] = {
            "score": parse_int(row.get("Score")),
            "modifier": parse_signed_int(row.get("Modifier")),
            "save_bonus": parse_signed_int(row.get("Save")),
        }
    return scores


def parse_skills(section_text: str) -> list[dict[str, Any]]:
    skill_rows = extract_first_table(section_text)
    skills: list[dict[str, Any]] = []
    for row in skill_rows:
        proficiency = row.get("Proficiency", "").strip().lower()
        if "expert" in proficiency:
            proficiency_level = "expertise"
        elif "proficient" in proficiency:
            proficiency_level = "proficient"
        else:
            proficiency_level = "none"
        skills.append(
            {
                "name": row.get("Skill", "").strip(),
                "bonus": parse_signed_int(row.get("Bonus")),
                "proficiency_level": proficiency_level,
            }
        )
    return skills


def parse_proficiencies(section_text: str) -> dict[str, list[str]]:
    result = {"armor": [], "weapons": [], "tools": [], "languages": []}
    for item in parse_bullet_items(section_text):
        key, _, value = item.partition(":")
        normalized_key = key.strip().lower()
        parsed_values = parse_csv_values(value)
        if normalized_key == "armor":
            result["armor"] = parsed_values
        elif normalized_key == "weapons":
            result["weapons"] = parsed_values
        elif normalized_key == "tools":
            result["tools"] = parsed_values
        elif normalized_key == "languages":
            result["languages"] = parsed_values
    return result


def parse_attacks(section_text: str) -> list[dict[str, Any]]:
    attack_rows = extract_first_table(section_text)
    attacks: list[dict[str, Any]] = []
    for index, row in enumerate(attack_rows, start=1):
        name = row.get("Attack", "").strip()
        if not name:
            continue
        category = "weapon"
        lowered = name.lower()
        if lowered == "unarmed strike":
            category = "unarmed"
        elif any(keyword in lowered for keyword in ("bolt", "blast", "spell")):
            category = "spell_attack"
        attacks.append(
            {
                "id": f"{slugify(name)}-{index}",
                "name": name,
                "attack_bonus": parse_signed_int(row.get("Hit")),
                "damage": row.get("Damage", "").strip(),
                "damage_type": "",
                "notes": row.get("Notes", "").strip(),
                "category": category,
            }
        )
    return attacks


def parse_feature_groups(section_text: str, warnings: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feature_groups = split_sections(section_text, "###")
    features: list[dict[str, Any]] = []
    tracker_templates: dict[str, dict[str, Any]] = {}
    display_order = 0

    for group_name, group_body in feature_groups.items():
        feature_category = build_feature_category(group_name)
        for index, item in enumerate(parse_bullet_items(group_body), start=1):
            lines = item.splitlines()
            header = lines[0].strip()
            description = "\n".join(line for line in lines[1:] if line.strip()).strip()
            source_match = split_feature_source_reference(header)
            header_name = source_match["name"].strip() if source_match else header
            source_value = source_match["source"].strip() if source_match else ""
            activation_type = build_activation_type(header)
            tracker_matches = extract_trackers_from_text(
                header,
                category=feature_category,
                display_start=display_order,
                warnings=warnings,
            )
            tracker_ref = tracker_matches[0]["id"] if tracker_matches else None
            for tracker in tracker_matches:
                merge_tracker(tracker_templates, tracker, warnings)
                display_order += 1

            anonymous_usage_match = ANONYMOUS_ACTION_COST_PATTERN.match(header_name)
            if anonymous_usage_match:
                if features:
                    tracker = build_tracker_template(
                        str(features[-1].get("name") or "Feature"),
                        current=int(anonymous_usage_match.group("value")),
                        max_value=int(anonymous_usage_match.group("value")),
                        reset_token=anonymous_usage_match.group("reset"),
                        category=feature_category,
                        display_order=display_order,
                        source_hint=header_name,
                    )
                    merge_tracker(tracker_templates, tracker, warnings)
                    display_order += 1
                    merge_feature_metadata(
                        features[-1],
                        activation_type=activation_type,
                        tracker_ref=tracker["id"],
                    )
                continue

            normalized_header_name = normalize_feature_header_name(header_name, tracker_matches)
            if (
                not description
                and not source_value
                and is_standalone_metadata_feature(normalized_header_name)
            ):
                if features:
                    merge_feature_metadata(
                        features[-1],
                        activation_type=activation_type,
                        tracker_ref=tracker_ref,
                    )
                continue
            if (
                not description
                and not source_value
                and tracker_ref
                and features
                and should_merge_tracker_only_followup_feature(normalized_header_name, features[-1])
            ):
                merge_feature_metadata(
                    features[-1],
                    activation_type=activation_type,
                    tracker_ref=tracker_ref,
                )
                continue
            if not description and not source_value:
                alias_target = find_feature_alias_target(normalized_header_name, features)
                if alias_target is not None:
                    merge_feature_metadata(
                        alias_target,
                        activation_type=activation_type,
                        tracker_ref=tracker_ref,
                    )
                    continue
            if is_ability_choice_followup_feature(
                normalized_header_name,
                category=feature_category,
                previous_feature=features[-1] if features else None,
                description=description,
                source_value=source_value,
            ):
                merge_ability_choice_followup_feature(
                    features[-1],
                    name=normalized_header_name,
                    description=description,
                    activation_type=activation_type,
                    tracker_ref=tracker_ref,
                )
                continue
            if (
                not description
                and not source_value
                and features
                and is_generic_followup_feature(normalized_header_name, str(features[-1].get("name") or ""))
            ):
                merge_feature_metadata(features[-1], activation_type=activation_type, tracker_ref=tracker_ref)
                continue

            features.append(
                {
                    "id": f"{slugify(group_name)}-{slugify(normalized_header_name)}-{index}",
                    "name": normalized_header_name,
                    "category": feature_category,
                    "source": source_value,
                    "description_markdown": description,
                    "activation_type": activation_type,
                    "tracker_ref": tracker_ref,
                }
            )
    return features, list(tracker_templates.values())


def parse_equipment(section_text: str) -> list[dict[str, Any]]:
    equipment_rows = extract_first_table(section_text)
    equipment: list[dict[str, Any]] = []
    for index, row in enumerate(equipment_rows, start=1):
        item_name = row.get("Item", "").strip()
        if not item_name:
            continue
        equipment.append(
            {
                "id": f"{slugify(item_name)}-{index}",
                "name": item_name,
                "default_quantity": parse_int(row.get("Qty")) or 0,
                "weight": row.get("Weight", "").strip(),
                "notes": "",
                "tags": [],
            }
        )
    return equipment


def parse_spellcasting(section_text: str, warnings: list[str]) -> dict[str, Any]:
    subsections = split_sections(section_text, "###")
    preamble = section_text.split("###", 1)[0].strip()
    summary_rows = extract_first_table(preamble)
    summary = {row.get("Field", "").strip(): row.get("Value", "").strip() for row in summary_rows}

    slot_progression: list[dict[str, Any]] = []
    slot_level = 1
    for line in subsections.get("Slots", "").splitlines():
        stripped = line.strip().lstrip("-").strip()
        if not stripped or stripped.lower() == "(at will)":
            continue
        match = re.match(r"(?P<count>\d+)\s+Slots", stripped, re.IGNORECASE)
        if not match:
            warnings.append(f"Could not parse spell slot line: {stripped}")
            continue
        slot_progression.append({"level": slot_level, "max_slots": int(match.group("count"))})
        slot_level += 1

    spell_rows = extract_first_table(subsections.get("Spells", ""))
    spells: list[dict[str, Any]] = []
    for index, row in enumerate(spell_rows, start=1):
        raw_name = row.get("Spell", "").strip()
        is_ritual = raw_name.endswith("[R]")
        spell_name = raw_name[:-3].strip() if is_ritual else raw_name
        mark = row.get("Mark", "").strip()
        spells.append(
            {
                "id": f"{slugify(spell_name)}-{index}",
                "name": spell_name,
                "mark": mark,
                "save_or_hit": row.get("Save/Hit", "").strip(),
                "casting_time": row.get("Time", "").strip(),
                "range": row.get("Range", "").strip(),
                "duration": row.get("Duration", "").strip(),
                "components": row.get("Components", "").strip(),
                "source": row.get("Source", "").strip(),
                "reference": row.get("Reference", "").strip(),
                "is_always_prepared": mark.lower() == "always",
                "is_ritual": is_ritual,
                "spell_level": None,
            }
        )

    return {
        "spellcasting_class": clean_text_value(summary.get("Spellcasting Class", "")),
        "spellcasting_ability": clean_text_value(summary.get("Spellcasting Ability", "")),
        "spell_save_dc": parse_int(summary.get("Spell Save DC")),
        "spell_attack_bonus": parse_signed_int(summary.get("Spell Attack Bonus")),
        "slot_progression": slot_progression,
        "spells": spells,
    }


def parse_personality_and_story(section_text: str, warnings: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    subsections = split_sections(section_text, "###")
    additional_notes = subsections.get("Additional Notes", "").strip()
    custom_sections = [
        {"title": title, "body_markdown": body.strip()}
        for title, body in subsections.items()
        if body.strip()
    ]
    return (
        {
            "additional_notes_markdown": additional_notes,
            "allies_and_organizations_markdown": "",
            "custom_sections": custom_sections,
            "personality_markdown": build_personality_markdown(subsections),
        },
        [],
    )


def parse_actions(
    section_text: str,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    subsections = split_sections(section_text, "###")
    custom_sections = [
        {"title": f"Actions: {title}", "body_markdown": body.strip()}
        for title, body in subsections.items()
        if body.strip()
    ]
    tracker_templates: dict[str, dict[str, Any]] = {}
    action_features: list[dict[str, Any]] = []
    display_order = 0
    action_feature_index = 0
    for title, body in subsections.items():
        for tracker in extract_trackers_from_text(
            body,
            category="class_feature",
            display_start=display_order,
            warnings=warnings,
        ):
            merge_tracker(tracker_templates, tracker, warnings)
            display_order += 1
        activation_hint = activation_type_from_section_title(title)
        for block in parse_action_feature_blocks(body):
            header = str(block.get("header") or "").strip()
            description = str(block.get("description") or "").strip()
            if normalize_feature_text(header) in GENERIC_ACTION_BLOCK_TITLES:
                continue
            tracker_matches = extract_trackers_from_text(
                header,
                category="class_feature",
                display_start=display_order,
                warnings=warnings,
            )
            tracker_ref = tracker_matches[0]["id"] if tracker_matches else None
            for tracker in tracker_matches:
                merge_tracker(tracker_templates, tracker, warnings)
                display_order += 1
            normalized_header = normalize_feature_header_name(header, tracker_matches)
            if (
                not description
                and normalize_feature_text(normalized_header) in STANDALONE_METADATA_TITLES
            ):
                continue
            activation_type = build_activation_type(header)
            if activation_type == "passive":
                activation_type = activation_hint
            action_feature_index += 1
            action_features.append(
                {
                    "id": f"actions-{slugify(normalized_header)}-{action_feature_index}",
                    "name": normalized_header,
                    "category": "class_feature",
                    "source": "",
                    "description_markdown": description,
                    "activation_type": activation_type,
                    "tracker_ref": tracker_ref,
                }
            )
    return custom_sections, list(tracker_templates.values()), action_features


def parse_character_sheet_text(
    campaign_slug: str,
    raw_text: str,
    *,
    source_path: Path | str,
    source_type: str,
    imported_from: str,
    parser_version: str = PARSER_VERSION,
    character_slug: str | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    sections = split_sections(raw_text, "##")
    warnings: list[str] = []

    profile = parse_sheet_summary(sections.get("Sheet Summary", ""), warnings)
    source_name = imported_from.strip() or Path(str(source_path)).name
    fallback_name = source_name.replace(" - Character Sheet", "").replace(".pdf", "").strip()
    name = profile.get("display_name") or fallback_name
    resolved_character_slug = character_slug or slugify(name)

    stats = parse_core_stats(sections.get("Defenses And Core Stats", ""), warnings)
    stats["ability_scores"] = parse_ability_scores(sections.get("Ability Scores", ""))
    skills = parse_skills(sections.get("Skills", ""))
    proficiencies = parse_proficiencies(sections.get("Proficiencies And Languages", ""))
    attacks = parse_attacks(sections.get("Attacks And Cantrips", ""))
    features, feature_trackers = parse_feature_groups(sections.get("Features And Traits", ""), warnings)
    _, action_trackers, action_features = parse_actions(sections.get("Actions", ""), warnings)
    features = merge_action_features_into_features(features, action_features)
    reference_notes, note_trackers = parse_personality_and_story(
        sections.get("Personality And Story", ""),
        warnings,
    )
    spellcasting = parse_spellcasting(sections.get("Spellcasting", ""), warnings)
    equipment_catalog = parse_equipment(sections.get("Equipment", ""))

    tracker_templates: dict[str, dict[str, Any]] = {}
    for tracker in feature_trackers + action_trackers + note_trackers:
        merge_tracker(tracker_templates, tracker, warnings)

    custom_sections = list(reference_notes.get("custom_sections") or [])
    if reference_notes.get("personality_markdown"):
        profile["personality_markdown"] = reference_notes["personality_markdown"]

    definition = CharacterDefinition(
        campaign_slug=campaign_slug,
        character_slug=resolved_character_slug,
        name=name,
        status="active",
        profile=profile,
        stats=stats,
        skills=skills,
        proficiencies=proficiencies,
        attacks=attacks,
        features=features,
        spellcasting=spellcasting,
        equipment_catalog=equipment_catalog,
        reference_notes={
            "additional_notes_markdown": reference_notes.get("additional_notes_markdown", ""),
            "allies_and_organizations_markdown": reference_notes.get("allies_and_organizations_markdown", ""),
            "custom_sections": custom_sections,
        },
        resource_templates=list(tracker_templates.values()),
        source={
            "source_path": str(source_path),
            "source_type": source_type,
            "imported_from": imported_from,
            "imported_at": isoformat(utcnow()),
            "parse_warnings": warnings,
        },
    )
    definition = normalize_definition_to_native_model(definition)
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=resolved_character_slug,
        source_path=str(source_path),
        imported_at_utc=isoformat(utcnow()),
        parser_version=parser_version,
        import_status="warning" if warnings else "clean",
        warnings=warnings,
    )
    return definition, import_metadata


def parse_character_sheet(
    campaign_slug: str,
    source_path: Path,
    *,
    character_slug: str | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    raw_text = source_path.read_text(encoding="utf-8")
    return parse_character_sheet_text(
        campaign_slug,
        raw_text,
        source_path=source_path,
        source_type="markdown_character_sheet",
        imported_from=source_path.name,
        parser_version=PARSER_VERSION,
        character_slug=character_slug,
    )


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(rendered, encoding="utf-8")


def _normalize_import_match_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _hash_import_identity(prefix: str, identity: str) -> str:
    return f"{prefix}:{sha1(identity.encode('utf-8')).hexdigest()[:16]}"


def _load_existing_character_definition(character_dir: Path) -> CharacterDefinition | None:
    definition_path = character_dir / "definition.yaml"
    if not definition_path.exists():
        return None

    existing_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    if not isinstance(existing_payload, dict) or not existing_payload.get("character_slug"):
        return None

    try:
        return CharacterDefinition.from_dict(existing_payload)
    except ValueError:
        return None


def load_existing_character_definition(character_dir: Path) -> CharacterDefinition | None:
    return _load_existing_character_definition(character_dir)


def _attack_match_keys(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    attack_id = str(payload.get("id") or "").strip()
    systems_ref = dict(payload.get("systems_ref") or {})
    page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
    explicit_identity = _normalize_explicit_link_identity(
        systems_ref=systems_ref,
        page_ref=page_ref,
    )
    tail = (
        payload.get("attack_bonus"),
        _normalize_import_match_text(payload.get("damage")),
        _normalize_import_match_text(payload.get("damage_type")),
        _normalize_import_match_text(payload.get("notes")),
        _normalize_import_match_text(payload.get("category")),
    )
    keys: list[tuple[Any, ...]] = []
    if attack_id:
        keys.append(("id", attack_id))
    if explicit_identity:
        keys.append(("explicit", explicit_identity, *tail))
    keys.extend(("name", candidate, *tail) for candidate in _merge_name_candidates(payload.get("name")))
    return keys


def _equipment_match_keys(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    equipment_id = str(payload.get("id") or "").strip()
    systems_ref = dict(payload.get("systems_ref") or {})
    page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
    explicit_identity = _normalize_explicit_link_identity(
        systems_ref=systems_ref,
        page_ref=page_ref,
    )
    tail = (
        _normalize_import_match_text(payload.get("weight")),
        _normalize_import_match_text(payload.get("notes")),
        bool(payload.get("is_currency_only")),
        _normalize_import_match_text(payload.get("source_kind")),
    )
    keys: list[tuple[Any, ...]] = []
    if equipment_id:
        keys.append(("id", equipment_id))
    if explicit_identity:
        keys.append(("explicit", explicit_identity, *tail))
    keys.extend(("name", candidate, *tail) for candidate in _merge_name_candidates(payload.get("name")))
    return keys


def _spell_match_keys(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    spell_id = str(payload.get("id") or "").strip()
    class_row_id = str(payload.get("class_row_id") or "").strip()
    source_row_id = str(payload.get("spell_source_row_id") or "").strip()
    source_row_kind = str(payload.get("spell_source_row_kind") or "source").strip() or "source"
    if class_row_id:
        tail = ("class", class_row_id)
    elif source_row_id:
        tail = (source_row_kind, source_row_id)
    else:
        tail = ()
    systems_ref = dict(payload.get("systems_ref") or {})
    page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
    explicit_identity = _normalize_explicit_link_identity(
        systems_ref=systems_ref,
        page_ref=page_ref,
    )
    keys: list[tuple[Any, ...]] = []
    if spell_id:
        keys.append(("id", spell_id, *tail))
    if explicit_identity:
        keys.append(("explicit", explicit_identity, *tail))
    spell_key = _spell_payload_key(payload)
    if spell_key:
        keys.append(("spell-key", spell_key.strip().lower(), *tail))
    keys.extend(("name", candidate, *tail) for candidate in _merge_name_candidates(payload.get("name")))
    return keys


def _feature_match_keys(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    feature_id = str(payload.get("id") or "").strip()
    systems_ref = dict(payload.get("systems_ref") or {})
    page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
    explicit_identity = _normalize_explicit_link_identity(
        systems_ref=systems_ref,
        page_ref=page_ref,
    )
    keys: list[tuple[Any, ...]] = []
    if feature_id:
        keys.append(("id", feature_id))
    if explicit_identity:
        keys.append(("explicit", explicit_identity))
    keys.append(
        (
            "feature",
            _normalize_import_match_text(payload.get("category")),
            _normalize_import_match_text(payload.get("name")),
            _normalize_import_match_text(payload.get("source")),
            _normalize_import_match_text(payload.get("description_markdown")),
            _normalize_import_match_text(payload.get("activation_type")),
        )
    )
    keys.append(
        (
            "feature-core",
            _normalize_import_match_text(payload.get("category")),
            _normalize_import_match_text(payload.get("name")),
            _normalize_import_match_text(payload.get("source")),
            _normalize_import_match_text(payload.get("description_markdown")),
        )
    )
    return keys


def _resource_template_match_keys(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    template_id = str(payload.get("id") or "").strip()
    keys: list[tuple[Any, ...]] = []
    if template_id:
        keys.append(("id", template_id))
    keys.append(
        (
            "resource",
            _normalize_import_match_text(payload.get("label")),
            _normalize_import_match_text(payload.get("category")),
            payload.get("max"),
            _normalize_import_match_text(payload.get("reset_on")),
            _normalize_import_match_text(payload.get("notes")),
        )
    )
    return keys


def _build_existing_match_lookup(
    entries: list[dict[str, Any]],
    key_builder,
) -> dict[tuple[Any, ...], dict[str, Any]]:
    lookup: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in entries:
        payload = dict(entry or {})
        for key in key_builder(payload):
            lookup.setdefault(key, payload)
    return lookup


def _matched_existing_entry(
    payload: dict[str, Any],
    existing_lookup: dict[tuple[Any, ...], dict[str, Any]],
    key_builder,
) -> dict[str, Any] | None:
    for key in key_builder(payload):
        existing = existing_lookup.get(key)
        if existing is not None:
            return existing
    return None


def _clone_link_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    return value


def _merge_existing_native_managed_entries(
    imported_entries: list[dict[str, Any]],
    existing_entries: list[dict[str, Any]],
    *,
    key_builder,
    include_entry,
) -> list[dict[str, Any]]:
    merged = [dict(entry or {}) for entry in imported_entries]
    lookup = _build_existing_match_lookup(merged, key_builder)
    for existing in existing_entries:
        payload = dict(existing or {})
        if not include_entry(payload):
            continue
        if _matched_existing_entry(payload, lookup, key_builder) is not None:
            continue
        merged.append(payload)
        for key in key_builder(payload):
            lookup.setdefault(key, payload)
    return merged


def _is_native_managed_feature_overlay(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("category") or "").strip()
        == NATIVE_MANAGED_CUSTOM_FEATURE_CATEGORY
    )


def _is_native_managed_equipment_overlay(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("source_kind") or "").strip()
        == NATIVE_MANAGED_CUSTOM_EQUIPMENT_SOURCE_KIND
    )


def _is_native_managed_spell_overlay(payload: dict[str, Any]) -> bool:
    return bool(
        str(payload.get("spell_source_row_id") or "").strip()
        or str(payload.get("grant_source_label") or "").strip()
        or str(payload.get("spell_access_type") or "").strip()
        or list(payload.get("campaign_option_sources") or [])
        or list(payload.get("campaign_option_replaced_by") or [])
    )


def _is_native_progression_managed_feature_overlay(payload: dict[str, Any]) -> bool:
    feature_payload = dict(payload or {})
    systems_ref = dict(feature_payload.get("systems_ref") or {})
    entry_type = str(systems_ref.get("entry_type") or "").strip().lower()
    category = str(feature_payload.get("category") or "").strip().lower()
    return entry_type in {"feat", "optionalfeature"} or category == "feat"


def _merge_existing_native_managed_overlays(
    definition: CharacterDefinition,
    existing_definition: CharacterDefinition,
) -> CharacterDefinition:
    payload = deepcopy(definition.to_dict())
    existing_payload = deepcopy(existing_definition.to_dict())
    preserve_native_progression_features = _has_native_progression_history(dict(existing_payload.get("source") or {}))

    merged_features = _merge_existing_native_managed_entries(
        list(payload.get("features") or []),
        list(existing_payload.get("features") or []),
        key_builder=_feature_match_keys,
        include_entry=lambda entry: _is_native_managed_feature_overlay(entry)
        or (
            preserve_native_progression_features
            and _is_native_progression_managed_feature_overlay(entry)
        ),
    )
    payload["features"] = merged_features

    payload["equipment_catalog"] = _merge_existing_native_managed_entries(
        list(payload.get("equipment_catalog") or []),
        list(existing_payload.get("equipment_catalog") or []),
        key_builder=_equipment_match_keys,
        include_entry=_is_native_managed_equipment_overlay,
    )

    native_feature_tracker_refs = {
        str(feature.get("tracker_ref") or "").strip()
        for feature in merged_features
        if _is_native_managed_feature_overlay(feature)
        and str(feature.get("tracker_ref") or "").strip()
    }
    if native_feature_tracker_refs:
        resource_templates = [dict(template or {}) for template in list(payload.get("resource_templates") or [])]
        existing_templates = [dict(template or {}) for template in list(existing_payload.get("resource_templates") or [])]
        existing_lookup = _build_existing_match_lookup(resource_templates, _resource_template_match_keys)
        for template in existing_templates:
            template_payload = dict(template or {})
            template_id = str(template_payload.get("id") or "").strip()
            if template_id not in native_feature_tracker_refs:
                continue
            if _matched_existing_entry(template_payload, existing_lookup, _resource_template_match_keys) is not None:
                continue
            resource_templates.append(template_payload)
            for key in _resource_template_match_keys(template_payload):
                existing_lookup.setdefault(key, template_payload)
        payload["resource_templates"] = resource_templates

    spellcasting = dict(payload.get("spellcasting") or {})
    existing_spellcasting = dict(existing_payload.get("spellcasting") or {})
    spellcasting["spells"] = _merge_existing_native_managed_entries(
        list(spellcasting.get("spells") or []),
        list(existing_spellcasting.get("spells") or []),
        key_builder=_spell_match_keys,
        include_entry=_is_native_managed_spell_overlay,
    )
    replacement_bases = _merge_existing_native_managed_entries(
        list(spellcasting.get("campaign_option_replacement_bases") or []),
        list(existing_spellcasting.get("campaign_option_replacement_bases") or []),
        key_builder=_spell_match_keys,
        include_entry=_is_native_managed_spell_overlay,
    )
    if replacement_bases:
        spellcasting["campaign_option_replacement_bases"] = replacement_bases
    else:
        spellcasting.pop("campaign_option_replacement_bases", None)
    payload["spellcasting"] = spellcasting
    return CharacterDefinition.from_dict(payload)


def _preserve_existing_profile_refs(
    imported_profile: dict[str, Any],
    existing_profile: dict[str, Any],
) -> dict[str, Any]:
    def _class_row_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
        payload = dict(row or {})
        systems_ref = dict(payload.get("systems_ref") or {})
        subclass_ref = dict(payload.get("subclass_ref") or {})
        return (
            str(systems_ref.get("source_id") or "").strip().upper(),
            str(systems_ref.get("slug") or payload.get("class_name") or "").strip().lower(),
            str(subclass_ref.get("source_id") or "").strip().upper(),
            str(subclass_ref.get("slug") or payload.get("subclass_name") or "").strip().lower(),
        )

    profile = dict(imported_profile or {})
    previous_profile = dict(existing_profile or {})
    for field in ("class_ref", "subclass_ref", "species_ref", "background_ref"):
        if profile.get(field):
            continue
        if previous_profile.get(field):
            profile[field] = dict(previous_profile.get(field) or {})
    imported_classes = ensure_profile_class_rows(profile)
    existing_classes = ensure_profile_class_rows(previous_profile)
    if imported_classes and existing_classes:
        existing_by_row_id = {
            str(row.get("row_id") or "").strip(): dict(row)
            for row in existing_classes
            if str(row.get("row_id") or "").strip()
        }
        existing_by_identity = {
            _class_row_identity(row): dict(row)
            for row in existing_classes
            if any(_class_row_identity(row))
        }
        preserved_classes: list[dict[str, Any]] = []
        for index, imported_row in enumerate(imported_classes):
            payload = dict(imported_row or {})
            row_id = str(payload.get("row_id") or "").strip()
            existing_row = existing_by_row_id.get(row_id)
            if existing_row is None:
                existing_row = existing_by_identity.get(_class_row_identity(payload))
            if existing_row is None and index < len(existing_classes):
                existing_row = dict(existing_classes[index] or {})
            if existing_row is not None:
                payload["row_id"] = str(existing_row.get("row_id") or row_id).strip() or row_id
                if existing_row.get("systems_ref") and not payload.get("systems_ref"):
                    payload["systems_ref"] = dict(existing_row.get("systems_ref") or {})
                if existing_row.get("subclass_ref") and not payload.get("subclass_ref"):
                    payload["subclass_ref"] = dict(existing_row.get("subclass_ref") or {})
            preserved_classes.append(payload)
        profile["classes"] = preserved_classes
    return profile


def _preserve_existing_source_metadata(
    imported_source: dict[str, Any],
    existing_source: dict[str, Any],
) -> dict[str, Any]:
    source = dict(imported_source or {})
    previous_source = dict(existing_source or {})
    existing_native_progression = dict(previous_source.get("native_progression") or {})
    incoming_native_progression = dict(source.get("native_progression") or {})
    if existing_native_progression:
        merged_native_progression = dict(existing_native_progression)
        if incoming_native_progression.get("hp_baseline") and not merged_native_progression.get("hp_baseline"):
            merged_native_progression["hp_baseline"] = dict(incoming_native_progression.get("hp_baseline") or {})
        if incoming_native_progression.get("history"):
            merged_native_progression["history"] = [
                dict(entry) for entry in list(incoming_native_progression.get("history") or []) if isinstance(entry, dict)
            ]
        source["native_progression"] = merged_native_progression
    elif incoming_native_progression:
        source["native_progression"] = incoming_native_progression
    for field in ("source_path", "source_type", "imported_from"):
        if source.get(field):
            continue
        if previous_source.get(field):
            source[field] = previous_source.get(field)
    return source


def _has_native_progression_history(source_payload: dict[str, Any]) -> bool:
    native_progression = dict(source_payload.get("native_progression") or {})
    return bool(list(native_progression.get("history") or []))


def _preserve_existing_attack_or_equipment_overrides(
    imported_entries: list[dict[str, Any]],
    existing_entries: list[dict[str, Any]],
    *,
    key_builder,
) -> list[dict[str, Any]]:
    existing_lookup = _build_existing_match_lookup(existing_entries, key_builder)
    merged: list[dict[str, Any]] = []
    for entry in imported_entries:
        payload = dict(entry or {})
        existing = _matched_existing_entry(payload, existing_lookup, key_builder)
        if existing is not None:
            existing_id = str(existing.get("id") or "").strip()
            if existing_id:
                payload["id"] = existing_id
            existing_page_ref = existing.get("page_ref")
            if existing_page_ref:
                payload["page_ref"] = _clone_link_payload(existing_page_ref)
                payload.pop("systems_ref", None)
                existing_name = str(existing.get("name") or "").strip()
                if existing_name:
                    payload["name"] = existing_name
            elif existing.get("systems_ref") and not payload.get("systems_ref"):
                payload["systems_ref"] = dict(existing.get("systems_ref") or {})
        merged.append(payload)
    return merged


def _preserve_existing_spell_overrides(
    imported_spells: list[dict[str, Any]],
    existing_spells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_lookup = _build_existing_match_lookup(existing_spells, _spell_match_keys)
    merged: list[dict[str, Any]] = []
    for spell in imported_spells:
        payload = dict(spell or {})
        existing = _matched_existing_entry(payload, existing_lookup, _spell_match_keys)
        if existing is not None:
            existing_id = str(existing.get("id") or "").strip()
            if existing_id:
                payload["id"] = existing_id
            existing_page_ref = existing.get("page_ref")
            if existing_page_ref:
                payload["page_ref"] = _clone_link_payload(existing_page_ref)
                existing_name = str(existing.get("name") or "").strip()
                if existing_name:
                    payload["name"] = existing_name
            if existing.get("systems_ref") and not payload.get("systems_ref"):
                payload["systems_ref"] = dict(existing.get("systems_ref") or {})
        merged.append(payload)
    return merged


def _preserve_existing_feature_overrides(
    imported_features: list[dict[str, Any]],
    existing_features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    existing_lookup = _build_existing_match_lookup(existing_features, _feature_match_keys)
    tracker_id_map: dict[str, str] = {}
    merged: list[dict[str, Any]] = []
    for feature in imported_features:
        payload = dict(feature or {})
        existing = _matched_existing_entry(payload, existing_lookup, _feature_match_keys)
        if existing is not None:
            existing_id = str(existing.get("id") or "").strip()
            if existing_id:
                payload["id"] = existing_id
            existing_page_ref = existing.get("page_ref")
            if existing_page_ref and not payload.get("page_ref"):
                payload["page_ref"] = _clone_link_payload(existing_page_ref)
            if existing.get("systems_ref") and not payload.get("systems_ref"):
                payload["systems_ref"] = dict(existing.get("systems_ref") or {})
            old_tracker_ref = str(existing.get("tracker_ref") or "").strip()
            new_tracker_ref = str(payload.get("tracker_ref") or "").strip()
            if old_tracker_ref:
                payload["tracker_ref"] = old_tracker_ref
                if new_tracker_ref and new_tracker_ref != old_tracker_ref:
                    tracker_id_map[new_tracker_ref] = old_tracker_ref
        merged.append(payload)
    return merged, tracker_id_map


def _preserve_existing_resource_template_overrides(
    imported_templates: list[dict[str, Any]],
    existing_templates: list[dict[str, Any]],
    *,
    tracker_id_map: dict[str, str],
) -> list[dict[str, Any]]:
    existing_lookup = _build_existing_match_lookup(existing_templates, _resource_template_match_keys)
    merged: list[dict[str, Any]] = []
    for template in imported_templates:
        payload = dict(template or {})
        template_id = str(payload.get("id") or "").strip()
        if template_id in tracker_id_map:
            payload["id"] = tracker_id_map[template_id]
        existing = _matched_existing_entry(payload, existing_lookup, _resource_template_match_keys)
        if existing is not None:
            existing_id = str(existing.get("id") or "").strip()
            if existing_id:
                payload["id"] = existing_id
        merged.append(payload)
    return merged


def _assign_missing_imported_ids(payload: dict[str, Any]) -> dict[str, Any]:
    definition = dict(payload or {})
    attacks: list[dict[str, Any]] = []
    for attack in list(definition.get("attacks") or []):
        attack_payload = dict(attack or {})
        if not str(attack_payload.get("id") or "").strip():
            attack_identity = "|".join(str(part) for part in (_attack_match_keys(attack_payload)[:1] or [attack_payload.get("name")]))
            attack_payload["id"] = _hash_import_identity("imported-attack", attack_identity)
        attacks.append(attack_payload)
    definition["attacks"] = attacks

    equipment_catalog: list[dict[str, Any]] = []
    for item in list(definition.get("equipment_catalog") or []):
        item_payload = dict(item or {})
        if not str(item_payload.get("id") or "").strip():
            item_identity = "|".join(str(part) for part in (_equipment_match_keys(item_payload)[:1] or [item_payload.get("name")]))
            item_payload["id"] = _hash_import_identity("imported-item", item_identity)
        equipment_catalog.append(item_payload)
    definition["equipment_catalog"] = equipment_catalog

    features: list[dict[str, Any]] = []
    for feature in list(definition.get("features") or []):
        feature_payload = dict(feature or {})
        if not str(feature_payload.get("id") or "").strip():
            feature_identity = "|".join(str(part) for part in _feature_match_keys(feature_payload)[:1])
            feature_payload["id"] = _hash_import_identity("imported-feature", feature_identity)
        features.append(feature_payload)
    definition["features"] = features

    spellcasting = dict(definition.get("spellcasting") or {})
    spells: list[dict[str, Any]] = []
    for spell in list(spellcasting.get("spells") or []):
        spell_payload = dict(spell or {})
        if not str(spell_payload.get("id") or "").strip():
            spell_identity = "|".join(str(part) for part in (_spell_match_keys(spell_payload)[:1] or [spell_payload.get("name")]))
            spell_payload["id"] = _hash_import_identity("imported-spell", spell_identity)
        spells.append(spell_payload)
    spellcasting["spells"] = spells
    definition["spellcasting"] = spellcasting

    resource_templates: list[dict[str, Any]] = []
    for template in list(definition.get("resource_templates") or []):
        template_payload = dict(template or {})
        if not str(template_payload.get("id") or "").strip():
            template_identity = "|".join(str(part) for part in _resource_template_match_keys(template_payload)[:1])
            template_payload["id"] = _hash_import_identity("imported-resource", template_identity)
        resource_templates.append(template_payload)
    definition["resource_templates"] = resource_templates
    return definition


def converge_imported_definition(
    definition: CharacterDefinition,
    *,
    existing_definition: CharacterDefinition | None = None,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: Any | None = None,
    resolved_subclass: Any | None = None,
    resolved_species: Any | None = None,
    resolved_background: Any | None = None,
) -> CharacterDefinition:
    if existing_definition is not None:
        definition = _merge_existing_native_managed_overlays(
            definition,
            existing_definition,
        )
    normalized_definition = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
    )
    if existing_definition is None:
        return CharacterDefinition.from_dict(
            _assign_missing_imported_ids(normalized_definition.to_dict())
        )

    normalized_existing = normalize_definition_to_native_model(
        existing_definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    payload = normalized_definition.to_dict()
    existing_payload = normalized_existing.to_dict()

    payload["source"] = _preserve_existing_source_metadata(
        dict(payload.get("source") or {}),
        dict(existing_payload.get("source") or {}),
    )

    if (
        _has_native_progression_history(dict(existing_payload.get("source") or {}))
        and _resolve_native_character_level(normalized_definition) < _resolve_native_character_level(normalized_existing)
    ):
        for field in (
            "profile",
            "stats",
            "skills",
            "proficiencies",
            "attacks",
            "features",
            "spellcasting",
            "equipment_catalog",
            "reference_notes",
            "resource_templates",
        ):
            payload[field] = deepcopy(existing_payload.get(field))
        return CharacterDefinition.from_dict(_assign_missing_imported_ids(payload))

    payload["profile"] = _preserve_existing_profile_refs(
        dict(payload.get("profile") or {}),
        dict(existing_payload.get("profile") or {}),
    )
    payload["attacks"] = _preserve_existing_attack_or_equipment_overrides(
        list(payload.get("attacks") or []),
        list(existing_payload.get("attacks") or []),
        key_builder=_attack_match_keys,
    )
    payload["equipment_catalog"] = _preserve_existing_attack_or_equipment_overrides(
        list(payload.get("equipment_catalog") or []),
        list(existing_payload.get("equipment_catalog") or []),
        key_builder=_equipment_match_keys,
    )
    payload["features"], tracker_id_map = _preserve_existing_feature_overrides(
        list(payload.get("features") or []),
        list(existing_payload.get("features") or []),
    )
    payload["resource_templates"] = _preserve_existing_resource_template_overrides(
        list(payload.get("resource_templates") or []),
        list(existing_payload.get("resource_templates") or []),
        tracker_id_map=tracker_id_map,
    )
    spellcasting = dict(payload.get("spellcasting") or {})
    existing_spellcasting = dict(existing_payload.get("spellcasting") or {})
    spellcasting["spells"] = _preserve_existing_spell_overrides(
        list(spellcasting.get("spells") or []),
        list(existing_spellcasting.get("spells") or []),
    )
    payload["spellcasting"] = spellcasting
    return CharacterDefinition.from_dict(_assign_missing_imported_ids(payload))


def preserve_existing_character_overrides(
    definition: CharacterDefinition,
    character_dir: Path,
    *,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> CharacterDefinition:
    existing_definition = _load_existing_character_definition(character_dir)
    return converge_imported_definition(
        definition,
        existing_definition=existing_definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )


def initialize_or_reconcile_imported_state(
    state_store: CharacterStateStore,
    definition: CharacterDefinition,
    *,
    previous_definition: CharacterDefinition | None = None,
) -> CharacterStateWriteResult:
    existing = state_store.get_state(definition.campaign_slug, definition.character_slug)
    if existing is None:
        initial_state = build_initial_state(definition)
        return state_store.initialize_state_if_missing(definition, initial_state)

    previous_resource_ids = {
        str(template.get("id") or "").strip()
        for template in list((previous_definition.resource_templates if previous_definition is not None else []) or [])
        if str(template.get("id") or "").strip()
    }
    current_resource_ids = {
        str(template.get("id") or "").strip()
        for template in list(definition.resource_templates or [])
        if str(template.get("id") or "").strip()
    }
    reconciled_state = merge_state_with_definition(definition, existing.state)
    if previous_resource_ids:
        reconciled_state = merge_state_with_definition(
            definition,
            existing.state,
            removed_resource_ids=previous_resource_ids - current_resource_ids,
        )
    if reconciled_state == existing.state:
        return CharacterStateWriteResult(record=existing, created=False)

    updated = state_store.replace_state(
        definition,
        reconciled_state,
        expected_revision=existing.revision,
    )
    return CharacterStateWriteResult(record=updated, created=False)


def import_character(
    project_root: Path,
    campaign_slug: str,
    source_arg: str,
    *,
    character_slug: str | None = None,
) -> CharacterImportResult:
    from .app import create_app

    app = create_app()
    with app.app_context():
        init_database()
        state_store: CharacterStateStore = app.extensions["character_state_store"]
        systems_service = app.extensions["systems_service"]
        campaign_page_records = list(app.extensions["campaign_page_store"].list_page_records(campaign_slug))
        campaigns_dir: Path = app.config["CAMPAIGNS_DIR"]
        config = load_campaign_character_config(campaigns_dir, campaign_slug)
        source_path = resolve_source_path(config, source_arg)
        definition, import_metadata = parse_character_sheet(
            campaign_slug,
            source_path,
            character_slug=character_slug,
        )
        character_dir = config.characters_dir / definition.character_slug
        existing_definition = load_existing_character_definition(character_dir)
        definition = preserve_existing_character_overrides(
            definition,
            character_dir,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        state_result = initialize_or_reconcile_imported_state(
            state_store,
            definition,
            previous_definition=existing_definition,
        )
        return CharacterImportResult(
            definition=definition,
            import_metadata=import_metadata,
            character_dir=character_dir,
            state_created=state_result.created,
        )


def command_search(project_root: Path, args: argparse.Namespace) -> int:
    campaigns_dir = project_root / "campaigns"
    config = load_campaign_character_config(campaigns_dir, args.campaign)
    query = args.query.strip().lower()
    matches: list[Path] = []
    for source_path in iter_character_source_files(config):
        relative_path = source_path.relative_to(config.source_root).as_posix()
        if not query or query in relative_path.lower() or query in source_path.stem.lower():
            matches.append(source_path)
    for match in matches[: args.limit]:
        print(match.relative_to(config.source_root).as_posix())
    if not matches:
        print(f"No character sheets matched '{args.query}'.")
    return 0


def command_import(project_root: Path, args: argparse.Namespace) -> int:
    result = import_character(
        project_root,
        args.campaign,
        args.source,
        character_slug=args.character_slug,
    )
    print(f"Imported: {result.definition.name}")
    print(f"Character slug: {result.definition.character_slug}")
    print(f"Definition: {result.character_dir / 'definition.yaml'}")
    print(f"Import metadata: {result.character_dir / 'import.yaml'}")
    print(f"State initialized: {'yes' if result.state_created else 'already existed'}")
    if result.import_metadata.warnings:
        print("Warnings:")
        for warning in result.import_metadata.warnings:
            print(f"  - {warning}")
    return 0


def command_pdf_pilot(project_root: Path, args: argparse.Namespace) -> int:
    from .character_pdf_importer import run_pdf_pilot

    result = run_pdf_pilot(
        project_root,
        args.campaign,
        Path(args.pdf_path),
        character_slug=args.character_slug,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(f"Pilot draft: {result.definition.name}")
    print(f"Character slug: {result.definition.character_slug}")
    print(f"Output directory: {result.output_dir}")
    print(f"Fields: {result.fields_path}")
    print(f"Synthetic markdown: {result.synthetic_markdown_path}")
    print(f"Definition draft: {result.definition_path}")
    print(f"Systems links: {result.systems_links_path}")
    print(f"Report: {result.report_path}")
    if result.import_metadata.warnings:
        print("Warnings:")
        for warning in result.import_metadata.warnings:
            print(f"  - {warning}")
    return 0


def command_pdf_import(project_root: Path, args: argparse.Namespace) -> int:
    from .character_pdf_importer import import_pdf_character

    result = import_pdf_character(
        project_root,
        args.campaign,
        Path(args.pdf_path),
        character_slug=args.character_slug,
    )
    print(f"Imported PDF character: {result.definition.name}")
    print(f"Character slug: {result.definition.character_slug}")
    print(f"Definition: {result.character_dir / 'definition.yaml'}")
    print(f"Import metadata: {result.character_dir / 'import.yaml'}")
    print(f"State initialized: {'yes' if result.state_created else 'already existed'}")
    if result.import_metadata.warnings:
        print("Warnings:")
        for warning in result.import_metadata.warnings:
            print(f"  - {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and import campaign character sheets into structured definition files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search configured character-sheet sources.")
    search_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    search_parser.add_argument("query", help="Search text for a character sheet path or title fragment")
    search_parser.add_argument("--limit", type=int, default=15, help="Maximum results to print")

    import_parser = subparsers.add_parser("import", help="Import one character sheet into structured records.")
    import_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    import_parser.add_argument("source", help="Source path or unique character title/path fragment")
    import_parser.add_argument("--character-slug", help="Override the generated character slug")

    pdf_pilot_parser = subparsers.add_parser(
        "pdf-pilot",
        help="Extract one flattened character-sheet PDF into local draft files and a Systems match report.",
    )
    pdf_pilot_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    pdf_pilot_parser.add_argument("pdf_path", help="Path to a character-sheet PDF export")
    pdf_pilot_parser.add_argument("--character-slug", help="Override the generated character slug")
    pdf_pilot_parser.add_argument(
        "--output-dir",
        help="Optional output directory for draft files. Defaults to .local/character_pdf_pilots/<slug>",
    )

    pdf_import_parser = subparsers.add_parser(
        "pdf-import",
        help="Import one character-sheet PDF into structured character files and initialize state.",
    )
    pdf_import_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    pdf_import_parser.add_argument("pdf_path", help="Path to a character-sheet PDF export")
    pdf_import_parser.add_argument("--character-slug", help="Override the generated character slug")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = Path(__file__).resolve().parent.parent

    try:
        if args.command == "search":
            return command_search(project_root, args)
        if args.command == "import":
            return command_import(project_root, args)
        if args.command == "pdf-pilot":
            return command_pdf_pilot(project_root, args)
        if args.command == "pdf-import":
            return command_pdf_import(project_root, args)
    except CharacterImportError as error:
        print(error)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2
